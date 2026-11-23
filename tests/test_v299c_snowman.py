"""v2.9.9c — server-authored snowmen, replay-safe placements and QA isolation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import random

import pytest

from snowfall.db.store import Store
from snowfall.platform.snowman_arcade import (
    DURATION_MS, ROUNDS, SnowmanBuilderEngine,
    install_snowman_schema, make_blueprints,
)
from snowfall.services.social_arcade import SocialArcadeEngine

SEASON = "snowman-builder-qa"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)


def when(ms):
    return START + timedelta(milliseconds=ms)


@pytest.fixture
def workshop(tmp_path):
    store = Store(tmp_path / "snowmen.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    for user, name in ((101, "FrostyOne"), (202, "WinterRival")):
        store.register(SEASON, user, name, "Chicago", START-timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Builder QA")
    with store.connect() as con:
        install_snowman_schema(con)
        install_snowman_schema(con)
    assert store.schema_version() == 11
    return SnowmanBuilderEngine(store, SEASON, rng=random.Random(42)), store


def test_blueprints_three_difficulties_real_geometry_and_decoys(workshop):
    engine, _ = workshop
    plans = make_blueprints(random.Random(42))
    assert len(plans) == 3
    assert [p["required"] for p in plans] == [4, 7, 9]
    assert sum(len(p["slots"]) for p in plans) == 20
    assert [sum(p["decoy"] for p in plan["parts"]) for plan in plans] == [0, 1, 2]
    for plan in plans:
        ids = {p["id"] for p in plan["parts"]}
        assert len(ids) == len(plan["parts"])
        assert {slot["id"] for slot in plan["slots"]}.issubset(ids)
        assert all(65 < slot["x"] < 450 and 70 <= slot["y"] <= 300
                   and 17 <= slot["radius"] <= 38 for slot in plan["slots"])
    run = engine.start(101, now=START)
    assert run["stage"] == 0 and run["round"] == 1
    assert run["total_parts"] == 20 and run["status"] == "paused"
    assert run["score"] == 0 and run["action_seq"] == 0
    assert run["practice"] and not run["competitive"]
    assert engine.start(101, now=START)["session_id"] == run["session_id"]
    with pytest.raises(ValueError, match="unavailable"):
        engine.session(202, run["session_id"], now=START)


def test_all_twenty_pieces_complete_three_rounds_with_one_hundred_points(workshop):
    engine, store = workshop
    run = engine.start(101, now=START)
    sid = run["session_id"]
    run = engine.control(101, sid, "resume", now=when(100))
    assert run["status"] == "active"
    seq = 0
    for stage, (_, expected_types, _) in enumerate(ROUNDS):
        assert run["stage"] == stage
        assert {p["id"] for p in run["blueprint"]["parts"]
                if not p["decoy"]} == set(expected_types)
        for slot in run["blueprint"]["slots"]:
            run = engine.place(
                101, sid, seq, slot["id"], slot["x"], slot["y"],
                f"builder-valid-{seq:03d}", now=when(800 + seq * 450))
            seq += 1
            assert run["mistakes"] == 0
            assert run["placed_total"] == seq
        assert run["stage"] == stage+1
    assert seq == 20
    assert run["status"] == "finished" and run["complete"]
    assert run["score"] == 100
    assert run["result"].startswith("FROSTY MASTERPIECE")
    record = engine.record(101, now=when(12_000))
    assert record["personal_best"] == 100 and record["completed_builds"] == 1
    assert engine.start(101, now=when(12_100))["session_id"] != sid
    with store.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM web_arcade_snowman_actions").fetchone()[0] == 20
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
    assert SocialArcadeEngine(store).lobby(SEASON, 101, when(12_000)).record(
        "snowman").attempts_today == 0


def test_wrong_spots_mistakes_and_replayed_actions(workshop):
    engine, store = workshop
    run = engine.start(101, now=START)
    sid = run["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    first = run["blueprint"]["slots"][0]
    wrong = engine.place(101, sid, 0, first["id"], 15, 15,
                         "builder-wrong-000", now=when(800))
    assert wrong["last_action"]["outcome"] == "wrong_spot"
    assert wrong["mistakes"] == 1 and wrong["placed_total"] == 0
    assert wrong["score"] == 0 and wrong["action_seq"] == 1
    retry = engine.place(101, sid, 0, first["id"], 15, 15,
                         "builder-wrong-000", now=when(1200))
    assert retry["repeated"] and retry["action_seq"] == 1
    with pytest.raises(ValueError, match="belongs"):
        engine.place(202, sid, 0, first["id"], 15, 15,
                     "builder-wrong-000", now=when(1400))
    with pytest.raises(ValueError, match="belongs"):
        engine.place(101, sid, 0, first["id"], 16, 15,
                     "builder-wrong-000", now=when(1500))
    with pytest.raises(ValueError, match="Out-of-order"):
        engine.place(101, sid, 9, first["id"], 200, 230,
                     "skip-00001", now=when(1600))
    placed = engine.place(101, sid, 1, first["id"], first["x"], first["y"],
                          "builder-fix-001", now=when(1900))
    assert placed["placed_total"] == 1 and placed["mistakes"] == 1
    with pytest.raises(ValueError, match="already"):
        engine.place(101, sid, 2, first["id"], first["x"], first["y"],
                     "duplicate-part", now=when(2300))
    assert engine.session(101, sid, now=when(2400))["action_seq"] == 2
    with store.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM web_arcade_snowman_actions").fetchone()[0] == 2


def test_decoy_penalty_and_bounds_belong_to_current_blueprint(workshop):
    engine, _ = workshop
    run = engine.start(101, now=START)
    sid = run["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    with pytest.raises(ValueError, match="Invalid"):
        engine.place(101, sid, 0, "base", True, 120, "bool-x", now=when(1000))
    with pytest.raises(ValueError, match="Invalid"):
        engine.place(101, sid, 0, "base", -10, 120, "negative-x", now=when(1000))
    with pytest.raises(ValueError, match="does not belong"):
        engine.place(101, sid, 0, "beachball", 300, 200,
                     "other-round-piece", now=when(1000))
    for seq, slot in enumerate(run["blueprint"]["slots"]):
        run = engine.place(101, sid, seq, slot["id"], slot["x"], slot["y"],
                           f"builder-stage1-{seq}", now=when(1300 + seq*450))
    assert run["stage"] == 1
    decoy = next(p for p in run["blueprint"]["parts"] if p["decoy"])
    wrong = engine.place(101, sid, 4, decoy["id"], 280, 210,
                         "builder-decoy", now=when(3300))
    assert wrong["last_action"]["outcome"] == "decoy"
    assert wrong["mistakes"] == 1
    assert wrong["placed_total"] == 4
    with pytest.raises(ValueError, match="does not belong"):
        engine.place(101, sid, 5, "beachball", 280, 210,
                     "only-stage3", now=when(3600))


def test_pause_resume_timer_and_expiration(workshop):
    engine, _ = workshop
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(200))
    paused = engine.control(101, sid, "pause", now=when(5200))
    assert paused["status"] == "paused" and paused["elapsed_ms"] == 5000
    assert engine.session(101, sid, now=when(60_000))["elapsed_ms"] == 5000
    assert engine.control(101, sid, "pause", now=when(80_000))["status"] == "paused"
    engine.control(101, sid, "resume", now=when(90_000))
    expired = engine.session(101, sid, now=when(240_000))
    assert expired["status"] == "finished" and expired["elapsed_ms"] == DURATION_MS
    assert expired["score"] == 0 and not expired["complete"]
    with pytest.raises(ValueError, match="paused, finished"):
        engine.place(101, sid, 0, "base", 250, 270, "expired-move", now=when(245_000))
    assert engine.start(101, now=when(245_000))["session_id"] != sid


def test_fast_double_drop_and_concurrent_writes_are_rejected(workshop):
    engine, store = workshop
    run = engine.start(101, now=START)
    sid = run["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    slots = run["blueprint"]["slots"]
    first, second = slots[0], slots[1]
    def send(i):
        try:
            return engine.place(101, sid, 0, first["id"], first["x"], first["y"],
                                f"parallel-builder-{i}", now=when(900))
        except ValueError as e:
            return e
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert sum(isinstance(v, dict) for v in results) == 1
    with pytest.raises(ValueError, match="Wait"):
        engine.place(101, sid, 1, second["id"], second["x"], second["y"],
                     "rapid-place", now=when(960))
    assert engine.session(101, sid, now=when(1300))["action_seq"] == 1
    with store.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM web_arcade_snowman_actions").fetchone()[0] == 1


def test_api_auth_csrf_default_off_and_ignores_browser_scores(monkeypatch):
    from unittest.mock import Mock

    from fastapi.testclient import TestClient
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings

    identities, shared = FakeIdentity(), Mock()
    shared.snowman_start.return_value = {"session_id": "a"*32}
    shared.snowman_place.return_value = {"score": 4}
    with TestClient(create_app(fake_settings(), identity=identities, game=shared),
                    base_url="https://snowfall.example") as client:
        assert client.post("/v1/game/arcade/snowman/start").status_code == 401
        token, csrf = identities.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.post("/v1/game/arcade/snowman/start").status_code == 403
        headers = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/game/arcade/snowman/start",
                           headers=headers).status_code == 503
        monkeypatch.setenv("SNOWFALL_ARCADE_V299C_ENABLED", "1")
        assert client.post("/v1/game/arcade/snowman/start",
                           headers=headers).status_code == 200
        body = {"session_id": "a"*32, "action_seq": 0,
                "piece_id": "base", "x": 250, "y": 270}
        assert client.post("/v1/game/arcade/snowman/place", json=body,
                           headers=headers).status_code == 400
        headers["Idempotency-Key"] = "snowman-accepted-action-001"
        assert client.post("/v1/game/arcade/snowman/place", json=body,
                           headers=headers).status_code == 200
        assert shared.snowman_place.call_args.args[:6] == (
            101, "a"*32, 0, "base", 250, 270)
        assert client.post("/v1/game/arcade/snowman/place",
                           json={**body, "score": 1000, "bonus": 9999},
                           headers=headers).status_code == 200
        assert shared.snowman_place.call_args.args[:6] == (
            101, "a"*32, 0, "base", 250, 270)
