"""v2.9.9 interactive practice schema and session on isolated PostgreSQL."""
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.db.store import Store
from snowfall.platform.interactive_arcade import InteractiveArcadePractice, install_practice_schema

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
    finally:
        with psycopg.connect(root, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(name)))
