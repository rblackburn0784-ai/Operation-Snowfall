"""v2.9.9b — full Frozen Safecracker, no Discord/event score mutations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import random

import pytest

from snowfall.db.store import Store
from snowfall.platform.safecracker_arcade import (
    DURATION_MS, SafecrackerEngine, install_safe_schema, proximity,
)
from snowfall.services.social_arcade import SocialArcadeEngine

SEASON = "safecracker-qa"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)


def when(ms: int) -> datetime:
    return START + timedelta(milliseconds=ms)


@pytest.fixture
def safe(tmp_path):
    store = Store(tmp_path / "safe.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    for user, name in ((101, "Safecracker"), (202, "Rival")):
        store.register(SEASON, user, name, "Chicago", START-timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Safecracker QA")
    with store.connect() as con:
        install_safe_schema(con)
        install_safe_schema(con)
    assert store.schema_version() == 11
    return SafecrackerEngine(store, SEASON, rng=random.Random(42)), store


def test_circular_distance_and_secret_is_server_only(safe):
    engine, _ = safe
    assert proximity(39, 0) == 1 and proximity(0, 39) == 1
    assert proximity(10, 30) == 20 and proximity(13, 13) == 0
    start = engine.start(101, now=START)
    assert start["status"] == "paused" and start["stage"] == 0
    assert start["dial"] == 0 and start["action_seq"] == 0
    assert start["turn_required"] == 40 and start["direction"] == 1
    assert start["combination"] is None and "code" not in start
    assert start["practice"] and not start["competitive"]
    assert start["score"] == 0
    assert engine.start(101, now=START)["session_id"] == start["session_id"]
    with pytest.raises(ValueError, match="unavailable"):
        engine.session(202, start["session_id"], now=START)
    with pytest.raises(ValueError, match="paused"):
        engine.move(101, start["session_id"], 0, "turn", 4, "prestart", now=when(100))


def test_three_tumbler_directions_open_and_score_only_in_practice(safe):
    engine, store = safe
    start = engine.start(101, now=START)
    sid = start["session_id"]
    with store.connect() as con:
        combo = __import__("json").loads(con.execute(
            "SELECT combination_json FROM web_arcade_safe_sessions "
            "WHERE session_id=?", (sid,)).fetchone()[0])
    assert len(combo) == 3 and all(0 <= number < 40 for number in combo)
    assert engine.control(101, sid, "resume", now=when(100))["status"] == "active"

    # One full revolution and precisely the desired number in each direction.
    dial = 0
    for stage, (direction, at) in enumerate(((1, 1800), (-1, 4500), (1, 7800))):
        number = combo[stage]
        distance = (number-dial) % 40 if direction == 1 else (dial-number) % 40
        ticks = direction * (40 + distance)
        turn = engine.move(
            101, sid, stage*2, "turn", ticks, f"turn-{stage}",
            now=when(at))
        assert turn["dial"] == number
        assert turn["stage"] == stage
        assert turn["signal"] == "click"
        assert turn["travel"] >= 40
        assert turn["combination"] is None
        seated = engine.move(
            101, sid, stage*2+1, "set", 0, f"set-{stage}",
            now=when(at+200))
        assert seated["stage"] == stage+1
        assert seated["mistakes"] == 0
        assert seated["attempts"] == stage+1
        dial = number

    assert seated["status"] == "finished" and seated["unlocked"]
    assert seated["combination"] == combo
    assert seated["score"] >= 85 and seated["score"] <= 100
    assert seated["result"].startswith("VAULT OPEN")
    assert engine.record(101, now=when(9000))["vaults_opened"] == 1
    assert engine.start(101, now=when(9000))["session_id"] != sid
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_safe_actions").fetchone()[0] == 6
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
    assert SocialArcadeEngine(store).lobby(SEASON, 101, when(9000)).record(
        "safe").attempts_today == 0


def test_wrong_direction_bad_set_and_exact_replay_are_handled(safe):
    engine, _ = safe
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    first = engine.move(101, sid, 0, "turn", -5, "wrong-way", now=when(1100))
    assert first["mistakes"] == 1 and first["travel"] == 0 and first["dial"] == 35
    assert first["action_seq"] == 1
    repeated = engine.move(101, sid, 0, "turn", -5, "wrong-way", now=when(1300))
    assert repeated["repeated"] and repeated["action_seq"] == 1
    with pytest.raises(ValueError, match="belongs"):
        engine.move(202, sid, 0, "turn", -5, "wrong-way", now=when(1800))
    with pytest.raises(ValueError, match="belongs"):
        engine.move(101, sid, 0, "turn", -6, "wrong-way", now=when(1800))
    bad = engine.move(101, sid, 1, "set", 0, "bad-set", now=when(2000))
    assert bad["mistakes"] == 2 and bad["attempts"] == 1
    assert bad["travel"] == 0 and bad["stage"] == 0
    assert bad["signal"] == "turn"
    assert bad["score"] == 0
    with pytest.raises(ValueError, match="Out-of-order"):
        engine.move(101, sid, 6, "turn", 4, "skip", now=when(3000))


def test_rate_limits_coordinates_boolean_actions_and_elapsed(safe):
    engine, _ = safe
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    with pytest.raises(ValueError, match="too fast"):
        engine.move(101, sid, 0, "turn", 80, "teleport", now=when(150))
    with pytest.raises(ValueError, match="Invalid"):
        engine.move(101, sid, 0, "turn", 81, "out-of-range", now=when(150))
    with pytest.raises(ValueError, match="Invalid"):
        engine.move(101, sid, 0, "turn", True, "boolean", now=when(150))
    with pytest.raises(ValueError, match="Invalid"):
        engine.move(101, sid, 0, "set", 1, "set-nonzero", now=when(150))
    assert engine.session(101, sid, now=when(1000))["action_seq"] == 0
    turn = engine.move(101, sid, 0, "turn", 8, "first-good", now=when(1000))
    assert turn["action_seq"] == 1 and turn["travel"] == 8
    assert turn["signal"] == "turn"


def test_pause_resume_replay_safe_controls_and_timeout(safe):
    engine, _ = safe
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    paused = engine.control(101, sid, "pause", now=when(5100))
    assert paused["status"] == "paused" and 4950 <= paused["elapsed_ms"] <= 5050
    assert engine.session(101, sid, now=when(50_000))["elapsed_ms"] == paused["elapsed_ms"]
    assert engine.control(101, sid, "pause", now=when(52_000))["status"] == "paused"
    engine.control(101, sid, "resume", now=when(60_000))
    expired = engine.session(101, sid, now=when(148_000))
    assert expired["elapsed_ms"] == DURATION_MS and expired["status"] == "finished"
    assert not expired["unlocked"] and expired["score"] == 0
    assert expired["combination"] is not None
    assert engine.control(101, sid, "finish", now=when(149_000))["status"] == "finished"
    assert engine.start(101, now=when(149_500))["session_id"] != sid


def test_concurrent_moves_only_one_writes(safe):
    engine, store = safe
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    def send(i):
        try:
            return engine.move(101, sid, 0, "turn", 5, f"parallel-{i}", now=when(1500))
        except ValueError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(send, range(2)))
    assert sum(isinstance(answer, dict) for answer in answers) == 1
    assert engine.session(101, sid, now=when(1600))["action_seq"] == 1
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_safe_actions").fetchone()[0] == 1


def test_safe_api_flag_auth_csrf_idempotent_calls(monkeypatch):
    from unittest.mock import Mock

    from fastapi.testclient import TestClient
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings

    ids, game = FakeIdentity(), Mock()
    game.safe_start.return_value = {"session_id": "a"*32}
    game.safe_move.return_value = {"dial": 8}
    with TestClient(create_app(fake_settings(), identity=ids, game=game),
                    base_url="https://snowfall.example") as client:
        assert client.post("/v1/game/arcade/safecracker/start").status_code == 401
        token, csrf = ids.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.post("/v1/game/arcade/safecracker/start").status_code == 403
        hdr = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/game/arcade/safecracker/start", headers=hdr).status_code == 503
        monkeypatch.setenv("SNOWFALL_ARCADE_V299B_ENABLED", "1")
        assert client.post("/v1/game/arcade/safecracker/start", headers=hdr).status_code == 200
        body = {"session_id": "a"*32, "action_seq": 0, "action": "turn", "ticks": 8}
        assert client.post("/v1/game/arcade/safecracker/move",
                           json=body, headers=hdr).status_code == 400
        hdr["Idempotency-Key"] = "safecracker-action-001"
        assert client.post("/v1/game/arcade/safecracker/move",
                           json=body, headers=hdr).status_code == 200
        assert game.safe_move.call_args.args[:5] == (101, "a"*32, 0, "turn", 8)
        # Score and hidden combination fields are deliberately not in the model.
        assert client.post("/v1/game/arcade/safecracker/move",
                           json={**body, "score": 1000, "combination": [1, 2, 3]},
                           headers=hdr).status_code == 200
        assert game.safe_move.call_args.args[:5] == (101, "a"*32, 0, "turn", 8)


def test_near_click_and_fine_reverse_preserve_progress(safe):
    engine, store = safe
    sid = engine.start(101, now=START)["session_id"]
    with store.connect() as con:
        con.execute("UPDATE web_arcade_safe_sessions SET combination_json=? WHERE session_id=?", ("[7, 10, 20]", sid))
    engine.control(101, sid, "resume", now=when(100))
    turn = engine.move(101, sid, 0, "turn", 49, "fine-turn", now=when(2000))
    assert turn["travel"] == 49
    reverse = engine.move(101, sid, 1, "turn", -1, "fine-reverse", now=when(2200))
    assert reverse["travel"] == 48 and reverse["signal"] == "click"
    assert reverse["mistakes"] == 0
    seated = engine.move(101, sid, 2, "set", 0, "fine-set", now=when(2400))
    assert seated["stage"] == 1
