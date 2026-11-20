"""v2.9.4: cross-origin Underworld login and verified Discord identity contracts."""
from __future__ import annotations

from datetime import datetime, timezone
import time

from fastapi.testclient import TestClient
import pytest

from snowfall.platform.api import APISettings, create_app
from snowfall.platform.assertions import sign_underworld_assertion
from snowfall.platform.discord_bridge import DiscordBridgeGateway, validate_bridge_environment
from snowfall.platform.identity import IdentityError, Session
from snowfall.platform.staging import STAGING_PROJECT, STAGING_ENVIRONMENT


SECRET = "test-cross-platform-shared-secret-of-64-plus-characters-0123456789"
UNDERWORLD = "https://underworld-stage.example"
WEB = "https://snowfall-web-qa-staging.up.railway.app"


class FakeStore:
    def initialize(self):
        pass

    def season(self, key):
        assert key == "web-qa-2026"


class FakeGame:
    store = FakeStore()

    def me(self, principal):
        return {"player_id": str(principal), "registered": False}

    def throw(self, principal, target, style, iid):
        return {"attacker_id": str(principal), "target_id": str(target),
                "style": style, "interaction_id": iid, "hit": True,
                "points_awarded": 4, "repeated": False}

    def boss(self, principal, iid):
        return {"player_id": str(principal), "interaction_id": iid, "damage": 12}

    def siege(self, principal, iid):
        return {"player_id": str(principal), "interaction_id": iid, "damage": 7}

    def leaderboard(self, limit=10):
        return []

    def ready(self, principal):
        return {"principal": principal}

    def targets(self, principal):
        return [{"player_id": "9000000000000000000", "city": "Chicago"}]


class FakeIdentity:
    def __init__(self):
        self.used = set()
        self.sessions = {}
        self.next_player = 6000000000000000001

    def check(self):
        pass

    def resolve_underworld(self, account, character, nonce, expiry):
        if nonce in self.used:
            raise IdentityError("Assertion replay blocked")
        self.used.add(nonce)
        assert account == "1"
        assert character == "2"
        return self.next_player

    def new_session(self, principal):
        token = "hardened-random-token-for-test"
        self.sessions[token] = principal
        return token, "csrf-value"

    def session(self, token):
        p = self.sessions.get(token)
        return Session(p, "csrf-value") if p else None

    def links(self, principal):
        return [{"provider": "underworld", "subject": "2"}]

    def principal_for_discord(self, discord_id):
        if discord_id != "123456":
            raise IdentityError("Not verified by Discord OAuth")
        return self.next_player


def _assertion(nonce):
    now = int(time.time())
    return sign_underworld_assertion({
        "iss": "underworld", "aud": "operation-snowfall",
        "account_id": "1", "character_id": "2", "character_name": "Gable",
        "iat": now, "exp": now + 60, "jti": nonce,
    }, SECRET)


def _cfg():
    return APISettings("postgresql://unused/db", "web-qa-2026", WEB,
                       underworld_secret=SECRET, underworld_origin=UNDERWORLD)


def test_handoff_rejects_untrusted_origin_invalid_content_and_replay():
    ids = FakeIdentity()
    app = create_app(_cfg(), identity=ids, game=FakeGame())
    with TestClient(app, base_url=WEB, follow_redirects=False) as client:
        data = {"assertion": _assertion("unique-bridge-auth-nonce")}
        rejected = client.post("/v1/auth/underworld/handoff", data=data,
                               headers={"Origin": "https://unknown.example"})
        assert rejected.status_code == 403
        rejected = client.post("/v1/auth/underworld/handoff", json=data,
                               headers={"Origin": UNDERWORLD})
        assert rejected.status_code == 415
        good = client.post("/v1/auth/underworld/handoff", data=data,
                           headers={"Origin": UNDERWORLD})
        assert good.status_code == 303
        assert good.headers["location"] == WEB + "/"
        assert "httponly" in good.headers["set-cookie"].lower()
        assert "secure" in good.headers["set-cookie"].lower()
        assert "no-store" in good.headers["cache-control"]
        assert client.get("/v1/auth/session").json()["player_id"] == (
            "6000000000000000001")
        second = client.post("/v1/auth/underworld/handoff", data=data,
                             headers={"Origin": UNDERWORLD})
        assert second.status_code == 401
        wrong = client.post("/v1/auth/underworld/handoff",
                            data={"assertion": _assertion("bad") + "junk"},
                            headers={"Origin": UNDERWORLD})
        assert wrong.status_code == 401
        assert len(ids.used) == 1


