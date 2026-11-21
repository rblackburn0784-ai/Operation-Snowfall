"""v2.9.4d — OAuth-owned Discord character discard / Underworld replacement.

Runs only in disposable localhost PostgreSQL CI, with mocked Discord identify.
No accounts are actually deleted from game history; retired accounts are
unplayable, excluded from active rankings, and retained as immutable records.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
from snowfall.platform.discard import DiscardService, QA_SEASON, CONFIRM_PHRASE
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityError, IdentityRepository
from snowfall.platform.staging import StagingGame, _source_snapshot

DISCORD_USER = "123456789012345678"
SECRET = "verified-ownership-discard-test-secret-0123456789"


def signed(account, character, nonce):
    now = int(datetime.now(timezone.utc).timestamp())
    return sign_underworld_assertion({
        "iss": "underworld", "aud": "operation-snowfall",
        "account_id": account, "character_id": character,
        "character_name": "UnderworldKeeper", "iat": now, "exp": now + 60,
        "jti": nonce,
    }, SECRET)


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable localhost CI PostgreSQL explicitly required")
def test_verified_discord_retirement_retains_underworld_and_immutable_audit(tmp_path):
    import psycopg
    from psycopg import sql

    admin_dsn = os.environ["SNOWFALL_PG_TEST_DSN"]
    parts = urlsplit(admin_dsn)
    if parts.hostname not in ("localhost", "127.0.0.1") or parts.path != "/snowfall_test":
        pytest.fail("Refusing non-test Postgres")
    name = "snowfall_v294d_discard_test"
    dsn = urlunsplit(parts._replace(path="/" + name))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        source = tmp_path / "source.sqlite3"
        _source_snapshot(source, QA_SEASON)
        migrate(source, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as conn:
            conn.execute("""CREATE TABLE snowfall_web_qa_bonus(
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        identity = IdentityRepository(dsn)
        identity.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        store = PostgresStore(dsn, practice_root=tmp_path)
        game = StagingGame(SharedGame(store, QA_SEASON))
        cfg = APISettings(
            database_url=dsn, season_key=QA_SEASON,
            public_base_url="https://qa.example", underworld_secret=SECRET,
            discord_client_id="existing-discord-application",
            discord_client_secret="local-fake-secret",
            discord_redirect_uri="https://qa.example/v1/auth/discord/callback",
        )
        async def discord_http(request):
            if request.url.path.endswith("/oauth2/token"):
                fields = parse_qs(request.content.decode())
                assert fields["code_verifier"][0]
                assert fields["client_id"] == [cfg.discord_client_id]
                return httpx.Response(200, json={"access_token": "oauth-test"})
            assert request.url.path.endswith("/users/@me")
            assert request.headers["authorization"] == "Bearer oauth-test"
            return httpx.Response(200, json={"id": DISCORD_USER})
        http = httpx.AsyncClient(transport=httpx.MockTransport(discord_http))

        try:
            app = create_app(cfg, identity=identity, game=game, oauth_http=http)
            with TestClient(app, base_url="https://qa.example",
                            follow_redirects=False) as client:
                def authorize(mode, csrf=None):
                    response = client.post("/v1/auth/discord/start",
                                           json={"mode": mode},
                                           headers={"X-Snowfall-CSRF": csrf} if csrf else {})
                    assert response.status_code == 200, response.text
                    query = parse_qs(urlsplit(response.json()["authorize_url"]).query)
                    assert query["scope"] == ["identify"]
                    return client.get("/v1/auth/discord/callback", params={
                        "state": query["state"][0], "code": "mock-code"})

                first = authorize("login")
                assert first.status_code == 303
                assert client.get("/v1/auth/session").json()["player_id"] == DISCORD_USER
                old_session = client.cookies.get("snowfall_session")
                current = client.get("/v1/auth/session").json()
                old_csrf = {"X-Snowfall-CSRF": current["csrf"]}
                old_registration = client.post("/v1/game/register", headers=old_csrf, json={
                    "mr_username": "DiscardThisDiscord", "city": "Detroit"})
                assert old_registration.status_code == 200, old_registration.text
                # Write real immutable score history for the profile to lose.
                with store.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("""INSERT INTO score_ledger(season_key,day,player_id,
                        city,category,points,source_key,created_at_utc)
                        VALUES(?,?,?,?,?,?,?,?)""",
                        (QA_SEASON, 1, int(DISCORD_USER), "Detroit", "quest",
                         17, "discard-test-award", datetime.now(timezone.utc).isoformat()))
                old_score = game.progress(int(DISCORD_USER))
                assert old_score["registered"]
                assert old_score["score"] == 17
                assert old_score["snowflakes"] == 60

                signed_in = client.post("/v1/auth/underworld", json={
                    "assertion": signed("uw-keeper-account", "uw-keeper-character", "uw-login-1")})
                assert signed_in.status_code == 200, signed_in.text
                target = int(signed_in.json()["player_id"])
                csrf = {"X-Snowfall-CSRF": client.get("/v1/auth/session").json()["csrf"]}
                assert target != int(DISCORD_USER)
                created = client.post("/v1/game/register", json={
                    "mr_username": "KeepThisUnderworld", "city": "Chicago"}, headers=csrf)
                assert created.status_code == 200, created.text
                kept = client.get("/v1/game/progress").json()
                assert kept["player_id"] == str(target)
                assert kept["score"] == 0
                assert kept["snowflakes"] == 60

                # The initial OAuth link does not discard a thing.
                blocked = authorize("link", csrf["X-Snowfall-CSRF"])
                assert blocked.status_code == 303
                assert blocked.headers["location"] == "https://qa.example/?discord=discard-offer"
                assert client.cookies.get("snowfall_discard_challenge")
                assert identity.principal_for_discord(DISCORD_USER) == int(DISCORD_USER)
                assert game.progress(int(DISCORD_USER)) == old_score

                preview = client.get("/v1/auth/discord/discard/preview")
                assert preview.status_code == 200, preview.text
                data = preview.json()
                assert data["keep"]["name"] == "KeepThisUnderworld"
                assert data["discard"]["name"] == "DiscardThisDiscord"
                assert data["discard"]["score"] == 17
                assert data["discard"]["snowflakes"] == 60
                assert "NOT move" in data["warning"]
                assert client.post("/v1/auth/discord/discard/confirm", json={
                    "acknowledged_loss": True, "confirmation": CONFIRM_PHRASE}).status_code == 403
                assert client.post("/v1/auth/discord/discard/confirm", headers=csrf, json={
                    "acknowledged_loss": False, "confirmation": CONFIRM_PHRASE}).status_code == 422
                assert client.post("/v1/auth/discord/discard/confirm", headers=csrf, json={
                    "acknowledged_loss": True, "confirmation": "DELETE"}).status_code == 422
                assert identity.principal_for_discord(DISCORD_USER) == int(DISCORD_USER)

                # Progress changed after the confirmation screen was shown:
                # no silent loss; user must re-verify OAuth and review again.
                with store.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("""UPDATE player_resources
                        SET snowflakes=snowflakes+1 WHERE season_key=?
                        AND discord_user_id=?""", (QA_SEASON, int(DISCORD_USER)))
                changed = client.post("/v1/auth/discord/discard/confirm", headers=csrf, json={
                    "acknowledged_loss": True, "confirmation": CONFIRM_PHRASE})
                assert changed.status_code == 409
                assert "changed since preview" in changed.json()["detail"]
                assert identity.principal_for_discord(DISCORD_USER) == int(DISCORD_USER)

                again = authorize("link", csrf["X-Snowfall-CSRF"])
                assert again.headers["location"] == "https://qa.example/?discord=discard-offer"
                assert client.get("/v1/auth/discord/discard/preview").json()[
                    "discard"]["snowflakes"] == 61
                final = client.post("/v1/auth/discord/discard/confirm", headers=csrf, json={
                    "acknowledged_loss": True, "confirmation": CONFIRM_PHRASE})
                assert final.status_code == 200, final.text
                assert final.json()["linked"]
                assert final.json()["kept_player_id"] == str(target)
                assert final.json()["retired_character"] == "DiscardThisDiscord"
                assert final.json()["discarded_points"] == 17
                assert identity.principal_for_discord(DISCORD_USER) == target
                assert client.get("/v1/auth/discord/discard/preview").status_code == 401
                assert client.post("/v1/auth/discord/discard/confirm", headers=csrf, json={
                    "acknowledged_loss": True, "confirmation": CONFIRM_PHRASE}).status_code == 401
                assert client.get("/v1/game/progress").json() == kept
                assert identity.session(old_session) is None

                # Historical immutable scores stay, active rankings exclude the
                # disqualified profile, and the old username is available.
                with psycopg.connect(dsn) as conn:
                    row = conn.execute("""SELECT mr_username,review_state FROM players
                                         WHERE season_key=%s AND discord_user_id=%s""",
                                       (QA_SEASON, int(DISCORD_USER))).fetchone()
                    assert row == ("Retired-" + DISCORD_USER, "disqualified")
                    assert conn.execute("""SELECT COALESCE(SUM(points),0) FROM score_ledger
                        WHERE season_key=%s AND player_id=%s""",
                        (QA_SEASON, int(DISCORD_USER))).fetchone()[0] == 17
                    audit = conn.execute("""SELECT old_character_name,points_discarded,
                        target_player_id FROM snowfall_identity_discard_audit""").fetchall()
                    assert audit == [("DiscardThisDiscord", 17, target)]
                ranks = game.leaderboard(limit=50)
                assert all(x["player_id"] != DISCORD_USER for x in ranks)

                assert client.post("/v1/auth/logout", headers=csrf).status_code == 200
                discord_login = authorize("login")
                assert discord_login.status_code == 303
                assert client.get("/v1/auth/session").json()["player_id"] == str(target)
                assert client.get("/v1/game/progress").json() == kept
        finally:
            asyncio.run(http.aclose())
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                          "WHERE datname=%s AND pid<>pg_backend_pid()", (name,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def test_production_discard_opt_out():
    with pytest.raises(IdentityError, match="only enabled in isolated QA"):
        DiscardService(None, "christmas-2026")
