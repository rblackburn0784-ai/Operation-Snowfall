"""v2.9.3 API contract and platform-neutral gameplay without external credentials."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from snowfall.db.store import Store
from snowfall.platform.api import APISettings, _idempotency, create_app
from snowfall.platform.assertions import (
    AssertionError as BadAssertion, parse_underworld_assertion, sign_underworld_assertion,
)
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityConflict, Session


SECRET = "testing-only-assertion-secret-with-40-bytes"


def assertion(*, account="account-1", character="character-1", now=None):
    now = int(time.time()) if now is None else now
    return sign_underworld_assertion(
        {"iss": "underworld", "aud": "operation-snowfall",
         "account_id": account, "character_id": character, "character_name": "WinterDude",
         "iat": now, "exp": now + 60, "jti": "one-time-" + character},
        SECRET,
    )


def test_signed_underworld_assertions_are_short_lived_and_unforgeable():
    value = assertion()
    parsed = parse_underworld_assertion(value, SECRET)
    assert parsed.account_id == "account-1" and parsed.character_id == "character-1"
    with pytest.raises(BadAssertion):
        parse_underworld_assertion(value + "x", SECRET)
    with pytest.raises(BadAssertion):
        parse_underworld_assertion(value, "wrong-key-with-32-plus-characters!")
    with pytest.raises(BadAssertion):
        parse_underworld_assertion(assertion(now=int(time.time())-250), SECRET)


def test_web_config_is_opt_in_with_secure_defaults():
    required = {
        "SNOWFALL_API_ENABLED": "1",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_DATABASE_URL": "postgresql://example/db",
        "SNOWFALL_API_SEASON_KEY": "qa",
        "SNOWFALL_WEB_PUBLIC_BASE_URL": "https://snowfall.example",
    }
    with pytest.raises(ValueError, match="disabled"):
        APISettings.from_env({})
    with pytest.raises(ValueError, match="HTTPS"):
        APISettings.from_env({**required, "SNOWFALL_WEB_PUBLIC_BASE_URL": "http://snowfall.example"})
    with pytest.raises(ValueError, match="PostgreSQL"):
        APISettings.from_env({**required, "SNOWFALL_DB_BACKEND": "sqlite"})
    cfg = APISettings.from_env(required)
    assert cfg.cookie_secure
    assert cfg.cors_origins == ()


class FakeStore:
    def initialize(self):
        pass

    def season(self, key):
        assert key == "qa"


class FakeGame:
    store = FakeStore()

    def __init__(self):
        self.calls = []

    def leaderboard(self, limit=25):
        return [{"player_id": 101, "score": 9}]

    def me(self, player_id):
        return {"player_id": player_id, "registered": True, "score": 9}

    def register(self, player_id, name, city):
        self.calls.append(("register", player_id, name, city))
        return {"player_id": player_id, "mr_username": name, "city": city}

    def throw(self, player_id, target_id, style, interaction_id):
        self.calls.append(("throw", player_id, target_id, style, interaction_id))
        return {"repeated": False, "points_awarded": 13}


class FakeIdentity:
    def __init__(self):
        self.tokens = {}
        self.states = {}
        self.linked = []

    def check(self):
        pass

    def resolve_underworld(self, account_id, char_id, nonce, expiry):
        assert account_id == "account-1"
        return 6000000000000000001

    def new_session(self, player_id):
        self.tokens["valid-session"] = player_id
        return "valid-session", "valid-csrf"

    def session(self, token):
        player_id = self.tokens.get(token)
        return Session(player_id, "valid-csrf") if player_id else None

    def csrf_ok(self, token, csrf):
        return token in self.tokens and csrf == "valid-csrf"

    def revoke(self, token):
        self.tokens.pop(token, None)

    def links(self, player_id):
        return [{"provider": "underworld", "subject": "character-1"}]

    def new_oauth_state(self, mode, token, verifier):
        self.states["unique-state"] = (mode, token, verifier)
        return "unique-state"

    def consume_oauth_state(self, state, token):
        mode, original, verifier = self.states.pop(state)
        assert original == token
        principal = self.tokens.get(token) if mode == "link" else None
        return mode, principal, verifier

    def resolve_discord(self, uid):
        assert uid == "555123456789"
        return 555123456789

    def link_discord(self, player_id, uid):
        self.linked.append((player_id, uid))


def fake_settings():
    return APISettings("postgresql://unused/db", "qa", "https://snowfall.example", SECRET,
                       "fakeclient", "fakeclientsecret",
                       "https://snowfall.example/v1/auth/discord/callback")


def test_web_login_cookie_csrf_and_shared_game_actions():
    ids, game = FakeIdentity(), FakeGame()
    app = create_app(fake_settings(), identity=ids, game=game)
    with TestClient(app) as client:
        assert client.get("/v1/health").json()["backend"] == "postgres"
        assert client.get("/v1/game/leaderboard").status_code == 200
        assert client.get("/v1/game/me").status_code == 401
        result = client.post("/v1/auth/underworld", json={"assertion": assertion()})
        assert result.status_code == 200
        assert "httponly" in result.headers["set-cookie"].lower()
        assert "secure" in result.headers["set-cookie"].lower()
        assert client.get("/v1/auth/session").json()["csrf"] == "valid-csrf"
        assert client.get("/v1/game/me").json()["player_id"] == 6000000000000000001
        assert client.post("/v1/game/register", json={"mr_username": "Tester", "city": "Chicago"}).status_code == 403
        headers = {"X-Snowfall-CSRF": "valid-csrf"}
        assert client.post("/v1/game/register", json={"mr_username": "Tester", "city": "Chicago"},
                           headers=headers).status_code == 200
        assert client.post("/v1/game/throw",
                           json={"target_player_id": 99, "style": "quick"},
                           headers=headers).status_code == 400
        response = client.post("/v1/game/throw",
            json={"target_player_id": 99, "style": "quick"},
            headers={**headers, "Idempotency-Key": "unique-action-123"})
        assert response.status_code == 200
        assert game.calls[-1][-1].startswith("web:")
        assert client.post("/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/v1/game/me").status_code == 401


def test_discord_oauth_verified_identity_not_user_submitted_id():
    ids = FakeIdentity()
    async def respond(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "verified-access-token"})
        assert request.headers.get("Authorization") == "Bearer verified-access-token"
        return httpx.Response(200, json={"id": "555123456789"})
    transport = httpx.MockTransport(respond)
    async_client = httpx.AsyncClient(transport=transport)
    try:
        app = create_app(fake_settings(), identity=ids, game=FakeGame(),
                         oauth_http=async_client)
        with TestClient(app, follow_redirects=False) as client:
            start = client.post("/v1/auth/discord/start", json={"mode": "login"})
            assert start.status_code == 200
            parsed = urlsplit(start.json()["authorize_url"])
            query = parse_qs(parsed.query)
            assert query["scope"] == ["identify"]
            assert query["code_challenge_method"] == ["S256"]
            response = client.get("/v1/auth/discord/callback",
                                  params={"code": "valid-code", "state": query["state"][0]})
            assert response.status_code == 303
            assert "httponly" in response.headers["set-cookie"].lower()
            assert client.get("/v1/game/me").json()["player_id"] == 555123456789
    finally:
        import asyncio
        asyncio.run(async_client.aclose())


def test_engine_facade_shares_existing_gameplay_ids(tmp_path):
    now = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
    store = Store(tmp_path / "isolated.sqlite3")
    store.initialize()
    store.ensure_season("qa", now)
    facade = SharedGame(store, "qa")
    joined = facade.register(101, "TesterOne", "Chicago", now=now)
    assert joined["player_id"] == 101
    assert facade.me(101, now=now)["registered"]
    store.register("qa", 102, "TesterTwo", "Detroit", now)
    store.transition("qa", 900, "start", now, "QA")
    from snowfall.services.combat import CombatEngine
    CombatEngine(store).ready("qa", 101, now)
    CombatEngine(store).ready("qa", 102, now)
    assert facade.me(101, now=now)["resources"]["snowballs"] == 8
    assert facade.targets(101, now=now)[0]["player_id"] == 102
    event = facade.throw(101, 102, "quick", "qa-event", now=now)
    assert event["attacker_id"] == 101
    assert facade.me(101, now=now)["score"] == event["points_awarded"]
    assert facade.leaderboard()[0]["player_id"] == 101


def test_idempotency_key_is_scoped_to_verified_player_and_operation():
    key = "a-unique-transaction"
    a = _idempotency(101, "throw", key)
    assert a == _idempotency(101, "throw", key)
    assert a != _idempotency(102, "throw", key)
    assert a != _idempotency(101, "boss", key)
    with pytest.raises(Exception):
        _idempotency(101, "throw", "x")
