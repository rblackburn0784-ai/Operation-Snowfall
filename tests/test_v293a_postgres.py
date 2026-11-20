"""Isolated PostgreSQL 16 v2.9.3a bootstrap/gameplay acceptance test.

ONLY runs in GitHub CI ephemeral postgres:16 with explicitly named test DSN.
It creates and drops two disposable CI databases; never runs on Railway.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from snowfall.db.migrate_postgres import migrate, verify
from snowfall.db.postgres import PostgresStore
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.staging import (
    QA_CONFIRM, QA_DB, STAGING_ENVIRONMENT, STAGING_PROJECT,
    StagingGame, _source_snapshot, prepare_web_qa,
)


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable PostgreSQL CI database required")
def test_staging_web_bootstrap_preserves_imported_database_and_plays(tmp_path):
    import psycopg

    admin_url = os.environ["SNOWFALL_PG_TEST_DSN"]
    parsed = urlsplit(admin_url)
    if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/snowfall_test":
        pytest.fail("Refusing to create databases outside disposable CI")
    original_url = urlunsplit(parsed._replace(path="/railway"))
    with psycopg.connect(admin_url, autocommit=True) as root:
        root.execute("CREATE DATABASE railway")
    try:
        snapshot = tmp_path / "fixture.sqlite3"
        _source_snapshot(snapshot, "imported-test")
        migrate(snapshot, original_url, confirmation="OFFLINE_MIGRATE")
        assert verify(snapshot, original_url)["matching"]

        env = {
            "SNOWFALL_DATABASE_URL": original_url,
            "RAILWAY_PROJECT_ID": STAGING_PROJECT,
            "RAILWAY_ENVIRONMENT_ID": STAGING_ENVIRONMENT,
            "RAILWAY_ENVIRONMENT_NAME": "staging",
            "SNOWFALL_API_ENABLED": "1",
            "SNOWFALL_DB_BACKEND": "postgres",
            "SNOWFALL_WEB_QA_CONFIRM": QA_CONFIRM,
            "SNOWFALL_API_SEASON_KEY": "web-qa-2026",
        }
        qa_url = prepare_web_qa(env)
        assert urlsplit(qa_url).path == "/" + QA_DB
        assert verify(snapshot, original_url)["matching"]  # Source untouched.
        identities = IdentityRepository(qa_url)
        identities.check()
        game = StagingGame(SharedGame(PostgresStore(qa_url, practice_root=tmp_path),
                                      "web-qa-2026"))
        exp = datetime.now(timezone.utc) + timedelta(minutes=1)
        user = identities.resolve_underworld("web-qa-account-1", "web-qa-character-1",
                                             "unique-qa-nonce-1", exp)
        first = game.register(user, "WebTestRunner", "Chicago")
        assert first["player_id"] == str(user)
        assert game.me(user)["resources"]["snowflakes"] == 60
        assert game.register(user, "WebTestRunner", "Chicago") == first
        assert game.me(user)["resources"]["snowflakes"] == 60
        assert game.targets(user)
        boss = game.boss(user, "web-staging-boss-test")
        assert boss["kind"] == "boss"
        assert game.boss(user, "web-staging-boss-test")["repeated"]
        assert game.world(user)["boss_hp"] >= 0
        assert game.me(user)["score"] >= 0
        assert game.leaderboard()
        assert len(identities.links(user)) == 1
        assert prepare_web_qa(env) == qa_url
        assert verify(snapshot, original_url)["matching"]
    finally:
        with psycopg.connect(admin_url, autocommit=True) as root:
            for name in (QA_DB, "railway"):
                root.execute("""SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()""",
                    (name,))
                # Identifiers are hardcoded ephemeral CI database names.
                from psycopg import sql
                root.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
