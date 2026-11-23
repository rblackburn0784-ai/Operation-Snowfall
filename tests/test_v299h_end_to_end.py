"""v2.9.9h — cross-mode day-one user journey and abuse resistance in isolated QA."""
from datetime import datetime, timedelta, timezone
import random

import pytest

from snowfall.db.store import Store
from snowfall.platform.arcade_hub import ArcadeHubEngine, GAMES
from snowfall.platform.catch_arcade import (
    SnowflakeCatchEngine, flake_position, install_catch_schema,
)
from snowfall.platform.gallery_arcade import (
    GalleryEngine, install_gallery_schema, target_position,
)
from snowfall.platform.safecracker_arcade import SafecrackerEngine, install_safe_schema
from snowfall.platform.snowman_arcade import SnowmanBuilderEngine, install_snowman_schema
from snowfall.platform.trivia_arcade import ChristmasTriviaEngine, install_trivia_schema
from snowfall.services.social_arcade import SocialArcadeEngine

START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
SEASON = "arcade-end-to-end-qa"
FLAGS = {g[5]: "1" for g in GAMES}


def at(milliseconds: int):
    return START + timedelta(milliseconds=milliseconds)


@pytest.fixture
def run_all(tmp_path):
    store = Store(tmp_path / "arcade-end-to-end.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    store.register(SEASON, 101, "LinkedUnderworld", "Chicago",
                   START - timedelta(days=1))
    store.register(SEASON, 202, "OtherPlayer", "Detroit",
                   START - timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Five arcade games QA")
    with store.connect() as con:
        for installer in (
            install_gallery_schema, install_safe_schema,
            install_snowman_schema, install_catch_schema,
            install_trivia_schema,
        ):
            installer(con)
    return store, {
        "gallery": GalleryEngine(store, SEASON),
        "safe": SafecrackerEngine(store, SEASON, random.Random(42)),
        "snowman": SnowmanBuilderEngine(store, SEASON, random.Random(42)),
        "catch": SnowflakeCatchEngine(store, SEASON, random.Random(42)),
        "trivia": ChristmasTriviaEngine(store, SEASON, random.Random(42)),
    }


def resources(con, player):
    row = con.execute(
        "SELECT snowballs,warmth,snowflakes,armour_hp "
        "FROM player_resources WHERE season_key=? AND discord_user_id=?",
        (SEASON, player),
    ).fetchone()
    return tuple(row)


def test_all_five_modes_resume_after_reconnect_without_awards_or_leaks(run_all):
    store, modes = run_all
    with store.connect() as con:
        before = resources(con, 101)
        before_other = resources(con, 202)

    # Five separate QA sessions coexist; no classic Arcade starts are spent.
    ready = {key: engine.start(101, now=START)
             for key, engine in modes.items()}
    assert set(ready) == {"gallery", "safe", "snowman", "catch", "trivia"}
    assert len({view["session_id"] for view in ready.values()}) == 5
    assert all(view["status"] == "paused" and view["practice"] and
               not view["competitive"] for view in ready.values())
    for key, engine in modes.items():
        sid = ready[key]["session_id"]
        assert engine.start(101, now=at(10))["session_id"] == sid
        with pytest.raises(ValueError, match="unavailable"):
            engine.session(202, sid, now=at(20))
        with pytest.raises(ValueError, match="unavailable"):
            engine.control(202, sid, "resume", now=at(30))
        engine.control(101, sid, "resume", now=at(100))

    # Real Gallery target. Score and hit result are server-calculated.
    gallery = ready["gallery"]
    target = gallery["schedule"][0]
    t = target["start"] + 120
    x, y = target_position(target, t)
    shot = modes["gallery"].shoot(
        101, gallery["session_id"], 0, round(x), round(y),
        "e2e-gallery-validated", now=at(t + 100))
    assert shot["last_event"]["outcome"] == "hit"
    assert shot["score"] == 7
    assert modes["gallery"].shoot(
        101, gallery["session_id"], 0, round(x), round(y),
        "e2e-gallery-validated", now=at(1950))["repeated"]

    # Real safe dial movement; cannot choose an unlocked state.
    safe = ready["safe"]
    turned = modes["safe"].move(
        101, safe["session_id"], 0, "turn", 4,
        "e2e-safe-turn", now=at(900))
    assert turned["dial"] == 4 and turned["stage"] == 0
    assert modes["safe"].move(
        101, safe["session_id"], 0, "turn", 4,
        "e2e-safe-turn", now=at(1100))["repeated"]

    # Real build: exactly one blueprint part, no client-awarded points.
    snowman = ready["snowman"]
    slot = snowman["blueprint"]["slots"][0]
    fit = modes["snowman"].place(
        101, snowman["session_id"], 0, slot["id"], slot["x"], slot["y"],
        "e2e-snowman-place", now=at(1100))
    assert fit["placed_total"] == 1 and fit["score"] == 4
    assert modes["snowman"].place(
        101, snowman["session_id"], 0, slot["id"], slot["x"], slot["y"],
        "e2e-snowman-place", now=at(1450))["repeated"]

    # Server resolves flake crossings and movement, not claimed catches.
    catch = ready["catch"]
    first = catch["schedule"][0]
    basket, _ = flake_position(first, first["impact"])
    updated = modes["catch"].update(
        101, catch["session_id"], 0, round(basket),
        "e2e-catch-move", now=at(first["impact"] + 190))
    assert updated["caught"] == 1 and updated["score"] == 3
    assert modes["catch"].update(
        101, catch["session_id"], 0, round(basket),
        "e2e-catch-move", now=at(first["impact"] + 280))["repeated"]

    # Trivia answer keys stay private until that question is resolved.
    trivia = ready["trivia"]
    assert "correct" not in trivia["question"]
    selected = trivia["question"]["options"][0]
    submitted = modes["trivia"].answer(
        101, trivia["session_id"], 0, selected,
        "e2e-trivia-answer", now=at(850))
    assert submitted["step"] == 1
    assert "correct" not in submitted["question"]
    assert submitted["last_answer"]["answer"]
    assert modes["trivia"].answer(
        101, trivia["session_id"], 0, selected,
        "e2e-trivia-answer", now=at(1650))["repeated"]

    # Navigation pause/resume keeps the same five session IDs.
    for key, engine in modes.items():
        sid = ready[key]["session_id"]
        paused = engine.control(101, sid, "pause", now=at(5000))
        assert paused["status"] == "paused"
        snapshot = engine.session(101, sid, now=at(55_000))
        assert snapshot["status"] == "paused"
        assert engine.start(101, now=at(55_000))["session_id"] == sid

    hub = ArcadeHubEngine(store, SEASON, env=FLAGS).overview(
        101, now=at(55_000))
    assert hub["available_games"] == 5 and hub["resumable_games"] == 5
    assert hub["completed_practice_runs"] == 0
    assert all(row["can_resume"] and row["practice"] and
               not row["competitive"] for row in hub["modes"])
    outsider = ArcadeHubEngine(store, SEASON, env=FLAGS).overview(
        202, now=at(55_000))
    assert outsider["resumable_games"] == 0
    assert outsider["completed_practice_runs"] == 0
    assert all(row["session_id"] is None for row in outsider["modes"])

    with store.connect() as con:
        assert resources(con, 101) == before
        assert resources(con, 202) == before_other
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
    classic = SocialArcadeEngine(store).lobby(SEASON, 101, at(55_000))
    assert all(classic.record(key).attempts_today == 0 for key in modes)


def test_competitive_passport_never_reads_practice_records(run_all):
    store, modes = run_all
    gallery = modes["gallery"].start(101, now=START)
    modes["gallery"].control(101, gallery["session_id"], "resume", now=at(100))
    modes["gallery"].control(101, gallery["session_id"], "finish", now=at(200))
    assert modes["gallery"].record(101, now=at(300))["finished_runs"] == 1
    assert ArcadeHubEngine(store, SEASON, env=FLAGS).overview(
        101, now=at(300))["completed_practice_runs"] == 1
    classic = SocialArcadeEngine(store).lobby(SEASON, 101, at(300))
    assert classic.record("gallery").attempts_today == 0
    assert classic.record("gallery").personal_best == 0
