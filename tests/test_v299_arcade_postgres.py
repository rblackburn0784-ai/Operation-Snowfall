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


    finally:
        with psycopg.connect(root, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(name)))
