"""v2.9.9 web-only arcade foundations and resumable practice isolation."""
from datetime import datetime, timedelta, timezone
import pytest

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.platform.interactive_arcade import (
    EMPTY_STATE, InteractiveArcadePractice, PRACTICE_DURATIONS,
    install_practice_schema,
)
from snowfall.services.social_arcade import SocialArcadeEngine

START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
SEASON = "interactive-test"


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "snowfall.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    for uid in (101, 202):
        store.register(SEASON, uid, "Tester"+str(uid), "Chicago", START-timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Practice QA")
    with store.connect() as con:
        install_practice_schema(con)
    assert store.schema_version() == 11  # No core migration / Discord schema drift.
    return SharedGame(store, SEASON)


def test_all_five_modes_have_separate_resumable_sessions(game):
    service = InteractiveArcadePractice(game.store, SEASON)
    sessions = {}
    for mode, duration in PRACTICE_DURATIONS.items():
        current = service.start(101, mode, now=START)
        assert current["mode"] == mode and current["duration_ms"] == duration
        assert current["practice"] and not current["competitive"]
        assert current["practice_score"] == 0
        assert current["state"] == EMPTY_STATE
        assert service.start(101, mode, now=START)["session_id"] == current["session_id"]
        sessions[mode] = current["session_id"]
    assert len(set(sessions.values())) == 5
    for mode, sid in sessions.items():
        assert service.session(101, sid, now=START)["mode"] == mode
        with pytest.raises(ValueError, match="unavailable"):
            service.session(202, sid, now=START)
    with game.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0


def test_checkpoint_replay_resume_finish_and_unlimited_restarts(game):
    engine = InteractiveArcadePractice(game.store, SEASON)
    first = engine.start(101, "gallery", now=START)
    sid = first["session_id"]
    state = {**EMPTY_STATE, "elapsed_ms": 3000, "hits": 2, "misses": 1,
             "progress": 1, "position": .33, "angle": 45}
    saved = game.arcade_practice_save(101, sid, 0, state, now=START+timedelta(seconds=4))
    assert saved["revision"] == 1 and saved["state"] == state
    assert saved["practice_score"] == 18 and saved["status"] == "active"
    assert engine.session(101, sid, now=START+timedelta(seconds=5)) == saved
    assert engine.save(101, sid, 0, state, now=START+timedelta(seconds=5)) == saved
    with pytest.raises(ValueError, match="out of date"):
        engine.save(101, sid, 0, {**state, "hits": 3},
                    now=START+timedelta(seconds=5))
    with pytest.raises(ValueError, match="backwards"):
        engine.save(101, sid, 1, {**state, "elapsed_ms": 2000},
                    now=START+timedelta(seconds=5))
    done = engine.save(101, sid, 1, {**state, "elapsed_ms": 5000}, finish=True,
                       now=START+timedelta(seconds=8))
    assert done["status"] == "finished" and done["revision"] == 2
    assert engine.save(101, sid, 1, done["state"], finish=True,
                       now=START+timedelta(seconds=8)) == done
    assert engine.start(101, "gallery", now=START+timedelta(seconds=9))[
        "session_id"] != sid
    assert SocialArcadeEngine(game.store).lobby(SEASON, 101, START).record(
        "gallery").attempts_today == 0


def test_invalid_checkpoints_blocked_without_any_official_points(game):
    engine = InteractiveArcadePractice(game.store, SEASON)
    run = engine.start(101, "safe", now=START)
    sid = run["session_id"]
    samples = [
        {**EMPTY_STATE, "elapsed_ms": 50000},  # impossible wall clock
        {**EMPTY_STATE, "elapsed_ms": 1000, "hits": 300},  # impossible rate
        {**EMPTY_STATE, "position": 1.5},
        {**EMPTY_STATE, "hits": True},
        {**EMPTY_STATE, "progress": 31},
        {"score": 100},  # no browser-chosen score field
    ]
    for state in samples:
        with pytest.raises(ValueError):
            engine.save(101, sid, 0, state, now=START+timedelta(seconds=2))
    with pytest.raises(ValueError, match="unavailable"):
        engine.save(202, sid, 0, EMPTY_STATE, now=START)
    with game.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM social_arcade_stamps").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM social_arcade_turns").fetchone()[0] == 0
        assert con.execute("SELECT revision FROM web_arcade_practice_sessions "
                           "WHERE session_id=?", (sid,)).fetchone()[0] == 0


def test_original_discord_arcade_still_operates_and_has_daily_cap(game):
    engine = SocialArcadeEngine(game.store)
    legacy = engine.begin(SEASON, 101, "gallery", START)
    assert legacy.step == 0 and legacy.current.choices
    InteractiveArcadePractice(game.store, SEASON).start(101, "gallery", now=START)
    lobby = engine.lobby(SEASON, 101, START)
    assert lobby.record("gallery").attempts_today == 1
    assert lobby.record("gallery").active_id == legacy.session_id
