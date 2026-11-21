"""v2.9.4e cross-platform proof: real official game ledgers on disposable PG.

This verifies two origins, one linked canonical player, real Discord event
receipts, browser CSRF, exact resource deltas, replay protection and expiry.
It neither starts a real bot nor connects to user/production databases.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.assertions import sign_underworld_assertion
from snowfall.platform.discord_bridge import DiscordBridgeGateway
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityConflict, IdentityError, IdentityRepository
from snowfall.platform.staging import StagingGame, _source_snapshot
from snowfall.platform.unified_discord import UnifiedDiscordStore
from snowfall.platform.verification import CrossPlatformVerifier

QA_SEASON = "web-qa-2026"
SECRET = "cross-platform-test-secret-0123456789-abcdefgh"
ACTOR = 123456789012345678
ACTOR2 = 234567890123456789


def assertion(account, character, nonce):
    now = int(datetime.now(timezone.utc).timestamp())
    return sign_underworld_assertion({
        "iss": "underworld", "aud": "operation-snowfall",
        "account_id": account, "character_id": character,
        "character_name": "VerifiedSnowDude",
        "iat": now, "exp": now+60, "jti": nonce,
    }, SECRET)


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Only disposable localhost PostgreSQL CI is supported")
def test_canonical_web_and_real_discord_actions_verified_end_to_end(tmp_path):
    import psycopg
    from psycopg import sql

    root_dsn = os.environ["SNOWFALL_PG_TEST_DSN"]
    parts = urlsplit(root_dsn)
    if parts.hostname not in ("localhost", "127.0.0.1") or parts.path != "/snowfall_test":
        pytest.fail("Refusing non-local PostgreSQL test")
    db = "snowfall_v294e_verification_test"
    dsn = urlunsplit(parts._replace(path="/" + db))
    with psycopg.connect(root_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
    try:
        source = tmp_path/"source.sqlite3"
        _source_snapshot(source, QA_SEASON)
        migrate(source, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as conn:
            conn.execute("""CREATE TABLE snowfall_web_qa_bonus(
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")

        identity = IdentityRepository(dsn)
        identity.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        base_store = PostgresStore(dsn, practice_root=tmp_path)
        shared = StagingGame(SharedGame(base_store, QA_SEASON))
        verifier = CrossPlatformVerifier(identity, shared, QA_SEASON)
        gateway = DiscordBridgeGateway(identity, shared, verification=verifier)
        config = APISettings(database_url=dsn, season_key=QA_SEASON,
                             public_base_url="https://qa.example",
                             underworld_secret=SECRET)

        with TestClient(create_app(config, identity=identity, game=shared),
                        base_url="https://qa.example") as client:
            assert client.get("/v1/verification/status").status_code == 401
            assert client.post("/v1/verification/start").status_code == 401

            login = client.post("/v1/auth/underworld", json={
                "assertion": assertion("test-account", "test-character", "nonce-1")})
            assert login.status_code == 200
            player_id = int(login.json()["player_id"])
            assert player_id > 2**53  # BIGINT stays a decimal string in web JSON.
            csrf = {"X-Snowfall-CSRF": login.json()["csrf"]}
            assert client.post("/v1/verification/start", headers=csrf).status_code == 409
            identity.link_discord(player_id, str(ACTOR))
            assert client.post("/v1/verification/start").status_code == 403
            assert client.post("/v1/verification/start", headers=csrf).status_code == 409

            register = client.post("/v1/game/register", json={
                "mr_username": "SharedSnowDude", "city": "Chicago"}, headers=csrf)
            assert register.status_code == 200, register.text

            # Linked, but no web baseline: even an authentic Discord user
            # cannot fabricate a completed verification.
            with pytest.raises(IdentityConflict, match="Start a 15-minute"):
                gateway.verify(ACTOR)
            with pytest.raises(IdentityError):
                gateway.verify(ACTOR2)

            initial = client.get("/v1/game/progress").json()
            assert initial["registered"] and initial["player_id"] == str(player_id)
            start = client.post("/v1/verification/start", headers=csrf, json={})
            assert start.status_code == 200, start.text
            pending = start.json()
            assert pending["state"] == "awaiting_discord"
            assert pending["player_id"] == str(player_id)
            assert pending["baseline"]["score"] == initial["score"]
            assert not pending["discord_confirmed"]
            assert pending["discord_action_count"] == 0

            # The only way to mark a Discord interaction as witnessed is
            # the server-side gateway using interaction.user.id.
            seen = gateway.verify(ACTOR)
            assert seen["state"] == "discord_confirmed"
            assert seen["discord_confirmed"]
            assert not seen["discord_gameplay_verified"]
            assert seen["discord_snapshot"]["score"] == initial["score"]
            assert client.get("/v1/verification/status").json()["discord_confirmed"]

            # Web-first activity is visible to Discord after a second /verify.
            web_key = "v294e-web-craft-123"
            web_craft = client.post("/v1/game/craft", json={"item": "fort"},
                headers={**csrf, "Idempotency-Key": web_key})
            assert web_craft.status_code == 200, web_craft.text
            web_craft_dup = client.post("/v1/game/craft", json={"item": "fort"},
                headers={**csrf, "Idempotency-Key": web_key})
            assert web_craft_dup.status_code == 200
            assert web_craft_dup.json()["repeated"]
            after_web = client.get("/v1/verification/status").json()
            assert after_web["web_action_count"] == 1
            assert after_web["discord_action_count"] == 0
            assert not after_web["web_gameplay_seen_by_discord"]
            verified_again = gateway.verify(ACTOR)
            assert verified_again["web_gameplay_seen_by_discord"]
            assert verified_again["discord_snapshot"]["inventory"]["fort"] == 1

            # A real Discord interaction crafts on the very same player ID.
            discord_craft = gateway.craft(ACTOR, "cocoa", 991234567890123456)
            assert not discord_craft["repeated"]
            duplicate = gateway.craft(ACTOR, "cocoa", 991234567890123456)
            assert duplicate["repeated"]
            after_discord = client.get("/v1/verification/status").json()
            assert after_discord["discord_gameplay_verified"]
            assert after_discord["discord_action_count"] == 1
            assert after_discord["web_action_count"] == 1
            assert after_discord["current"]["inventory"]["cocoa"] == initial["inventory"]["cocoa"] + 1
            assert after_discord["current"]["inventory"]["fort"] == 1
            assert after_discord["current"]["snowflakes"] == initial["snowflakes"]-18
            assert after_discord["delta"]["snowflakes"] == -18
            assert after_discord["player_id"] == str(player_id)

            # The original /snow EconomyEngine also uses the same canonical
            # player via UnifiedDiscordStore, not a second mirror database.
            from snowfall.services.economy import EconomyEngine
            original_bot = UnifiedDiscordStore(dsn, practice_root=tmp_path)
            legacy = EconomyEngine(original_bot).inventory(
                QA_SEASON, ACTOR, datetime.now(timezone.utc))
            assert legacy.snowflakes == after_discord["current"]["snowflakes"]
            assert legacy.quantities["cocoa"] == initial["inventory"]["cocoa"] + 1
            assert legacy.quantities["fort"] == 1

            # Shared Snow Don: a Discord attack updates the website boss
            # and the global ledger atomically, without replaying damage.
            boss = gateway.boss(ACTOR, 991234567890123457)
            boss_dup = gateway.boss(ACTOR, 991234567890123457)
            assert boss_dup["repeated"]
            web_now = client.get("/v1/game/progress").json()
            assert web_now["boss_hp"] == boss["hp_after"]
            final = client.get("/v1/verification/status").json()
            assert final["discord_action_count"] == 2
            assert final["current"]["boss_hp"] == boss["hp_after"]
            assert final["current"]["score"] == web_now["score"]

            # Identity/ledger evidence is canonical, not a duplicate profile.
            with psycopg.connect(dsn) as conn:
                assert conn.execute(
                    "SELECT COUNT(*) FROM players WHERE season_key=%s "
                    "AND discord_user_id=%s", (QA_SEASON, player_id)).fetchone()[0] == 1
                assert conn.execute(
                    "SELECT COUNT(*) FROM players WHERE season_key=%s "
                    "AND discord_user_id=%s", (QA_SEASON, ACTOR)).fetchone()[0] == 0

            # A new login session still sees the exact same principal/receipts.
            reauth = client.post("/v1/auth/underworld", json={
                "assertion": assertion("test-account", "test-character", "nonce-2")})
            assert int(reauth.json()["player_id"]) == player_id
            assert client.get("/v1/verification/status").json()["discord_action_count"] == 2

            # Expiry invalidates old proof, and a real Discord call must not
            # resurrect it or reassign another player's profile.
            with psycopg.connect(dsn) as conn:
                conn.execute(
                    "UPDATE snowfall_identity_platform_checks "
                    "SET expires_at=now()-interval '1 minute' WHERE player_id=%s",
                    (player_id,))
            assert client.get("/v1/verification/status").json()["state"] == "expired"
            with pytest.raises(IdentityConflict, match="Start a 15-minute"):
                gateway.verify(ACTOR)
            assert CrossPlatformVerifier(identity, shared, QA_SEASON).status(
                player_id)["state"] == "expired"
    finally:
        with psycopg.connect(root_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()", (db,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db)))


def test_no_shared_verification_in_prize_bearing_production():
    with pytest.raises(IdentityError, match="isolated-QA only"):
        CrossPlatformVerifier(None, None, "christmas-2026")


def test_gateway_verify_requires_single_worker_in_qa():
    gateway = DiscordBridgeGateway(None, None)
    with pytest.raises(ValueError, match="unified QA"):
        gateway.verify(ACTOR)
