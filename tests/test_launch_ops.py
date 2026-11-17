"""Milestone F and isolated test bot: never require real Discord or MR tokens."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path

import pytest

from snowfall.config import load_settings
from snowfall.db.store import Store
from snowfall.ops import (
    OperationsError, adjust_personal_score, approve_launch, award_csv,
    backup_sqlite, capture_final_awards, check_backup, check_health, is_approved,
    mark_prize, reconcile, restore_sqlite,
)
from snowfall.simulate import run_simulation

START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
KEY = "ops-2026"


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "state.sqlite3")
    db.initialize()
    db.ensure_season(KEY, START)
    db.register(KEY, 101, "Alpha", "Chicago", START - timedelta(days=1))
    db.register(KEY, 102, "Bravo", "New York", START - timedelta(days=1))
    db.register(KEY, 103, "Charlie", "Detroit", START - timedelta(days=1))
    return db


def _score(db, user, pts, day=1):
    with db.connect() as con:
        con.execute("INSERT INTO score_ledger(season_key,day,player_id,city,category,points,"
                    "source_key,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                    (KEY, day, user, {101:"Chicago",102:"New York",103:"Detroit"}[user],
                     "admin_adjustment", pts, f"seed:{day}:{user}", START.isoformat()))


def test_legacy_v5_migration_preserves_users_and_wal(store):
    with store.connect() as con:
        con.execute("DROP TABLE IF EXISTS launch_approvals")
        con.execute("DROP TRIGGER IF EXISTS prize_awards_immutable_delete")
        con.execute("DROP TABLE IF EXISTS prize_awards")
        con.execute("PRAGMA user_version=5")
    store.initialize()
    store.initialize()
    assert store.schema_version() == 9
    assert len(store.registrations(KEY)) == 3
    assert store.season(KEY).phase(START) == "ready"
    assert store.connect is not None


def test_launch_approval_audited_and_start_date_bound(store):
    assert not is_approved(store, KEY)
    with pytest.raises(OperationsError, match="reason"):
        approve_launch(store, KEY, 9, "short", START - timedelta(days=1))
    approve_launch(store, KEY, 9, "Kat confirmed rehearsal", START - timedelta(days=1))
    assert is_approved(store, KEY)
    assert store.audit_entries(KEY)[-1]["action"] == "launch:approve"


def test_approval_cannot_be_recorded_after_start(store):
    store.transition(KEY, 999, "start", START, "Start")
    with pytest.raises(OperationsError, match="before"):
        approve_launch(store, KEY, 9, "late approval forbidden", START)


def test_score_corrections_are_append_only_audited_and_idempotent(store):
    _score(store, 101, 80)
    store.transition(KEY, 999, "start", START, "Start")
    when = START + timedelta(minutes=1)
    assert adjust_personal_score(store, KEY, 999, 101, 1, -20,
                                 "Correct duplicate claim", "fix-001", when) == -20
    assert adjust_personal_score(store, KEY, 999, 101, 1, -20,
                                 "Correct duplicate claim", "fix-001", when) == -20
    assert check_health(store, KEY)["ledger_entries"] == 2
    with pytest.raises(OperationsError, match="already used"):
        adjust_personal_score(store, KEY, 999, 102, 1, -20,
                              "Incorrect other identity", "fix-001", when)
    with pytest.raises(OperationsError, match="below zero"):
        adjust_personal_score(store, KEY, 999, 101, 1, -99,
                              "Larger than balance", "fix-002", when)
    with store.connect() as con:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("UPDATE score_ledger SET points=1 WHERE source_key='admin:fix-001'")
    assert any(x["action"] == "score:adjust" for x in store.audit_entries(KEY))


def test_corrections_rejected_after_finalization(store):
    store.transition(KEY, 999, "start", START, "Start")
    end = START + timedelta(days=7)
    store.transition(KEY, 999, "finalize", end, "End")
    with pytest.raises(OperationsError, match="before finalization"):
        adjust_personal_score(store, KEY, 999, 101, 1, 1,
                              "Inadmissible late credit", "too-late", end)


def test_individual_only_awards_snapshot_and_manual_paid_tracking(store):
    for who, pts in ((101, 120), (102, 100), (103, 80)):
        _score(store, who, pts)
    store.review(KEY, 999, 102, "flagged", "Review claimed identity", START)
    store.transition(KEY, 999, "start", START, "Start")
    with pytest.raises(OperationsError, match="finalized"):
        capture_final_awards(store, KEY, 999, START)
    end = START + timedelta(days=7)
    store.transition(KEY, 999, "finalize", end, "End")
    awards = capture_final_awards(store, KEY, 999, end)
    assert [(r["place"], r["mr_username"]) for r in awards] == [(1, "Alpha"), (2, "Charlie")]
    assert capture_final_awards(store, KEY, 999, end) == awards
    raw = award_csv(awards).decode("utf-8-sig")
    assert "Alpha" in raw and "Charlie" in raw and "Bravo" not in raw
    assert "city_winner" not in raw and "city_prize" not in raw
    mark_prize(store, KEY, 999, 1, "2 MR credits, delivered manually", "paid",
               "Verified delivery in MR", end)
    with pytest.raises(OperationsError, match="reverted"):
        mark_prize(store, KEY, 999, 1, "Same", "pending", "Oops attempted revert", end)
    with store.connect() as con:
        assert con.execute("SELECT status FROM prize_awards WHERE place=1").fetchone()[0] == "paid"


def test_reconcile_detects_missing_pvp_ledger(store):
    store.transition(KEY, 999, "start", START, "Start")
    with store.connect() as con:
        con.execute("""INSERT INTO combat_events
          (interaction_id,season_key,day,attacker_id,target_id,target_city,style,
           happened_at_utc,effective_at_utc,hit,critical,hit_roll,armour_damage,
           warmth_damage,knocked_out,points_awarded,bonus_city,bonus_ko,defense_points)
           VALUES(?,?,1,101,102,'New York','quick',?,?,1,0,0.1,0,8,0,8,0,0,0)""",
           ("missing-ledger", KEY, START.isoformat(), START.isoformat()))
    result = reconcile(store, KEY)
    assert not result["ok"]
    assert result["mismatched_combat_ids"] == ["missing-ledger"]


def test_backup_checksum_restore_and_pre_restore_safety_copy(store, tmp_path):
    original = backup_sqlite(store.path, tmp_path / "backups")
    assert check_backup(original)["sha256"]
    restore_target = tmp_path / "restored.sqlite3"
    with pytest.raises(OperationsError, match="RESTORE"):
        restore_sqlite(original, restore_target, confirmation="no")
    assert restore_sqlite(original, restore_target, confirmation="RESTORE") == restore_target
    restored = Store(restore_target)
    assert len(restored.registrations(KEY)) == 3
    # Simulate stopping the process and checkpointing before a second restore.
    # sqlite3.Connection.__exit__ commits but does NOT close on Windows.
    with closing(sqlite3.connect(restore_target)) as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
    second = restore_sqlite(original, restore_target, confirmation="RESTORE")
    assert second == restore_target
    assert list((tmp_path / "pre_restore_backups").glob("*.sqlite3"))
    original.write_bytes(original.read_bytes() + b"tamper")
    with pytest.raises(OperationsError, match="checksum mismatch"):
        check_backup(original)


def test_locked_restore_is_reported_without_overwriting_target(store, tmp_path, monkeypatch):
    original = backup_sqlite(store.path, tmp_path / "backups")
    target = tmp_path / "target.sqlite3"
    restore_sqlite(original, target, confirmation="RESTORE")
    content_before = target.read_bytes()
    original_replace = Path.replace

    def simulate_windows_lock(path, destination):
        if path.name.startswith(".restore-"):
            raise PermissionError("WinError 5: file is held open")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", simulate_windows_lock)
    with pytest.raises(OperationsError, match="target is locked"):
        restore_sqlite(original, target, confirmation="RESTORE")
    assert target.read_bytes() == content_before


def test_restoring_into_active_wal_is_rejected(store, tmp_path):
    source = backup_sqlite(store.path, tmp_path / "backups")
    Path(str(store.path) + "-wal").touch()
    with pytest.raises(OperationsError, match="WAL/SHM"):
        restore_sqlite(source, store.path, confirmation="RESTORE")


def _write_toml(path, guild, db, season, backup):
    path.write_text(f'''[discord]
guild_id = {guild}
admin_user_ids = [123]
leaderboard_channel_id = 0
announcement_channel_id = 0
[event]
season_key = "{season}"
name = "Snowfall"
starts_at_utc = "AUTO"
duration_days = 7
registration_open_hours_before = 168
identity_mode = "self_declaration"
prize_mode = "individual_only"
city_championship = "bragging_rights_only"
[storage]
database_path = "{db}"
backup_dir = "{backup}"
''', encoding="utf-8")


def test_test_mode_uses_separate_token_server_season_and_db(tmp_path, monkeypatch):
    prod = tmp_path / "config.toml"
    test = tmp_path / "config.test.toml"
    _write_toml(prod, 777, "data/live.sqlite3", "live2026", "data/live-backups")
    _write_toml(test, 888, "data/test/practice.sqlite3", "test2026", "data/test-backups")
    prod.write_text(prod.read_text().replace('starts_at_utc = "AUTO"',
                              'starts_at_utc = "2026-12-20T19:00:00+00:00"'))
    monkeypatch.setenv("SNOWFALL_CONFIG", str(prod))
    monkeypatch.setenv("SNOWFALL_TEST_CONFIG", str(test))
    monkeypatch.setenv("DISCORD_TOKEN", "live-secret")
    monkeypatch.setenv("DISCORD_TEST_TOKEN", "test-secret")
    settings = load_settings(test_mode=True)
    assert settings.is_test and settings.guild_id == 888
    assert settings.database_path != (tmp_path / "data/live.sqlite3")
    assert settings.backup_dir != (tmp_path / "data/live-backups")
    assert settings.starts_at_utc.tzinfo == timezone.utc
    monkeypatch.setenv("DISCORD_TEST_TOKEN", "live-secret")
    with pytest.raises(ValueError, match="DISCORD_TEST_TOKEN"):
        load_settings(test_mode=True)
    monkeypatch.setenv("DISCORD_TEST_TOKEN", "test-secret")
    _write_toml(test, 777, "data/test/practice.sqlite3", "test2026", "data/test-backups")
    with pytest.raises(ValueError, match="separate Discord test server"):
        load_settings(test_mode=True)
    _write_toml(test, 888, "data/live.sqlite3", "test2026", "data/test-backups")
    with pytest.raises(ValueError, match="database must differ"):
        load_settings(test_mode=True)
    _write_toml(test, 888, "data/test/practice.sqlite3", "live2026", "data/test-backups")
    with pytest.raises(ValueError, match="different test season_key"):
        load_settings(test_mode=True)


def test_seven_day_simulation_runs_in_temp_db_only():
    result = json.loads(run_simulation())
    assert result["days"] == 7
    assert result["pvp_throws"] == 126
    assert result["pve_attempts"] == 252
    assert result["city_day_snapshots"] == 42
    assert result["ledger_ok"] is True
    assert result["award_places"] == 3
