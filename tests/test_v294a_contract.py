"""v2.9.4a OAuth link conflict, state replay and unified progress contracts."""
from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient

from snowfall.platform.api import APISettings, _link_conflict_code, create_app
from snowfall.platform.discord_bridge import DiscordBridgeGateway
from snowfall.platform.identity import IdentityConflict, IdentityError, Session


class StoreStub:
    def initialize(self):
        pass

    def season(self, key):
        assert key == "web-qa-2026"


class GameStub:
    store = StoreStub()

    def progress(self, player_id):
        return {"player_id": str(player_id), "season": "web-qa-2026",
                "registered": True, "score": 17, "snowballs": 7,
                "snowflakes": 30, "warmth": 95,
                "inventory": {"cocoa": 1, "fort": 0},
                "boss_hp": 500, "boss_max_hp": 1000}

    def me(self, player_id):
        return {"player_id": str(player_id), "registered": True, "score": 17}


class IdentityStub:
    principal_id = 6_000_000_000_000_000_003

    def __init__(self):
        self.state = None
        self.consumed = False

    def check(self):
        pass

    def session(self, token):
        return Session(self.principal_id, "valid-csrf") if token == "test-session" else None

    def csrf_ok(self, token, csrf):
        return token == "test-session" and csrf == "valid-csrf"

    def links(self, player_id):
        assert player_id == self.principal_id
        return [{"provider": "underworld", "subject": "qa-character"}]

    def new_oauth_state(self, mode, session_token, verifier):
        assert mode == "link" and session_token == "test-session"
        assert len(verifier) > 40
        self.state = ("one-use-qa-oauth-state-1234567890", session_token, verifier)
        return self.state[0]

    def consume_oauth_state(self, state, session_token):
        if not self.state or self.consumed or self.state[:2] != (state, session_token):
            raise IdentityError("Expired or reused OAuth state")
        self.consumed = True
        return "link", self.principal_id, self.state[2]

    def link_discord(self, player_id, discord_subject):
        assert player_id == self.principal_id
        assert discord_subject == "555123456789"
        raise IdentityConflict("Discord account already belongs to another player")

    def principal_for_discord(self, discord_subject):
        if discord_subject == "555123456789":
            return self.principal_id
        raise IdentityError("Discord is not linked")


def config():
    return APISettings(
        "postgresql://unused/test", "web-qa-2026", "https://qa.example",
        discord_client_id="fake-client", discord_client_secret="fake-secret",
        discord_redirect_uri="https://qa.example/v1/auth/discord/callback",
    )


def test_browser_oauth_conflict_is_safe_redirect_without_account_merge():
    identity = IdentityStub()
    async def oauth_reply(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "fake-token"})
        assert request.headers["authorization"] == "Bearer fake-token"
        return httpx.Response(200, json={"id": "555123456789"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(oauth_reply))
    try:
        app = create_app(config(), identity=identity, game=GameStub(), oauth_http=http)
        with TestClient(app, base_url="https://qa.example",
                        follow_redirects=False) as client:
            assert client.get("/v1/game/progress").status_code == 401
            client.cookies.set("snowfall_session", "test-session",
                               domain="qa.example", path="/")
            assert client.get("/v1/game/progress").json()["player_id"] == str(
                identity.principal_id)
            assert client.post("/v1/auth/discord/start",
                json={"mode": "link"}).status_code == 403
            start = client.post("/v1/auth/discord/start",
                json={"mode": "link"}, headers={"X-Snowfall-CSRF": "valid-csrf"})
            assert start.status_code == 200
            args = parse_qs(urlsplit(start.json()["authorize_url"]).query)
            assert args["scope"] == ["identify"]
            assert args["code_challenge_method"] == ["S256"]
            response = client.get("/v1/auth/discord/callback", params={
                "state": args["state"][0], "code": "a-fake-code"})
            assert response.status_code == 303
            assert response.headers["location"] == ("https://qa.example/"\n                "?discord=conflict&reason=linked-elsewhere")
            assert "fake-token" not in response.headers["location"]
            assert client.get("/v1/auth/session").json()["player_id"] == str(
                identity.principal_id)
            assert client.get("/v1/game/progress").json()["score"] == 17
            assert client.get("/v1/auth/discord/callback", params={
                "state": args["state"][0], "code": "a-fake-code"}).status_code == 401
    finally:
        asyncio.run(http.aclose())


def test_oauth_conflict_diagnostics_are_fixed_and_do_not_expose_subjects():
    reasons = {
        "Discord has existing gameplay; manual review required": "gameplay",
        "Discord has existing activity; manual review required": "activity",
        "Discord account has another linked identity": "linked-elsewhere",
        "Discord belongs to another player with linked progress": "linked-elsewhere",
        "This Snowfall character already has a Discord account linked": "character-occupied",
        "Discord ID already reserved by another principal": "reserved",
        "Sign in through Underworld before linking Discord": "underworld-required",
    }
    for message, code in reasons.items():
        assert _link_conflict_code(IdentityConflict(message)) == code
    sensitive = "Unknown conflict for person 111111111111111111"
    assert _link_conflict_code(IdentityConflict(sensitive)) == "manual-review"


def test_discord_bridge_progress_is_canonical_and_rejects_unlinked_actor():
    gateway = DiscordBridgeGateway(IdentityStub(), GameStub())
    progress = gateway.progress(555123456789)
    assert progress["player_id"] == "6000000000000000003"
    assert progress["snowflakes"] == 30
    assert progress["inventory"]["cocoa"] == 1
    try:
        gateway.progress(555987654321)
        raise AssertionError("Unlinked Discord account was accepted")
    except IdentityError:
        pass
    try:
        gateway.craft(555123456789, "unknown-item", 123)
        raise AssertionError("Invalid economy item was accepted")
    except ValueError:
        pass
