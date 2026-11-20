"""v2.9.4a: real two-adapter shared-progress test on disposable PostgreSQL.

No Discord token, production user data, Railway credential, or external
network dependency. OAuth is a trusted /users/@me mock; *gameplay* uses the
real v11 PostgreSQL engines and independent database connections.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import os
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.assertions import sign_underworld_assertion
from snowfall.platform.discord_bridge import DiscordBridgeGateway
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityConflict, IdentityRepository
from snowfall.platform.staging import StagingGame, _source_snapshot

SECRET = "shared-progress-integration-test-secret-0123456789"
SEASON = "web-qa-2026"
DISCORD_USER = 123456789012345678


def signed(account, character, nonce):
    now = int(datetime.now(timezone.utc).timestamp())
    return sign_underworld_assertion({
        "iss": "underworld", "aud": "operation-snowfall",
        "account_id": account, "character_id": character,
        "character_name": "FrostTester", "iat": now, "exp": now + 60,
        "jti": nonce,
    }, SECRET)


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable local CI PostgreSQL explicitly required")
def test_browser_discord_link_and_two_way_real_postgres_progress(tmp_path):
    import psycopg
    from psycopg import sql

    original = os.environ["SNOWFALL_PG_TEST_DSN"]
    parsed = urlsplit(original)
    if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/snowfall_test":
        pytest.fail("Refusing a database outside the ephemeral local PostgreSQL CI service")
    db_name = "snowfall_v294a_shared_progress_test"
    dsn = urlunsplit(parsed._replace(path="/" + db_name))

    with psycopg.connect(original, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    try:
        source = tmp_path / "source.sqlite3"
        _source_snapshot(source, SEASON)
        migrate(source, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as conn:
            conn.execute("""CREATE TABLE snowfall_web_qa_bonus(
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        identity = IdentityRepository(dsn)
        identity.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        identity.check()

        # A fresh game/store instance represents a separate Railway web process.
        web_game = StagingGame(SharedGame(
            PostgresStore(dsn, practice_root=tmp_path), SEASON))
        cfg = APISettings(
            database_url=dsn, season_key=SEASON,
            public_base_url="https://qa.example",
            underworld_secret=SECRET,
            discord_client_id="test-application-id",
            discord_client_secret="fake-do-not-deploy",
            discord_redirect_uri="https://qa.example/v1/auth/discord/callback",
        )
        verified_exchange = []
        def mock_discord(request):
            if request.url.path.endswith("/oauth2/token"):
                fields = parse_qs(request.content.decode("utf-8"))
                assert fields["code"] == ["mock-authorization-code"]
                assert fields["client_id"] == [cfg.discord_client_id]
                assert fields["code_verifier"][0]
                verified_exchange.append("token")
                return httpx.Response(200, json={"access_token": "mock-access-token"})
            assert request.url.path.endswith("/users/@me")
            assert request.headers["authorization"] == "Bearer mock-access-token"
            verified_exchange.append("identity")
            return httpx.Response(200, json={"id": str(DISCORD_USER)})
        mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_discord))

        try:
            app = create_app(cfg, identity=identity, game=web_game, oauth_http=mock_http)
            with TestClient(app, base_url="https://qa.example",
                            follow_redirects=False) as client:
                assert client.get("/v1/game/progress").status_code == 401
                login = client.post("/v1/auth/underworld", json={
                    "assertion": signed("qa-account-1", "qa-character-1", "qa-login-1")})
                assert login.status_code == 200
                principal_id = login.json()["player_id"]
                assert int(principal_id) >= 6_000_000_000_000_000_000
                session = client.get("/v1/auth/session").json()
                assert session["player_id"] == principal_id
                assert session["links"] == [
                    {"provider": "underworld", "subject": "qa-character-1"}]
                csrf = {"X-Snowfall-CSRF": session["csrf"]}
                assert client.post("/v1/auth/discord/start",
                    json={"mode": "link"}).status_code == 403

                registered = client.post("/v1/game/register", json={
                    "mr_username": "SnowBridgeQA", "city": "Chicago"},
                    headers=csrf)
                assert registered.status_code == 200, registered.text
                assert registered.json()["player_id"] == principal_id
                before = client.get("/v1/game/progress").json()
                assert before["registered"]
                assert before["snowflakes"] == 60
                assert before["score"] == 0
                assert before["player_id"] == principal_id
                assert before["inventory"]["cocoa"] >= 0

                started = client.post("/v1/auth/discord/start",
                                      json={"mode": "link"}, headers=csrf)
                assert started.status_code == 200
                params = parse_qs(urlsplit(started.json()["authorize_url"]).query)
                assert params["scope"] == ["identify"]
                assert params["code_challenge_method"] == ["S256"]
                state = params["state"][0]
                callback = client.get("/v1/auth/discord/callback", params={
                    "code": "mock-authorization-code", "state": state})
                assert callback.status_code == 303, callback.text
                assert callback.headers["location"] == "https://qa.example/?linked=discord"
                assert verified_exchange == ["token", "identity"]
                assert client.get("/v1/auth/discord/callback", params={
                    "code": "mock-authorization-code", "state": state}).status_code == 401
                session = client.get("/v1/auth/session").json()
                assert session["player_id"] == principal_id
                assert session["links"] == [
                    {"provider": "discord", "subject": str(DISCORD_USER)},
                    {"provider": "underworld", "subject": "qa-character-1"},
                ]
                assert identity.principal_for_discord(str(DISCORD_USER)) == int(principal_id)

                # The test-guild gateway uses a fresh PostgreSQL connection and
                # the same staging facade as the web service.
                discord_game = StagingGame(SharedGame(
                    PostgresStore(dsn, practice_root=tmp_path), SEASON))
                gateway = DiscordBridgeGateway(IdentityRepository(dsn), discord_game)
                assert gateway.progress(DISCORD_USER) == before
                assert gateway.me(DISCORD_USER)["player_id"] == principal_id

                # Discord performs a Snow Don attack. Web sees authoritative
                # damage, resource consumption and score, not a duplicated sync.
                boss = gateway.boss(DISCORD_USER, 294001)
                assert boss["kind"] == "boss"
                after_discord = client.get("/v1/game/progress").json()
                assert gateway.progress(DISCORD_USER) == after_discord
                assert after_discord["boss_hp"] == boss["hp_after"]
                repeated = gateway.boss(DISCORD_USER, 294001)
                assert repeated["repeated"]
                assert gateway.progress(DISCORD_USER) == after_discord

                # Web crafts an item and Discord immediately sees it; identical
                # Idempotency-Key must not spend currency twice.
                headers = {**csrf, "Idempotency-Key": "same-web-craft-request"}
                craft = client.post("/v1/game/craft", json={"item": "cocoa"},
                                    headers=headers)
                assert craft.status_code == 200, craft.text
                assert craft.json()["repeated"] is False
                after_web_craft = gateway.progress(DISCORD_USER)
                assert after_web_craft["inventory"]["cocoa"] == (\n                    after_discord["inventory"]["cocoa"] + 1)
                assert after_web_craft["snowflakes"] == (
                    after_discord["snowflakes"] - 8)
                replay = client.post("/v1/game/craft", json={"item": "cocoa"},
                                     headers=headers)
                assert replay.status_code == 200, replay.text
                assert replay.json()["repeated"]
                assert gateway.progress(DISCORD_USER) == after_web_craft

                # Discord crafts a second item, web verifies inventory and
                # resources without copying state between adapters.
                crafted_in_discord = gateway.craft(DISCORD_USER, "fort", 294002)
                assert not crafted_in_discord["repeated"]
                after_discord_craft = client.get("/v1/game/progress").json()
                assert after_discord_craft["inventory"]["fort"] == 1
                assert after_discord_craft["snowflakes"] == (
                    after_web_craft["snowflakes"] - 10)
                assert gateway.craft(DISCORD_USER, "fort", 294002)["repeated"]
                assert gateway.progress(DISCORD_USER) == after_discord_craft

                # Browser PvP uses the same target IDs and official resource
                # rules; results are immediately visible in Discord.
                targets = client.get("/v1/game/targets").json()["targets"]
                assert targets
                shoot = client.post("/v1/game/throw", json={
                    "target_player_id": targets[0]["player_id"],
                    "style": "quick",
                }, headers={**csrf, "Idempotency-Key": "qa-cross-channel-throw"})
                assert shoot.status_code == 200, shoot.text
                assert gateway.progress(DISCORD_USER) == (
                    client.get("/v1/game/progress").json())

                # A browser logout and fresh Underworld login must not lose
                # scores, linked identity, boss HP or purchased resources.
                saved = gateway.progress(DISCORD_USER)
                assert client.post("/v1/auth/logout", headers=csrf).status_code == 200
                assert client.get("/v1/game/progress").status_code == 401
                fresh = client.post("/v1/auth/underworld", json={
                    "assertion": signed("qa-account-1", "qa-character-1", "qa-login-2")})
                assert fresh.status_code == 200
                assert fresh.json()["player_id"] == principal_id
                assert client.get("/v1/game/progress").json() == saved

                # No second Discord account can be silently granted access
                # to this canonical character or an already linked user.
                with pytest.raises(IdentityConflict, match="already has"):
                    identity.link_discord(int(principal_id), "123456789012345679")
                second_id = identity.resolve_underworld(
                    "qa-account-2", "qa-character-2", "qa-login-3",
                    datetime.now(timezone.utc) + timedelta(minutes=1))
                with pytest.raises(IdentityConflict, match="another player"):
                    identity.link_discord(second_id, str(DISCORD_USER))
                with pytest.raises(ValueError):
                    gateway.progress(987654321012345678)

                with psycopg.connect(dsn) as conn:
                    assert conn.execute(
                        """SELECT COUNT(*) FROM snowfall_identity_links
                           WHERE provider='discord' AND player_id=%s""",
                        (int(principal_id),)).fetchone()[0] == 1
        finally:
            asyncio.run(mock_http.aclose())
    finally:
        with psycopg.connect(original, autocommit=True) as admin:
            admin.execute("""SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                             WHERE datname=%s AND pid<>pg_backend_pid()""",
                          (db_name,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
                sql.Identifier(db_name)))
