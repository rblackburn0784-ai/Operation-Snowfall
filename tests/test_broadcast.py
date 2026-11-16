"""Release 0.1.4a: announcement stages and read-only summary logic."""
from datetime import datetime, timedelta, timezone

import pytest

from snowfall.config import load_settings
from snowfall.db.store import Store
from snowfall.services.broadcast import (
    DAY_DETAILS,
    boss_defeated_announcement,
    boss_is_defeated,
    completed_announcement,
    daily_announcement,
    registration_announcement,
    waiting_announcement,
    world_snapshot,
)
from snowfall.services.world import WorldEngine, THEMES

START = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
SEASON = "christmas-broadcast-tests"


def test_all_seven_announcements_are_unique_and_include_specific_day_bonus():
    assert len(DAY_DETAILS) == len(THEMES) == 7
    texts = [daily_announcement(day) for day in range(1, 8)]
    assert len(set(texts)) == 7
    for day, text in enumerate(texts, 1):
        assert f"DAY {day}/7" in text
        assert THEMES[day - 1] in text
        assert "individual prizes only" in text
    for day, expected in ((2, "8 Snowflakes"), (3, "+10"),
                          (4, "non-Golden"), (5, "first boss attempt"),
                          (6, "+20"), (7, "Final 24")):
        assert expected.casefold() in texts[day - 1].casefold()
    assert "paused" in daily_announcement(1, paused=True).lower()
    with pytest.raises(ValueError):
        daily_announcement(0)
    with pytest.raises(ValueError):
        daily_announcement(8)


def test_registration_ready_end_and_defeat_messages():
    assert f"<t:{int(START.timestamp())}:F>" in registration_announcement(START, "Snowfall")
    assert "self-declared" in registration_announcement(START, "Snowfall")
    assert "host" in waiting_announcement("Snowfall").lower()
    assert "prizes" in completed_announcement("Snowfall").lower()
    assert "training echoes" in boss_defeated_announcement(3).lower()


def test_world_summary_and_boss_defeat_protected_from_disabled_boss(tmp_path):
    db = Store(tmp_path / "broadcast.sqlite3")
    db.initialize()
    db.ensure_season(SEASON, START)
    assert world_snapshot(db, SEASON, None)[0] == "Awaiting kickoff"
    assert not boss_is_defeated(db, SEASON, 1)
    db.register(SEASON, 42, "Rival42", "Chicago", START - timedelta(days=1))
    db.transition(SEASON, 123, "start", START, "test")
    WorldEngine(db).tick(SEASON, START)
    boss, forts = world_snapshot(db, SEASON, 1)
    assert "HP remaining" in boss
    assert forts.startswith("0/6")
    with db.connect() as con:
        con.execute("UPDATE world_days SET boss_hp=0 WHERE season_key=? AND day=1",
                    (SEASON,))
    assert boss_is_defeated(db, SEASON, 1)
    assert "echoes" in world_snapshot(db, SEASON, 1)[0]
    with db.connect() as con:
        con.execute("INSERT INTO world_settings (season_key,boss_enabled,boss_hp_override) "
                    "VALUES (?,0,NULL)", (SEASON,))
    assert not boss_is_defeated(db, SEASON, 1)
    assert "Disabled" in world_snapshot(db, SEASON, 1)[0]
    assert not boss_is_defeated(db, SEASON, 8)


def test_load_settings_two_distinct_channel_ids(tmp_path, monkeypatch):
    p = tmp_path / "config.toml"
    p.write_text('''[discord]
guild_id = 123456789
admin_user_ids = [33333333]
leaderboard_channel_id = 1571697566842748970
announcement_channel_id = 1571828901024374824
[event]
season_key = "test"
starts_at_utc = "2026-12-10T19:00:00+00:00"
identity_mode = "self_declaration"
prize_mode = "individual_only"
city_championship = "bragging_rights_only"
[storage]
database_path = "data/snow.sqlite3"
''', encoding="utf8")
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    settings = load_settings(p)
    assert settings.leaderboard_channel_id == 1571697566842748970
    assert settings.announcement_channel_id == 1571828901024374824
    p.write_text(p.read_text().replace('1571828901024374824', '1571697566842748970'))
    with pytest.raises(ValueError, match="two different channels"):
        load_settings(p)
    p.write_text(p.read_text().replace('announcement_channel_id = 1571697566842748970',
                                     'announcement_channel_id = -2'))
    with pytest.raises(ValueError, match="must be positive"):
        load_settings(p)


def test_stage_and_end_clocks_use_actual_start(tmp_path):
    db = Store(tmp_path / "times.sqlite3")
    db.initialize()
    db.ensure_season(SEASON, START)
    assert db.season(SEASON).phase(START - timedelta(days=8)) == "not_open"
    assert db.season(SEASON).phase(START - timedelta(days=7)) == "registration"
    assert db.season(SEASON).phase(START) == "ready"
    db.transition(SEASON, 1, "start", START, "launch")
    assert db.season(SEASON).day(START + timedelta(days=6)) == 7
    assert db.season(SEASON).phase(START + timedelta(days=7)) == "closed"
