"""v2.9.4c: Discord-first OAuth login can link to its real Underworld character.

Uses disposable PostgreSQL plus mocked Discord identify. Never contacts the
real Discord API or a user database; verifies conflict and takeover defenses.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.assertions import sign_underworld_assertion
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityConflict, IdentityRepository
from snowfall.platform.staging import StagingGame, _source_snapshot

SEASON = "web-qa-2026"
SECRET = "relink-test-identity-assertion-secret-0123456789"
DISCORD_USER = "123456789012345678"


def signed(account, character, nonce):
    now = int(datetime.now(timezone.utc).timestamp())
    return sign_underworld_assertion({
        "iss": "underworld", "aud": "operation-snowfall",
        "account_id": account, "character_id": character,
        "character_name": "UnderworldTester", "iat": now, "exp": now + 60,
        "jti": nonce,
    }, SECRET)


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable local CI database required")
def test_discord_first_unused_identity_relinks_to_underworld_but_progress_never_merges(tmp_path):
    import psycopg
    from psycopg import sql

    original = os.environ["SNOWFALL_PG_TEST_DSN"]
    parsed = urlsplit(original)
    if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/snowfall_test":
        pytest.fail("Refusing all non-CI PostgreSQL databases")
    db = "snowfall_v294c_reconciliation_test"
    dsn = urlunsplit(parsed._replace(path="/" + db))
    with psycopg.connect(original, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
    try:
        source = tmp_path / "source.sqlite3"
        _source_snapshot(source, SEASON)
        migrate(source, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as conn:
            conn.execute("""CREATE TABLE snowfall_web_qa_bonus(
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        identities = IdentityRepository(dsn)
        identities.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        store = PostgresStore(dsn, practice_root=tmp_path)
        game = StagingGame(SharedGame(store, SEASON))
        cfg = APISettings(
            database_url=dsn, season_key=SEASON, public_base_url="https://qa.example",
            underworld_secret=SECRET, discord_client_id="existing-discord-app",
            discord_client_secret="mock-local-only",
            discord_redirect_uri="https://qa.example/v1/auth/discord/callback")

        async def discord_http(request):
            if request.url.path.endswith("/oauth2/token"):
                fields = parse_qs(request.content.decode())
                assert fields["client_id"] == [cfg.discord_client_id]
                assert fields["code_verifier"][0]
                return httpx.Response(200, json={"access_token": "mock-oauth-token"})
            assert request.url.path.endswith("/users/@me")
            assert request.headers["authorization"] == "Bearer mock-oauth-token"
            return httpx.Response(200, json={"id": DISCORD_USER})
        http = httpx.AsyncClient(transport=httpx.MockTransport(discord_http))
        try:
            app = create_app(cfg, identity=identities, game=game, oauth_http=http)
            with TestClient(app, base_url="https://qa.example",
                            follow_redirects=False) as client:
                def authorize(mode, csrf=None):
                    headers = {"X-Snowfall-CSRF": csrf} if csrf else {}
                    response = client.post(
                        "/v1/auth/discord/start", json={"mode": mode}, headers=headers)
                    assert response.status_code == 200, response.text
                    state = parse_qs(urlsplit(
                        response.json()["authorize_url"]).query)["state"][0]
                    result = client.get("/v1/auth/discord/callback", params={
                        "state": state, "code": "oauth-code"})
                    return result

                # Reproduce the reported order: Discord login FIRST.
                first = authorize("login")
                assert first.status_code == 303
                assert first.headers["location"] == "https://qa.example/?login=ok"
                first_session = client.cookies.get("snowfall_session")
                assert client.get("/v1/auth/session").json()["player_id"] == DISCORD_USER
                assert identities.resolve_discord(DISCORD_USER) == int(DISCORD_USER)

                # Then authenticate the Underworld account normally.
                underworld = client.post("/v1/auth/underworld", json={
                    "assertion": signed("uw-account-main", "uw-character-main", "uw-login-1")})
                assert underworld.status_code == 200
                principal = int(underworld.json()["player_id"])
                assert principal > int(DISCORD_USER)
                assert identities.links(principal) == [
                    {"provider": "underworld", "subject": "uw-character-main"}]
                csrf = client.get("/v1/auth/session").json()["csrf"]
                register = client.post("/v1/game/register", json={
                    "mr_username": "MainUnderworld", "city": "Chicago"},
                    headers={"X-Snowfall-CSRF": csrf})
                assert register.status_code == 200, register.text
                before = client.get("/v1/game/progress").json()
                assert before["registered"] and before["player_id"] == str(principal)

                # The next verified Discord consent reclaims only the empty
                # Discord-first identity and leaves Underworld progress intact.
                linked = authorize("link", csrf)
                assert linked.status_code == 303
                assert linked.headers["location"] == "https://qa.example/?linked=discord"
                assert identities.principal_for_discord(DISCORD_USER) == principal
                assert client.get("/v1/game/progress").json() == before
                assert identities.session(first_session) is None
                assert identities.links(principal) == [
                    {"provider": "discord", "subject": DISCORD_USER},
                    {"provider": "underworld", "subject": "uw-character-main"},
                ]
                with psycopg.connect(dsn) as conn:
                    assert conn.execute(
                        "SELECT COUNT(*) FROM snowfall_identity_relink_audit "
                        "WHERE discord_user_id=%s AND target_player_id=%s",
                        (DISCORD_USER, principal)).fetchone()[0] == 1
                    assert conn.execute(
                        "SELECT COUNT(*) FROM snowfall_identity_principals "
                        "WHERE player_id=%s",
                        (int(DISCORD_USER),)).fetchone()[0] == 0

                # Discord can subsequently sign in as the SAME Underworld player.
                again = authorize("login")
                assert again.status_code == 303
                assert client.get("/v1/auth/session").json()["player_id"] == str(principal)
                assert client.get("/v1/game/progress").json() == before
                identities.link_discord(principal, DISCORD_USER)  # idempotent
                with psycopg.connect(dsn) as conn:
                    assert conn.execute(
                        "SELECT COUNT(*) FROM snowfall_identity_relink_audit").fetchone()[0] == 1

                # A *registered* Discord-first account must never be transferred.
                registered_discord = "234567890123456789"
                identities.resolve_discord(registered_discord)
                game.register(int(registered_discord), "AnotherDiscordPlayer", "New York")
                another = identities.resolve_underworld(
                    "uw-account-other", "uw-character-other", "uw-login-2",
                    datetime.now(timezone.utc) + timedelta(minutes=1))
                with pytest.raises(IdentityConflict, match="existing gameplay"):
                    identities.link_discord(another, registered_discord)
                assert identities.principal_for_discord(
                    registered_discord) == int(registered_discord)

                # A Discord account already attached to an Underworld character
                # must never be reassigned, even if it has no scored gameplay.
                with pytest.raises(IdentityConflict, match="another player"):
                    identities.link_discord(another, DISCORD_USER)
                assert identities.principal_for_discord(DISCORD_USER) == principal

                # An Underworld account with a different Discord link stays protected.
                claimed = "345678901234567890"
                identities.link_discord(another, claimed)
                unused = "456789012345678901"
                identities.resolve_discord(unused)
                with pytest.raises(IdentityConflict, match="already has"):
                    identities.link_discord(another, unused)
                assert identities.principal_for_discord(unused) == int(unused)

                # A Discord-only principal cannot manufacture a new link.
                orphan = "567890123456789012"
                ids = identities.resolve_discord(orphan)
                with pytest.raises(IdentityConflict, match="through Underworld"):
                    identities.link_discord(ids, unused)
        finally:
            asyncio.run(http.aclose())
    finally:
        with psycopg.connect(original, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()", (db,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db)))
