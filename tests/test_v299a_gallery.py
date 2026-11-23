"""v2.9.9a: real 45-second gallery, ownership, timing, honest scores, replay safety."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import math
import random

import pytest

from snowfall.db.store import Store
from snowfall.platform.gallery_arcade import (
    AMMO, DURATION_MS, GalleryEngine, find_target, install_gallery_schema,
    schedule_targets, target_position,
)
from snowfall.services.social_arcade import SocialArcadeEngine

SEASON = "target-gallery-qa"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)


@pytest.fixture
def gallery(tmp_path):
    store = Store(tmp_path / "gallery.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    store.register(SEASON, 101, "Marksman", "Chicago", START-timedelta(days=1))
    store.register(SEASON, 202, "Rival", "Detroit", START-timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Gallery staging")
    with store.connect() as con:
        install_gallery_schema(con)
        install_gallery_schema(con)  # additive installer can be rerun safely
    assert store.schema_version() == 11
    return GalleryEngine(store, SEASON), store


def when(ms: int) -> datetime:
    return START + timedelta(milliseconds=ms)


def target_shot(engine, user, snap, target, when_elapsed):
    x, y = target_position(target, when_elapsed)
    return engine.shoot(
        user, snap["session_id"], snap["shots_used"], round(x), round(y),
        f"gallery-{snap['session_id']}-{snap['shots_used']}",
        now=when(200 + when_elapsed))


def test_schedule_has_three_waves_target_types_and_shared_collision_math():
    schedule = schedule_targets(random.Random(42))
    assert len(schedule) == 43
    assert {t["kind"] for t in schedule} == {"normal", "gold", "decoy"}
    assert {t["wave"] for t in schedule} == {1, 2, 3}
    assert all(0 <= t["start"] < DURATION_MS and 0 < t["life"] < DURATION_MS
               for t in schedule)
    for t in schedule:
        x, y = target_position(t, t["start"] + 100)
        assert 15 < x < 630 and 70 < y < 325
        assert find_target([t], set(), t["start"] + 100, round(x), round(y)) == t
        assert find_target([t], {t["id"]}, t["start"] + 100, round(x), round(y)) is None
        assert math.isfinite(x)


def test_gallery_first_hit_replay_and_isolation(gallery):
    engine, store = gallery
    ready = engine.start(101, now=START)
    assert ready["status"] == "paused" and ready["ammo"] == AMMO
    assert ready["score"] == 0 and not ready["competitive"]
    assert ready["day"] == 1 and len(ready["schedule"]) == 43
    assert engine.start(101, now=START)["session_id"] == ready["session_id"]
    with pytest.raises(ValueError, match="unavailable"):
        engine.session(202, ready["session_id"], now=START)
    with pytest.raises(ValueError, match="paused"):
        engine.shoot(101, ready["session_id"], 0, 300, 200, "before-start", now=when(100))
    active = engine.control(101, ready["session_id"], "resume", now=when(200))
    assert active["status"] == "active"
    first = active["schedule"][0]
    hit = target_shot(engine, 101, active, first, 520)
    assert hit["last_event"]["target_id"] == first["id"]
    assert hit["last_event"]["outcome"] == "hit"
    assert hit["score"] == 7 and hit["hits"] == 1
    assert hit["ammo"] == AMMO - 1 and hit["accuracy"] == 100
    idempotency_id = f"gallery-{hit['session_id']}-0"
    x, y = target_position(first, 520)
    repeated = engine.shoot(101, hit["session_id"], 0, round(x), round(y),
                             idempotency_id, now=when(2000))
    assert repeated["repeated"] and repeated["shots_used"] == 1
    with pytest.raises(ValueError, match="idempotency"):
        engine.shoot(202, hit["session_id"], 0, round(x), round(y),
                     idempotency_id, now=when(2100))
    with pytest.raises(ValueError, match="idempotency"):
        engine.shoot(101, hit["session_id"], 0, round(x)+20, round(y),
                     idempotency_id, now=when(2100))
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_gallery_shots").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0


def test_pause_resume_does_not_advance_timer_and_audits_misses(gallery):
    engine, _ = gallery
    ready = engine.start(101, now=START)
    sid = ready["session_id"]
    engine.control(101, sid, "resume", now=when(200))
    paused = engine.control(101, sid, "pause", now=when(5300))
    assert paused["status"] == "paused"
    assert 5050 <= paused["elapsed_ms"] <= 5150
    again = engine.session(101, sid, now=when(50_000))
    assert again["status"] == "paused" and again["elapsed_ms"] == paused["elapsed_ms"]
    assert engine.control(101, sid, "resume", now=when(50_100))["status"] == "active"
    miss = engine.shoot(101, sid, 0, 1, 1, "miss-01", now=when(50_350))
    assert miss["last_event"]["outcome"] == "miss"
    assert miss["misses"] == 1 and miss["combo"] == 0
    assert miss["shots_used"] == 1
    assert engine.control(101, sid, "pause", now=when(51_000))["status"] == "paused"
    assert engine.control(101, sid, "pause", now=when(52_000))["status"] == "paused"


def test_shot_bounds_rate_limit_and_untrusted_client_scores_are_rejected(gallery):
    engine, store = gallery
    snap = engine.start(101, now=START)
    sid = snap["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    with pytest.raises(ValueError, match="shot"):
        engine.shoot(101, sid, -1, 10, 20, "badindex", now=when(350))
    with pytest.raises(ValueError, match="shot"):
        engine.shoot(101, sid, 0, 999, 20, "badcoord", now=when(350))
    first = engine.shoot(101, sid, 0, 1, 1, "miss-first", now=when(420))
    assert first["score"] == 0
    with pytest.raises(ValueError, match="Out-of-order"):
        engine.shoot(101, sid, 4, 1, 1, "skip-sequence", now=when(600))
    with pytest.raises(ValueError, match="Slow down"):
        engine.shoot(101, sid, 1, 1, 1, "spam", now=when(450))
    assert engine.session(101, sid, now=when(700))["shots_used"] == 1
    assert not hasattr(engine, "set_score")
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0


def test_end_of_timer_finished_record_and_separate_discord_attempts(gallery):
    engine, store = gallery
    started = engine.start(101, now=START)
    sid = started["session_id"]
    engine.control(101, sid, "resume", now=when(200))
    expired = engine.session(101, sid, now=when(46000))
    assert expired["status"] == "finished" and expired["elapsed_ms"] == 45000
    assert expired["result"] and expired["score"] == 0
    assert engine.record(101, now=when(47000))["finished_runs"] == 1
    restarted = engine.start(101, now=when(48000))
    assert restarted["session_id"] != sid
    assert restarted["status"] == "paused"
    classic = SocialArcadeEngine(store).lobby(SEASON, 101, when(48000))
    assert classic.record("gallery").attempts_today == 0


def test_finish_early_then_restart_and_double_tap_concurrency(gallery):
    engine, store = gallery
    ready = engine.start(101, now=START)
    sid = ready["session_id"]
    engine.control(101, sid, "resume", now=when(150))
    def send(i):
        try:
            return engine.shoot(101, sid, 0, 1, 1, f"parallel-{i}", now=when(400))
        except ValueError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(send, range(2)))
    assert sum(isinstance(x, dict) for x in answers) == 1
    assert engine.session(101, sid, now=when(500))["shots_used"] == 1
    finished = engine.control(101, sid, "finish", now=when(1500))
    assert finished["status"] == "finished" and finished["misses"] == 1
    assert engine.control(101, sid, "finish", now=when(1600))["status"] == "finished"
    assert engine.start(101, now=when(1700))["session_id"] != sid
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_gallery_shots").fetchone()[0] == 1


def test_api_gallery_feature_flag_auth_csrf_and_shot_idempotency(monkeypatch):
    from fastapi.testclient import TestClient
    from unittest.mock import Mock
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings

    ids, game = FakeIdentity(), Mock()
    game.gallery_start.return_value = {"session_id": "a" * 32}
    game.gallery_shoot.return_value = {"score": 7}
    with TestClient(create_app(fake_settings(), identity=ids, game=game),
                    base_url="https://snowfall.example") as client:
        assert client.post("/v1/game/arcade/gallery/start").status_code == 401
        token, csrf = ids.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.post("/v1/game/arcade/gallery/start").status_code == 403
        hdr = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/game/arcade/gallery/start", headers=hdr).status_code == 503
        monkeypatch.setenv("SNOWFALL_ARCADE_V299A_ENABLED", "1")
        assert client.post("/v1/game/arcade/gallery/start", headers=hdr).status_code == 200
        body = {"session_id": "a"*32, "shot_index": 0, "x": 200, "y": 150}
        assert client.post("/v1/game/arcade/gallery/shot", json=body,
                           headers=hdr).status_code == 400
        hdr["Idempotency-Key"] = "gallery-shot-00001"
        assert client.post("/v1/game/arcade/gallery/shot", json=body,
                           headers=hdr).status_code == 200
        assert game.gallery_shoot.call_args.args[:5] == (101, "a"*32, 0, 200, 150)
        assert client.post("/v1/game/arcade/gallery/shot",
                           json={**body, "score": 1000}, headers=hdr).status_code == 200
        # Pydantic ignores extra fields; however neither the engine nor facade
        # has any setter for client-supplied scores and the value is unused.
        assert game.gallery_shoot.call_args.args[:5] == (101, "a"*32, 0, 200, 150)
