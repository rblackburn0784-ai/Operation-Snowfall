"""v2.9.5 — concurrent replay, two-player isolation, restart and readiness PG gate."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.discord_bridge import DiscordBridgeGateway
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.staging import STAGING_PROJECT, StagingGame, _source_snapshot

SEASON = "web-qa-2026"
ACTOR1 = 123456789012345678
ACTOR2 = 234567890123456789
ID1 = 991234567890123456
ID2 = 991234567890123457


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Isolated localhost PostgreSQL fixture explicitly required")
def test_two_linked_users_replay_concurrency_and_restarts(tmp_path, monkeypatch):
    import psycopg
    from psycopg import sql

    root = os.environ["SNOWFALL_PG_TEST_DSN"]
    parsed = urlsplit(root)
    if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/snowfall_test":
        pytest.fail("Refusing any non-local PostgreSQL")
    name = "snowfall_v295_launch_readiness_test"
    dsn = urlunsplit(parsed._replace(path="/" + name))
    with psycopg.connect(root, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        source = tmp_path / "seed.sqlite3"
        _source_snapshot(source, SEASON)
        migrate(source, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as con:
            # The consolidated web readiness gate requires verified QA DB
            # ownership; an ad-hoc localhost database without its marker
            # must correctly return 503, not silently pass.
            con.execute("""CREATE TABLE snowfall_web_qa_marker (
                singleton INT PRIMARY KEY CHECK(singleton=1),
                project_id TEXT NOT NULL, season_key TEXT NOT NULL)""")
            con.execute("INSERT INTO snowfall_web_qa_marker VALUES(1,%s,%s)",
                        (STAGING_PROJECT, SEASON))
            con.execute("""CREATE TABLE snowfall_web_qa_bonus (
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        identities = IdentityRepository(dsn)
        identities.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        expiry = datetime.now(timezone.utc)+timedelta(minutes=5)
        p1 = identities.resolve_underworld(
            "account-qa-one", "character-qa-one", "nonce-one", expiry)
        p2 = identities.resolve_underworld(
            "account-qa-two", "character-qa-two", "nonce-two", expiry)
        identities.link_discord(p1, str(ACTOR1))
        identities.link_discord(p2, str(ACTOR2))
        game = StagingGame(SharedGame(PostgresStore(dsn, practice_root=tmp_path), SEASON))
        gateway = DiscordBridgeGateway(identities, game)
        game.register(p1, "OneSnowman", "Chicago")
        game.register(p2, "TwoSnowman", "Detroit")
        first_before = game.progress(p1)
        second_before = game.progress(p2)
        assert first_before["snowflakes"] == second_before["snowflakes"] == 60

        # The same Discord interaction, even invoked concurrently six times,
        # MUST produce exactly one game mutation under the shared PG lock.
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda _: gateway.craft(ACTOR1, "fort", ID1), range(6)))
        assert sum(not result["repeated"] for result in results) == 1
        assert sum(result["repeated"] for result in results) == 5
        after = game.progress(p1)
        assert after["inventory"]["fort"] == first_before["inventory"]["fort"]+1
        assert after["snowflakes"] == first_before["snowflakes"]-10
        assert game.progress(p2) == second_before

        # Even the exact same action ID cannot be replayed by another
        # identity, nor transferred to its progress/inventory.
        with pytest.raises(ValueError, match="another action"):
            gateway.craft(ACTOR2, "fort", ID1)
        assert game.progress(p2) == second_before

        other = gateway.craft(ACTOR2, "cocoa", ID2)
        assert not other["repeated"]
        assert game.progress(p2)["snowflakes"] == second_before["snowflakes"]-8
        assert game.progress(p1)["snowflakes"] == after["snowflakes"]

        cfg = APISettings(
            database_url=dsn, season_key=SEASON, public_base_url="https://qa.test",
            underworld_secret="test-qa-local-secret",
        )
        app = create_app(cfg, identity=identities, game=game)
        with TestClient(app, base_url="https://qa.test") as client:
            assert client.get("/v1/health").json()["version"] == "2.9.7"
            ready = client.get("/v1/ready")
            assert ready.status_code == 200
            assert ready.json()["status"] == "ready"
            # A service whose identity database is unavailable should NOT
            # claim readiness, nor disclose any secret SQL/DSN information.
            def dead_database():
                raise RuntimeError("Private database credential must never be returned")
            monkeypatch.setattr(identities, "check", dead_database)
            blocked = client.get("/v1/ready")
            assert blocked.status_code == 503
            assert "Private database" not in blocked.text
            monkeypatch.undo()

        # A new independent app/worker connection reads identical resource
        # state after the simulated restart and the original interaction is
        # still replay-safe (no duplicate bonus, item, attack or balance).
        restarted_identity = IdentityRepository(dsn)
        restarted_game = StagingGame(
            SharedGame(PostgresStore(dsn, practice_root=tmp_path), SEASON))
        new_gateway = DiscordBridgeGateway(restarted_identity, restarted_game)
        assert restarted_identity.principal_for_discord(str(ACTOR1)) == p1
        assert restarted_identity.principal_for_discord(str(ACTOR2)) == p2
        assert restarted_game.progress(p1) == game.progress(p1)
        assert restarted_game.progress(p2) == game.progress(p2)
        replay = new_gateway.craft(ACTOR1, "fort", ID1)
        assert replay["repeated"]
        assert restarted_game.progress(p1) == after
        assert restarted_game.progress(p2)["snowflakes"] == second_before["snowflakes"]-8
        with psycopg.connect(dsn) as con:
            assert con.execute(
                "SELECT COUNT(*) FROM item_events WHERE interaction_id=%s",
                ("discord-bridge:"+str(ID1),)).fetchone()[0] == 1
            assert con.execute(
                "SELECT COUNT(*) FROM players WHERE season_key=%s "
                "AND discord_user_id IN (%s,%s)",
                (SEASON, ACTOR1, ACTOR2)).fetchone()[0] == 0
    finally:
        with psycopg.connect(root, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()", (name,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
