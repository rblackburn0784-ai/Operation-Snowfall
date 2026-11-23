"""v2.9.9 interactive practice schema and session on isolated PostgreSQL."""
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.db.store import Store
from snowfall.platform.interactive_arcade import InteractiveArcadePractice, install_practice_schema
from snowfall.platform.gallery_arcade import GalleryEngine, install_gallery_schema, target_position
from snowfall.platform.safecracker_arcade import SafecrackerEngine, install_safe_schema
from snowfall.platform.snowman_arcade import SnowmanBuilderEngine, install_snowman_schema
from snowfall.platform.catch_arcade import SnowflakeCatchEngine, install_catch_schema
from snowfall.platform.trivia_arcade import ChristmasTriviaEngine, install_trivia_schema
from snowfall.platform.arcade_hub import ArcadeHubEngine, GAMES

SEASON = "web-qa-2026"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)


@pytest.mark.skipif(
    not os.getenv("SNOWFALL_PG_TEST_DSN") or
    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
    reason="Explicit isolated PostgreSQL fixture only",
)
def test_additive_practice_table_runs_on_real_postgres_without_game_schema_change(tmp_path):
    import psycopg
    from psycopg import sql

    root = os.environ["SNOWFALL_PG_TEST_DSN"]
    u = urlsplit(root)
    if u.hostname not in ("localhost", "127.0.0.1") or u.path != "/snowfall_test":
        pytest.fail("Refusing to connect to non-local PostgreSQL")
    name = "snowfall_v299_practice_test"
    dsn = urlunsplit(u._replace(path="/" + name))
    with psycopg.connect(root, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        source = Store(tmp_path / "source.sqlite3")
        source.initialize()
        source.ensure_season(SEASON, START)
        source.register(SEASON, 101, "TestSnowman", "Chicago", START-timedelta(days=1))
        source.transition(SEASON, 900, "start", START, "QA arcade")
        migrate(source.path, dsn, confirmation="OFFLINE_MIGRATE")
        pg = PostgresStore(dsn, practice_root=tmp_path)
        pg.initialize()
        with pg.connect() as con:
            install_practice_schema(con)
            install_gallery_schema(con)
            install_safe_schema(con)
            install_snowman_schema(con)
            install_catch_schema(con)
            install_trivia_schema(con)
        pg.initialize()  # Existing canonical version stays unchanged.
        arcade = InteractiveArcadePractice(pg, SEASON)
        run = arcade.start(101, "gallery", now=START)
        sid = run["session_id"]
        assert arcade.start(101, "gallery", now=START)["session_id"] == sid
        state = {**run["state"], "elapsed_ms": 3000, "hits": 1, "position": .4}
        saved = arcade.save(101, sid, 0, state, now=START+timedelta(seconds=5))
        assert saved["revision"] == 1 and saved["practice_score"] == 10
        assert arcade.session(101, sid, now=START+timedelta(seconds=6)) == saved
        with pg.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM web_arcade_practice_sessions").fetchone()[0] == 1
        gallery = GalleryEngine(pg, SEASON)
        ready = gallery.start(101, now=START)
        assert ready["status"] == "paused" and ready["ammo"] == 32
        sid = ready["session_id"]
        playing = gallery.control(101, sid, "resume", now=START+timedelta(milliseconds=100))
        t = playing["schedule"][0]
        x, y = target_position(t, t["start"]+80)
        hit = gallery.shoot(101, sid, 0, round(x), round(y),
                            "gallery-pg-first-shot",
                            now=START+timedelta(milliseconds=100+t["start"]+80))
        assert hit["hits"] == 1 and hit["score"] == 7
        assert gallery.shoot(101, sid, 0, round(x), round(y),
                             "gallery-pg-first-shot",
                             now=START+timedelta(seconds=3))["repeated"]
        assert gallery.control(101, sid, "finish", now=START+timedelta(seconds=4))["status"] == "finished"
        with pg.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM web_arcade_gallery_sessions").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM web_arcade_gallery_shots").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        safe = SafecrackerEngine(pg, SEASON)
        vault = safe.start(101, now=START)
        assert vault["status"] == "paused"
        assert vault["combination"] is None
        safe_id = vault["session_id"]
        assert safe.control(101, safe_id, "resume",
                            now=START+timedelta(milliseconds=200))["status"] == "active"
        rotated = safe.move(101, safe_id, 0, "turn", 8, "safe-pg-dial-00001",
                            now=START+timedelta(milliseconds=1200))
        assert rotated["action_seq"] == 1 and rotated["dial"] == 8
        assert safe.move(101, safe_id, 0, "turn", 8, "safe-pg-dial-00001",
                         now=START+timedelta(milliseconds=1600))["repeated"]
        assert safe.control(101, safe_id, "pause",
                            now=START+timedelta(milliseconds=1900))["status"] == "paused"
        assert safe.session(101, safe_id,
                            now=START+timedelta(seconds=5))["dial"] == 8
        with pg.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM web_arcade_safe_sessions").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM web_arcade_safe_actions").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        builder = SnowmanBuilderEngine(pg, SEASON)
        build = builder.start(101, now=START)
        assert build["status"] == "paused" and build["total_parts"] == 20
        assert build["blueprint"]["required"] == 4
        building = builder.control(101, build["session_id"], "resume",
                                   now=START+timedelta(milliseconds=300))
        slot = building["blueprint"]["slots"][0]
        dropped = builder.place(101, build["session_id"], 0, slot["id"],
                                slot["x"], slot["y"], "snowman-pg-drop-00001",
                                now=START+timedelta(milliseconds=1400))
        assert dropped["placed_total"] == 1 and dropped["score"] == 4
        assert builder.place(101, build["session_id"], 0, slot["id"],
                             slot["x"], slot["y"], "snowman-pg-drop-00001",
                             now=START+timedelta(milliseconds=1800))["repeated"]
        assert builder.control(101, build["session_id"], "pause",
                               now=START+timedelta(seconds=2))["status"] == "paused"
        assert builder.session(101, build["session_id"],
                               now=START+timedelta(seconds=8))["placed_total"] == 1
        with pg.connect() as con:
            assert con.execute(
                "SELECT COUNT(*) FROM web_arcade_snowman_sessions").fetchone()[0] == 1
            assert con.execute(
                "SELECT COUNT(*) FROM web_arcade_snowman_actions").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        storm = SnowflakeCatchEngine(pg, SEASON)
        flurries = storm.start(101, now=START)
        assert flurries["status"] == "paused"
        assert len(flurries["schedule"]) == 45
        assert storm.control(101, flurries["session_id"], "resume",
                             now=START+timedelta(milliseconds=100))["status"] == "active"
        moved = storm.update(101, flurries["session_id"], 0, 345,
                             "catch-pg-position-00001",
                             now=START+timedelta(milliseconds=1300))
        assert moved["basket_x"] == 345 and moved["action_seq"] == 1
        assert storm.update(101, flurries["session_id"], 0, 345,
                            "catch-pg-position-00001",
                            now=START+timedelta(milliseconds=1800))["repeated"]
        assert storm.control(101, flurries["session_id"], "pause",
                             now=START+timedelta(seconds=2))["status"] == "paused"
        assert storm.session(101, flurries["session_id"],
                             now=START+timedelta(seconds=8))["basket_x"] == 345
        with pg.connect() as con:
            assert con.execute(
                "SELECT COUNT(*) FROM web_arcade_catch_sessions").fetchone()[0] == 1
            assert con.execute(
                "SELECT COUNT(*) FROM web_arcade_catch_actions").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        trivia = ChristmasTriviaEngine(pg, SEASON)
        quiz = trivia.start(101, now=START)
        assert quiz["status"] == "paused" and quiz["total_questions"] == 15
        assert "correct" not in quiz["question"]
        assert trivia.control(101, quiz["session_id"], "resume",
                              now=START+timedelta(milliseconds=100))["status"] == "active"
        good = next(p for p in quiz["question"]["options"]
                    if p == "Reindeer") if "Reindeer" in quiz["question"]["options"] else quiz["question"]["options"][0]
        answered = trivia.answer(101, quiz["session_id"], 0, good,
                                 "trivia-pg-answer-00001",
                                 now=START+timedelta(milliseconds=700))
        assert answered["step"] == 1 and answered["last_answer"]["verdict"] in (
            "correct", "wrong")
        assert trivia.answer(101, quiz["session_id"], 0, good,
                             "trivia-pg-answer-00001",
                             now=START+timedelta(milliseconds=1000))["repeated"]
        assert trivia.control(101, quiz["session_id"], "pause",
                              now=START+timedelta(seconds=2))["status"] == "paused"
        assert trivia.session(101, quiz["session_id"],
                              now=START+timedelta(seconds=8))["step"] == 1
        with pg.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM web_arcade_trivia_sessions").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM web_arcade_trivia_answers").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0

        # Hub reads the five existing QA schemas; it does not create tables,
        # acquire official competitive starts or expose future trivia keys.
        hub = ArcadeHubEngine(pg, SEASON, env={g[5]: "1" for g in GAMES})
        overview = hub.overview(101, now=START+timedelta(seconds=8))
        assert overview["version"] == "2.9.9f"
        assert overview["available_games"] == 5
        assert overview["resumable_games"] == 4
        assert overview["completed_practice_runs"] == 1
        assert [m["key"] for m in overview["modes"]] == [
            "gallery", "safe", "snowman", "catch", "trivia"]
        by_key = {m["key"]: m for m in overview["modes"]}
        assert by_key["gallery"]["status"] == "ready"
        assert by_key["gallery"]["finished_runs"] == 1
        assert by_key["safe"]["can_resume"]
        assert by_key["snowman"]["progress_label"] == "1 / 20 parts fitted"
        assert by_key["trivia"]["progress_label"] == "1 / 15 questions answered"
        assert "correct" not in str(by_key["trivia"])
        with pg.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0






    finally:
        with psycopg.connect(root, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(name)))
