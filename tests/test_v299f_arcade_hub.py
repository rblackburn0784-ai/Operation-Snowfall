"""v2.9.9f — five-game hub identity, resumability, records and isolation."""
from datetime import datetime, timedelta, timezone
import json
import random
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from snowfall.db.store import Store
from snowfall.platform.api import create_app
from snowfall.platform.arcade_hub import ArcadeHubEngine, GAMES
from snowfall.platform.catch_arcade import SnowflakeCatchEngine, install_catch_schema
from snowfall.platform.gallery_arcade import GalleryEngine, install_gallery_schema
from snowfall.platform.safecracker_arcade import SafecrackerEngine, install_safe_schema
from snowfall.platform.snowman_arcade import SnowmanBuilderEngine, install_snowman_schema
from snowfall.platform.trivia_arcade import ChristmasTriviaEngine, install_trivia_schema
from snowfall.services.social_arcade import SocialArcadeEngine
from test_v293_platform import FakeIdentity, fake_settings

SEASON = "arcade-hub-qa"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
FLAGS = {g[5]: "1" for g in GAMES}


def at(ms: int):
    return START + timedelta(milliseconds=ms)


@pytest.fixture
def arcade(tmp_path):
    store = Store(tmp_path / "arcade_hub.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    for pid, name in ((101, "WinterTester"), (202, "SnowGuest")):
        store.register(SEASON, pid, name, "Chicago", START - timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Arcade Hub QA")
    with store.connect() as con:
        for install in (
            install_gallery_schema, install_safe_schema, install_snowman_schema,
            install_catch_schema, install_trivia_schema,
        ):
            install(con)
    assert store.schema_version() == 11
    return store


def game_engines(store):
    return {
        "gallery": GalleryEngine(store, SEASON),
        "safe": SafecrackerEngine(store, SEASON, random.Random(42)),
        "snowman": SnowmanBuilderEngine(store, SEASON, random.Random(42)),
        "catch": SnowflakeCatchEngine(store, SEASON, random.Random(42)),
        "trivia": ChristmasTriviaEngine(store, SEASON, random.Random(42)),
    }


def test_all_disabled_omits_game_tables_and_never_leaks_player_data(tmp_path):
    store = Store(tmp_path / "no_arcade_tables.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    store.register(SEASON, 101, "SnowUser", "Chicago", START - timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Hub disabled")
    # This database has NO v2.9.9a-e tables. Flags off must not query them.
    hub = ArcadeHubEngine(store, SEASON, env={}).overview(101, now=START)
    assert hub["version"] == "2.9.9f"
    assert hub["player_id"] == "101" and hub["day"] == 1
    assert hub["practice"] is True and hub["competitive"] is False
    assert hub["available_games"] == hub["resumable_games"] == 0
    assert hub["completed_practice_runs"] == 0
    assert hub["suggested_mode"] is None
    assert len(hub["modes"]) == 5
    assert [m["key"] for m in hub["modes"]] == [
        "gallery", "safe", "snowman", "catch", "trivia"]
    assert all(m["status"] == "unavailable" and not m["enabled"] and
               not m["can_resume"] and m["session_id"] is None and
               m["personal_best"] == 0 for m in hub["modes"])


def test_enabling_only_one_mode_does_not_read_the_other_four_tables(tmp_path):
    store = Store(tmp_path / "one_game.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    store.register(SEASON, 101, "SnowUser", "Chicago", START - timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Gallery only")
    with store.connect() as con:
        install_gallery_schema(con)
    env={"SNOWFALL_ARCADE_V299A_ENABLED": "1"}
    hub = ArcadeHubEngine(store, SEASON, env=env).overview(101, now=START)
    assert hub["available_games"] == 1 and hub["suggested_mode"] == "gallery"
    assert hub["modes"][0]["enabled"] is True
    assert all(not m["enabled"] for m in hub["modes"][1:])


def test_five_saved_games_surface_resumable_status_without_new_starts(arcade):
    engine = game_engines(arcade)
    created = {key: game.start(101, now=START) for key, game in engine.items()}
    assert all(run["status"] == "paused" for run in created.values())
    hub = ArcadeHubEngine(arcade, SEASON, env=FLAGS)
    result = hub.overview(101, now=at(500))
    assert result["available_games"] == result["resumable_games"] == 5
    assert result["completed_practice_runs"] == 0
    assert result["suggested_mode"] in created
    assert all(m["can_resume"] and m["status"] == "paused"
               for m in result["modes"])
    assert {m["key"]: m["session_id"] for m in result["modes"]} == {
        key: row["session_id"] for key, row in created.items()}
    assert all(m["progress_percent"] == 0 for m in result["modes"])
    assert all(m["personal_best"] == 0 for m in result["modes"])
    # A GET of hub data doesn't create extra sessions or write Classic scores.
    again = hub.overview(101, now=at(700))
    assert again["resumable_games"] == 5
    with arcade.connect() as con:
        for game in GAMES:
            assert con.execute(
                f"SELECT COUNT(*) FROM {game[6]} WHERE player_id=?",
                (101,)).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0


def test_progress_and_records_use_actual_finished_and_paused_game_state(arcade):
    game = game_engines(arcade)
    gallery = game["gallery"].start(101, now=START)
    snowman = game["snowman"].start(101, now=START)
    safe = game["safe"].start(101, now=START)
    game["trivia"].start(101, now=START)
    game["catch"].start(101, now=START)
    game["gallery"].control(101, gallery["session_id"], "resume", now=at(100))
    game["gallery"].control(101, gallery["session_id"], "finish", now=at(300))
    game["snowman"].control(101, snowman["session_id"], "resume", now=at(500))
    slot = snowman["blueprint"]["slots"][0]
    step = game["snowman"].place(
        101, snowman["session_id"], 0, slot["id"], slot["x"], slot["y"],
        "hub-snowman-place-001", now=at(1000))
    assert step["placed_total"] == 1
    hub = ArcadeHubEngine(arcade, SEASON, env=FLAGS).overview(101, now=at(1500))
    by_key = {m["key"]: m for m in hub["modes"]}
    assert by_key["gallery"]["status"] == "ready"
    assert by_key["gallery"]["finished_runs"] == 1
    assert by_key["gallery"]["session_id"] is None
    assert by_key["snowman"]["status"] == "active"
    assert by_key["snowman"]["progress_percent"] == 5
    assert by_key["snowman"]["progress_label"] == "1 / 20 parts fitted"
    assert by_key["safe"]["can_resume"] is True
    assert hub["resumable_games"] == 4
    assert hub["completed_practice_runs"] == 1
    assert game["safe"].start(101, now=at(2000))["session_id"] == safe["session_id"]
    assert SocialArcadeEngine(arcade).lobby(
        SEASON, 101, at(2000)).record("snowman").attempts_today == 0


def test_hub_ends_expired_games_before_reporting_record_count(arcade):
    gallery = GalleryEngine(arcade, SEASON)
    sid = gallery.start(101, now=START)["session_id"]
    gallery.control(101, sid, "resume", now=at(100))
    hub = ArcadeHubEngine(arcade, SEASON, env=FLAGS).overview(101, now=at(47_000))
    g = hub["modes"][0]
    assert g["status"] == "ready" and not g["can_resume"]
    assert g["finished_runs"] == 1
    assert g["progress_percent"] == 0 and g["session_id"] is None
    assert hub["completed_practice_runs"] == 1
    assert gallery.session(101, sid, now=at(47_500))["status"] == "finished"


def test_visitor_does_not_see_another_player_sessions_or_records(arcade):
    gallery = GalleryEngine(arcade, SEASON)
    private = gallery.start(101, now=START)
    gallery.control(101, private["session_id"], "finish", now=at(100))
    hub = ArcadeHubEngine(arcade, SEASON, env=FLAGS).overview(202, now=at(300))
    assert hub["player_id"] == "202"
    assert hub["completed_practice_runs"] == 0 and hub["resumable_games"] == 0
    assert all(m["personal_best"] == 0 and m["finished_runs"] == 0 and
               m["session_id"] is None for m in hub["modes"])
    assert private["session_id"] not in json.dumps(hub)
    with pytest.raises(ValueError, match="unavailable"):
        gallery.session(202, private["session_id"], now=at(500))


def test_api_is_authenticated_cache_private_default_off_and_read_only(monkeypatch):
    identity, game = FakeIdentity(), Mock()
    game.arcade_hub.return_value = {
        "version": "2.9.9f", "player_id": "101", "modes": [
            {"key": key} for key in ("gallery", "safe", "snowman", "catch", "trivia")
        ],
    }
    with TestClient(create_app(fake_settings(), identity=identity, game=game),
                    base_url="https://snowfall.example") as client:
        assert client.get("/v1/game/arcade/hub").status_code == 401
        token, _csrf = identity.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.get("/v1/game/arcade/hub").status_code == 503
        monkeypatch.setenv("SNOWFALL_ARCADE_V299F_ENABLED", "1")
        response = client.get("/v1/game/arcade/hub")
        assert response.status_code == 200
        assert response.headers.get("Cache-Control") == "no-store"
        assert response.json()["player_id"] == "101"
        assert game.arcade_hub.call_args.args == (101,)
        assert client.post("/v1/game/arcade/hub", json={}).status_code == 405
        assert game.arcade_hub.call_count == 1
