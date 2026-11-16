"""v0.1.6a: single-app practice mode, every day and destructive safety gates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3

import pytest

from snowfall.config import Settings
from snowfall.db.store import Store
from snowfall.practice import (
    PracticeManager, PracticeError, ScopedSettings, ScopedStore, pin,
    practice_expired,
)
from snowfall.services.broadcast import DAY_DETAILS
from snowfall.services.world import WorldEngine, THEMES
from snowfall.services.combat import CombatEngine

NOW = datetime(2026, 11, 16, 15, 28, tzinfo=timezone.utc)
PROD_START = NOW + timedelta(days=25)


def fresh(tmp_path):
    live = Store(tmp_path / "official.sqlite3")
    live.initialize()
    live.ensure_season("christmas-2026", PROD_START)
    settings = Settings(
        token="same_bot_token", guild_id=123, admin_user_ids=frozenset({22}),
        season_key="christmas-2026", event_name="Operation Snowfall",
        starts_at_utc=PROD_START, database_path=live.path,
        leaderboard_channel_id=444, announcement_channel_id=555,
    )
    return PracticeManager(settings, live)


def hash_db(store):
    with store.connect() as db:
        tables = ("players", "score_ledger", "season_state", "published_messages",
                  "launch_approvals", "prize_awards", "world_days", "combat_events")
        content = []
        for table in tables:
            content.append((table, [tuple(r) for r in db.execute(
                f"SELECT * FROM {table} ORDER BY rowid")]))
    return hashlib.sha256(repr(content).encode()).hexdigest()


@pytest.mark.parametrize("day", range(1, 8))
def test_each_of_seven_days_is_playable_with_correct_theme_and_isolated(tmp_path, day):
    manager = fresh(tmp_path)
    before = hash_db(manager.live_store)
    session = manager.start(day, 777, 22, NOW)
    assert session.settings.token == manager.live_settings.token
    assert session.settings.guild_id == manager.live_settings.guild_id
    assert session.settings.season_key != manager.live_settings.season_key
    assert session.store.path != manager.live_store.path
    assert session.settings.announcement_channel_id == 0
    assert session.settings.leaderboard_channel_id == 0
    assert session.settings.mode == "practice" and session.settings.is_test
    season = session.store.season(session.settings.season_key)
    assert season.phase(NOW) == "live" and season.day(NOW) == day
    assert manager.snapshot(NOW)["theme"] == THEMES[day-1]
    assert manager.snapshot(NOW)["bonus"] == DAY_DETAILS[day-1][1]
    player = session.store.register(session.settings.season_key, 27,
                                    "WinterTester", "Chicago", NOW)
    assert player.mr_username == "WinterTester"
    status = WorldEngine(session.store).status(session.settings.season_key, 27, NOW)
    assert status.day == day and status.theme == THEMES[day-1]
    with session.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM world_sieges WHERE season_key=? AND day=?",
                           (session.settings.season_key, day)).fetchone()[0] == 6
        assert con.execute("SELECT COUNT(*) FROM world_days WHERE season_key=? AND day=?",
                           (session.settings.season_key, day)).fetchone()[0] == 1
    assert hash_db(manager.live_store) == before
    temp = session.store.path
    assert manager.end() is None
    assert not temp.exists()
    assert hash_db(manager.live_store) == before


def test_real_commands_and_prompts_route_by_selected_channel_and_thread_context(tmp_path):
    manager = fresh(tmp_path)
    routed_settings, routed_store = ScopedSettings(manager), ScopedStore(manager)
    assert routed_settings.season_key == "christmas-2026"
    active = manager.start(4, 777, 22, NOW)
    assert not manager.for_interaction(666)
    assert routed_store.resolve() is manager.live_store
    assert manager.for_interaction(777)
    assert routed_store.resolve() is active.store
    assert routed_settings.season_key == active.settings.season_key
    pinned_settings, pinned_store = pin(routed_settings, routed_store)
    assert pinned_settings is active.settings and pinned_store is active.store
    # Context is copied by asyncio.to_thread in the Discord handlers.
    with ThreadPoolExecutor(max_workers=1) as pool:
        # Direct copy_context makes this deterministic without a Discord gateway.
        from contextvars import copy_context
        ctx = copy_context()
        assert pool.submit(ctx.run, lambda: routed_store.resolve()).result() is active.store
    assert manager.for_interaction(666) is False
    assert routed_settings.season_key == manager.live_settings.season_key
    manager.end()
    assert practice_expired(pinned_settings, pinned_store)
    with pytest.raises(PracticeError, match="ended"):
        pinned_store.registrations(pinned_settings.season_key)
    assert routed_store.resolve() is manager.live_store


def test_day_switch_retains_only_test_registration_and_resets_progress(tmp_path):
    manager = fresh(tmp_path)
    real_before = hash_db(manager.live_store)
    old = manager.start(1, 777, 22, NOW)
    old.store.register(old.settings.season_key, 101, "OldSnow", "Chicago", NOW)
    old.store.register(old.settings.season_key, 102, "YoungSnow", "Detroit", NOW)
    # Build a real PvE event on the disposable store, never on production.
    combat = CombatEngine(old.store)
    combat.ready(old.settings.season_key, 101, NOW)
    WorldEngine(old.store).attack(old.settings.season_key, 101, "boss", "test-pve-1", NOW)
    assert old.store.path.exists()
    next_day = manager.change_day(5, 22, NOW + timedelta(minutes=1))
    assert next_day.day == 5
    assert next_day.store.path != old.store.path
    assert not old.store.path.exists()
    assert not old.store.active
    players = next_day.store.registrations(next_day.settings.season_key)
    assert {p.mr_username for p in players} == {"OldSnow", "YoungSnow"}
    with next_day.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM pve_events").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
    assert hash_db(manager.live_store) == real_before
    manager.end()


def test_archive_is_verified_and_stale_sessions_cannot_recreate_db(tmp_path):
    manager = fresh(tmp_path)
    session = manager.start(7, 777, 22, NOW)
    session.store.register(session.settings.season_key, 101, "SnowWinner", "Chicago", NOW)
    path = session.store.path
    archived = manager.end(archive=True)
    assert archived is not None and archived.exists()
    assert archived.resolve().parent == manager.archive_dir.resolve()
    assert not path.exists()
    with sqlite3.connect(archived) as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1
    with pytest.raises(PracticeError):
        with session.store.connect():
            pass
    assert not path.exists()


def test_refuses_duplicate_start_and_live_channel_ids(tmp_path):
    manager = fresh(tmp_path)
    with pytest.raises(PracticeError, match="separate test channel"):
        manager.start(1, 444, 22, NOW)
    with pytest.raises(PracticeError, match="separate test channel"):
        manager.start(1, 555, 22, NOW)
    with pytest.raises(PracticeError, match="1 to 7"):
        manager.start(8, 777, 22, NOW)
    manager.start(1, 777, 22, NOW)
    with pytest.raises(PracticeError, match="already running"):
        manager.start(2, 777, 22, NOW)
    manager.end()
    with pytest.raises(PracticeError, match="No active test"):
        manager.change_day(3, 22, NOW)



def test_production_really_live_blocks_testing(tmp_path):
    manager = fresh(tmp_path)
    manager.live_store.transition("christmas-2026", 22, "start", PROD_START, "start")
    with pytest.raises(PracticeError, match="blocked after live kickoff"):
        manager.start(1, 777, 22, PROD_START)
    assert manager.session is None


def test_restart_removes_orphaned_db_without_touching_live_or_archives(tmp_path):
    manager = fresh(tmp_path)
    live_before = hash_db(manager.live_store)
    session = manager.start(3, 777, 22, NOW)
    path = session.store.path
    orphan = PracticeManager(manager.live_settings, manager.live_store)
    assert orphan.clean_orphans() == 1
    assert not path.exists()
    assert hash_db(manager.live_store) == live_before


def test_test_stop_cannot_change_live_only_prize_approval(tmp_path):
    manager = fresh(tmp_path)
    manager.start(2, 777, 22, NOW)
    assert manager.live_store.audit_count(manager.live_settings.season_key) == 0
    manager.end()
    assert manager.live_store.audit_count(manager.live_settings.season_key) == 0