def test_handoff_disabled_without_shared_credentials():
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", WEB)
    app = create_app(cfg, identity=FakeIdentity(), game=FakeGame())
    with TestClient(app, base_url=WEB) as client:
        assert client.post("/v1/auth/underworld/handoff", data={
            "assertion": _assertion("disabled")},
            headers={"Origin": UNDERWORLD}).status_code == 503


def test_configuration_requires_both_issuer_and_trusted_origin():
    env = {"SNOWFALL_API_ENABLED": "1", "SNOWFALL_DB_BACKEND": "postgres",
           "SNOWFALL_DATABASE_URL": "postgresql://test/test",
           "SNOWFALL_API_SEASON_KEY": "web-qa-2026",
           "SNOWFALL_WEB_PUBLIC_BASE_URL": WEB,
           "SNOWFALL_UNDERWORLD_ASSERTION_SECRET": SECRET}
    with pytest.raises(ValueError, match="both secret"):
        APISettings.from_env(env)
    env["SNOWFALL_UNDERWORLD_TRUSTED_ORIGIN"] = UNDERWORLD
    cfg = APISettings.from_env(env)
    assert cfg.underworld_origin == UNDERWORLD


def test_discord_gateway_uses_verified_canonical_principal():
    gateway = DiscordBridgeGateway(FakeIdentity(), FakeGame())
    p = gateway.principal(123456)
    assert p == 6000000000000000001
    assert gateway.me(123456)["player_id"] == str(p)
    result = gateway.throw(123456, "9000000000000000000", "quick", 900)
    assert result["attacker_id"] == str(p)
    assert result["interaction_id"] == "discord-bridge:900"
    with pytest.raises(IdentityError):
        gateway.boss(999999, 901)
    with pytest.raises(ValueError, match="player ID"):
        gateway.throw(123456, "not-a-player-id", "quick", 902)
    with pytest.raises(ValueError, match="Invalid player ID"):
        gateway.throw(123456, "9999999999999999999", "quick", 902)


def test_discord_bridge_cannot_start_as_live_bot():
    good = {"SNOWFALL_DISCORD_BRIDGE_ENABLED": "1",
            "RAILWAY_PROJECT_ID": STAGING_PROJECT,
            "RAILWAY_ENVIRONMENT_ID": STAGING_ENVIRONMENT,
            "RAILWAY_ENVIRONMENT_NAME": "staging",
            "SNOWFALL_API_SEASON_KEY": "web-qa-2026",
            "SNOWFALL_DATABASE_URL": "postgresql://tester:pass@localhost/railway",
            "SNOWFALL_DISCORD_BRIDGE_TOKEN": "testing-bot-token",
            "SNOWFALL_DISCORD_BRIDGE_GUILD_ID": "987654321"}
    assert validate_bridge_environment(good)[1] == 987654321
    for key, value in (
        ("SNOWFALL_DISCORD_BRIDGE_ENABLED", ""),
        ("RAILWAY_PROJECT_ID", "live-project"),
        ("SNOWFALL_DISCORD_BRIDGE_TOKEN", ""),
        ("SNOWFALL_DISCORD_BRIDGE_GUILD_ID", "0"),
        ("SNOWFALL_API_SEASON_KEY", "christmas-2026"),
    ):
        with pytest.raises(ValueError):
            validate_bridge_environment({**good, key: value})
    with pytest.raises(ValueError):
        validate_bridge_environment({**good,
            "DISCORD_TOKEN": good["SNOWFALL_DISCORD_BRIDGE_TOKEN"]})
