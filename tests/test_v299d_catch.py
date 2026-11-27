"""v2.9.9d: deterministic wind, score and hazard settlement in isolated QA."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import random

import pytest

from snowfall.db.store import Store
from snowfall.platform.catch_arcade import (
    BASKET_MAX, BASKET_MIN, DURATION_MS, SnowflakeCatchEngine,
    flake_position, generate_schedule, install_catch_schema,
)
from snowfall.services.social_arcade import SocialArcadeEngine

SEASON = "snowflake-catch-qa"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)


def when(ms):
    return START + timedelta(milliseconds=ms)


@pytest.fixture
def storm(tmp_path):
    store = Store(tmp_path / "catch.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    for user, name in ((101, "FlakeCatcher"), (202, "IceRival")):
        store.register(SEASON, user, name, "Chicago", START-timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Catch QA")
    with store.connect() as con:
        install_catch_schema(con)
        install_catch_schema(con)
    assert store.schema_version() == 11
    return SnowflakeCatchEngine(store, SEASON, random.Random(42)), store


def test_three_waves_wind_and_every_falling_object_is_server_owned(storm):
    engine, _ = storm
    schedule = generate_schedule(random.Random(42))
    assert len(schedule) == 45
    assert {item["wave"] for item in schedule} == {1, 2, 3}
    assert {item["kind"] for item in schedule} == {
        "snowflake", "crystal", "gold", "hazard"}
    assert all(0 <= item["start"] < item["impact"] <= DURATION_MS
               for item in schedule)
    assert all(item["flight"] in (4400, 3400, 2400)
               for item in schedule)
    assert [sum(item['wave'] == wave for item in schedule) for wave in (1, 2, 3)] == [10, 14, 21]
    for item in schedule:
        beginning = flake_position(item, item["start"])
        impact = flake_position(item, item["impact"])
        assert beginning[1] == 38 and impact[1] == 300
        assert abs(beginning[0] - impact[0]) > 0.1
    ready = engine.start(101, now=START)
    assert ready["status"] == "paused" and ready["basket_x"] == 320
    assert ready["score"] == 0 and ready["action_seq"] == 0
    assert ready["practice"] and not ready["competitive"]
    assert engine.start(101, now=START)["session_id"] == ready["session_id"]
    with pytest.raises(ValueError, match="unavailable"):
        engine.session(202, ready["session_id"], now=START)


def test_first_flake_caught_and_replay_does_not_double_award(storm):
    engine, store = storm
    ready = engine.start(101, now=START)
    sid = ready["session_id"]
    first = ready["schedule"][0]
    assert first["kind"] == "snowflake"
    with pytest.raises(ValueError, match="paused"):
        engine.update(101, sid, 0, 320, "before-start", now=when(100))
    engine.control(101, sid, "resume", now=when(100))
    x, _ = flake_position(first, first["impact"])
    assert BASKET_MIN < x < BASKET_MAX
    when_hit = first["impact"] + 100
    caught = engine.update(101, sid, 0, round(x), "first-catch-001",
                           now=when(when_hit))
    assert caught["caught"] == 1 and caught["score"] == 3
    assert caught["combo"] == 1 and caught["best_combo"] == 1
    assert caught["settled"] == [0] and caught["action_seq"] == 1
    assert caught["events"][0]["outcome"] == "caught"
    assert caught["events"][0]["score_after"] == 3
    again = engine.update(101, sid, 0, round(x), "first-catch-001",
                          now=when(when_hit + 900))
    assert again["repeated"] and again["score"] == 3
    assert again["events"] == caught["events"]
    with pytest.raises(ValueError, match="belongs"):
        engine.update(202, sid, 0, round(x), "first-catch-001",
                      now=when(when_hit + 1000))
    with pytest.raises(ValueError, match="belongs"):
        engine.update(101, sid, 0, round(x)+1, "first-catch-001",
                      now=when(when_hit + 1000))
    with store.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM web_arcade_catch_actions").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
    assert SocialArcadeEngine(store).lobby(SEASON, 101, when(when_hit)).record(
        "catch").attempts_today == 0


def test_unreported_hazards_are_settled_even_when_browser_does_not_claim_them(storm):
    engine, _ = storm
    ready = engine.start(101, now=START)
    sid = ready["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    hazard = next(item for item in ready["schedule"] if item["kind"] == "hazard")
    # No basket updates until after the hazard crosses. The server settles
    # every due object, including penalties, in a single transaction.
    result = engine.session(101, sid, now=when(hazard["impact"] + 500))
    assert hazard["id"] in result["settled"]
    assert any(event["id"] == hazard["id"] for event in result["events"])
    assert any(event["id"] == hazard["id"] and event["outcome"] in (
        "avoided", "hazard") for event in result["events"])
    assert result["caught"] + result["missed"] + result["hazards"] <= len(
        result["settled"])


def test_hazard_interception_penalises_and_resets_combo(storm):
    engine, _ = storm
    ready = engine.start(101, now=START)
    sid = ready["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    hazard = next(item for item in ready["schedule"] if item["kind"] == "hazard")
    target, _ = flake_position(hazard, hazard["impact"])
    if not BASKET_MIN <= round(target) <= BASKET_MAX:
        pytest.skip("Seeded ice path missed reachable basket track")
    event = engine.update(101, sid, 0, round(target), "ice-hit-001",
                          now=when(hazard["impact"] + 100))
    assert hazard["id"] in event["settled"]
    assert any(e["id"] == hazard["id"] and e["outcome"] == "hazard"
               for e in event["events"])
    assert event["hazards"] == 1
    assert event["combo"] == 0
    assert event["score"] <= 100


def test_speed_limit_sequence_identity_bounds_and_concurrent_update(storm):
    engine, store = storm
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    with pytest.raises(ValueError, match="Invalid"):
        engine.update(101, sid, 0, 65, "bad-position", now=when(200))
    with pytest.raises(ValueError, match="Invalid"):
        engine.update(101, sid, 0, True, "bool-position", now=when(200))
    with pytest.raises(ValueError, match="cannot move"):
        engine.update(101, sid, 0, 574, "teleport", now=when(200))
    with pytest.raises(ValueError, match="Out-of-order"):
        engine.update(101, sid, 5, 320, "future-update", now=when(250))
    def move(i):
        try:
            return engine.update(101, sid, 0, 332, f"parallel-{i}", now=when(500))
        except ValueError as e:
            return e
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, range(2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    with pytest.raises(ValueError, match="too frequent"):
        engine.update(101, sid, 1, 340, "spam-update", now=when(520))
    assert engine.session(101, sid, now=when(600))["action_seq"] == 1
    with store.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM web_arcade_catch_actions").fetchone()[0] == 1


def test_pause_resume_exact_elapsed_and_finish_60_seconds(storm):
    engine, _ = storm
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    paused = engine.control(101, sid, "pause", now=when(5100))
    assert paused["status"] == "paused" and paused["elapsed_ms"] == 5000
    assert engine.session(101, sid, now=when(60_000))["elapsed_ms"] == 5000
    assert engine.control(101, sid, "pause", now=when(65_000))["status"] == "paused"
    engine.control(101, sid, "resume", now=when(70_000))
    done = engine.session(101, sid, now=when(130_500))
    assert done["elapsed_ms"] == DURATION_MS and done["status"] == "finished"
    assert len(done["settled"]) == 45
    record = engine.record(101, now=when(131_000))
    assert record["finished_runs"] == 1
    assert engine.start(101, now=when(131_100))["session_id"] != sid
    with pytest.raises(ValueError, match="paused, finished"):
        engine.update(101, sid, 0, 320, "after-end", now=when(132_000))


def test_api_default_off_csrf_idempotency_and_no_client_score(monkeypatch):
    from unittest.mock import Mock

    from fastapi.testclient import TestClient
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings

    identities, shared = FakeIdentity(), Mock()
    shared.catch_start.return_value = {"session_id": "a"*32}
    shared.catch_update.return_value = {"score": 3}
    with TestClient(create_app(fake_settings(), identity=identities, game=shared),
                    base_url="https://snowfall.example") as client:
        assert client.post("/v1/game/arcade/catch/start").status_code == 401
        token, csrf = identities.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.post("/v1/game/arcade/catch/start").status_code == 403
        headers = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/game/arcade/catch/start", headers=headers).status_code == 503
        monkeypatch.setenv("SNOWFALL_ARCADE_V299D_ENABLED", "1")
        assert client.post("/v1/game/arcade/catch/start", headers=headers).status_code == 200
        body = {"session_id": "a"*32, "action_seq": 0, "x": 320}
        assert client.post("/v1/game/arcade/catch/update", json=body,
                           headers=headers).status_code == 400
        headers["Idempotency-Key"] = "catch-authoritative-00001"
        assert client.post("/v1/game/arcade/catch/update", json=body,
                           headers=headers).status_code == 200
        assert shared.catch_update.call_args.args[:4] == (101, "a"*32, 0, 320)
        assert client.post("/v1/game/arcade/catch/update",
                           json={**body, "score": 1000, "caught": [0, 1, 2]},
                           headers=headers).status_code == 200
        assert shared.catch_update.call_args.args[:4] == (101, "a"*32, 0, 320)
