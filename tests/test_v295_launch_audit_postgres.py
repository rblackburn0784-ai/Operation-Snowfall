"""v2.9.5: real isolated PostgreSQL audit and web database-readiness checks.

Uses disposable localhost Postgres only. Neither test calls Discord nor reads
Railway variables, production players or user data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.launch_audit import ReadinessError, audit_qa_database
from snowfall.platform.staging import QA_SEASON, STAGING_PROJECT, StagingGame, _source_snapshot


def test_audit_rejects_other_season_database():
    with pytest.raises(ReadinessError, match="isolated"):
        audit_qa_database("postgresql://test:secret@localhost/railway")


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable localhost PostgreSQL must be explicitly enabled")
def test_staging_qa_readiness_and_audit_gate(tmp_path, monkeypatch):
    import psycopg
    from psycopg import sql

    admin_dsn = os.environ["SNOWFALL_PG_TEST_DSN"]
    parsed = urlsplit(admin_dsn)
    if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/snowfall_test":
        pytest.fail("Refusing non-CI PostgreSQL database")
    db = "snowfall_web_qa"  # audit refuses a different logical database
    dsn = urlunsplit(parsed._replace(path="/" + db))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
    try:
        seed = tmp_path/"seed.sqlite3"
        _source_snapshot(seed, QA_SEASON)
        migrate(seed, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as conn:
            conn.execute("""CREATE TABLE snowfall_web_qa_marker (
                singleton INT PRIMARY KEY CHECK(singleton=1),
                project_id TEXT NOT NULL, season_key TEXT NOT NULL)""")
            conn.execute("INSERT INTO snowfall_web_qa_marker VALUES(1,%s,%s)",
                         (STAGING_PROJECT, QA_SEASON))
            conn.execute("""CREATE TABLE snowfall_web_qa_bonus (
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")

        identity = IdentityRepository(dsn)
        identity.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        store = PostgresStore(dsn, practice_root=tmp_path)
        game = StagingGame(SharedGame(store, QA_SEASON))
        unlinked = audit_qa_database(dsn)
        assert unlinked["scope"] == "ISOLATED_QA_ONLY"
        assert unlinked["season"] == QA_SEASON
        assert unlinked["prize_awards"] == 0
        assert unlinked["linked_registered_players"] == 0
        assert unlinked["status"] in ("ready_with_warnings", "ready")

        principal = identity.resolve_underworld(
            "account-qa-ready", "character-qa-ready", "nonce-qa-ready",
            datetime.now(timezone.utc)+timedelta(minutes=1))
        identity.link_discord(principal, "123456789012345678")
        game.register(principal, "AuditSnowDude", "Chicago")
        audit = audit_qa_database(dsn)
        assert audit["linked_registered_players"] == 1
        assert audit["prize_awards"] == 0
        assert audit["bad_resources"] == 0
        assert audit["orphan_resources"] == 0
        assert audit["status"] in ("ready", "ready_with_warnings")

        cfg = APISettings(database_url=dsn, season_key=QA_SEASON,
                          public_base_url="https://qa.local", underworld_secret="qa-fake-secret")
        with TestClient(create_app(cfg, identity=identity, game=game),
                        base_url="https://qa.local") as client:
            healthy = client.get("/v1/health")
            assert healthy.status_code == 200
            assert healthy.json()["version"] == "2.9.5"
            ready = client.get("/v1/ready")
            assert ready.status_code == 200, ready.text
            assert ready.json() == {
                "status": "ready", "backend": "postgres", "season": QA_SEASON}

            def broken_dependency():
                raise RuntimeError("postgresql://user:TOP_SECRET_PASSWORD@host/db")
            monkeypatch.setattr(identity, "check", broken_dependency)
            failure = client.get("/v1/ready")
            assert failure.status_code == 503
            assert failure.json()["detail"] == "Game database not ready"
            assert "TOP_SECRET_PASSWORD" not in failure.text
            # Liveness intentionally remains quick and does not promise DB readiness.
            assert client.get("/v1/health").status_code == 200
            monkeypatch.undo()
            assert client.get("/v1/ready").status_code == 200

        # A QA prize award is a hard red flag: do not hide it behind a
        # successful process or HTTP health check.
        with psycopg.connect(dsn) as conn:
            conn.execute("""INSERT INTO prize_awards(
                season_key,place,discord_user_id,mr_username,city,points,reward,status)
                VALUES (%s,1,%s,%s,'Chicago',5,'QA_TEST_SHOULD_NOT_PAY','pending')""",
                (QA_SEASON, principal, "AuditSnowDude"))
        blocked = audit_qa_database(dsn)
        assert blocked["status"] == "blocked"
        assert blocked["prize_awards"] == 1
        assert any("prize" in x.lower() for x in blocked["blockers"])
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()", (db,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db)))
