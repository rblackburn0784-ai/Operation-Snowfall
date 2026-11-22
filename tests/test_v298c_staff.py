"""v2.9.8c staff-only control centre and safety regression."""
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.platform.control_centre import control_centre_view
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.staging_web import attach_web_ui
from snowfall.platform.staging import STAGING_PROJECT, STAGING_ENVIRONMENT, QA_CONFIRM
from test_v293_platform import FakeIdentity

STAFF = "123456789012345678"
OTHER = "234567890123456789"


class StaffIdentity(FakeIdentity):
    def __init__(self, *, discord=None, underworld=True):
        super().__init__()
        self.discord = discord
        self.underworld = underworld
    def links(self, player_id):
        links = []
        if self.underworld:
            links.append({"provider": "underworld", "subject": "character-1"})
        if self.discord:
            links.append({"provider": "discord", "subject": self.discord})
        return links

    def resolve_discord(self, user_id):
        assert user_id == STAFF
        self.discord = user_id
        return 6000000000000000001


def qa_env(staff=STAFF):
    return {
        "RAILWAY_PROJECT_ID": STAGING_PROJECT,
        "RAILWAY_ENVIRONMENT_ID": STAGING_ENVIRONMENT,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "SNOWFALL_WEB_QA_CONFIRM": QA_CONFIRM,
        "SNOWFALL_API_ENABLED": "1",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_WEB_DEMO_ACCESS_CODE": "a-valid-private-demo-code-that-is-long-enough",
        "SNOWFALL_WEB_STAFF_DISCORD_IDS": staff,
    }


def test_staff_routes_require_verified_allowlisted_discord_without_underworld():
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    store = Store(__import__("tempfile").mkdtemp() + "/authstaff.sqlite3")
    store.initialize()
    now = datetime(2026,12,20,18,tzinfo=timezone.utc)
    store.ensure_season("web-qa-2026", now)
    store.register("web-qa-2026",101,"StaffFixture","Chicago",now-timedelta(days=1))
    for discord, underworld, allowed in [(STAFF, True, True),
                                         (STAFF, False, True),
                                         (OTHER, True, False),
                                         (OTHER, False, False),
                                         (None, True, False),
                                         (None, False, False)]:
        ids = StaffIdentity(discord=discord, underworld=underworld)
        app = attach_web_ui(FastAPI(), ids, cfg, env=qa_env(),
                            game=SharedGame(store,"web-qa-2026"))
        with TestClient(app, base_url="https://qa.example") as client:
            assert client.get("/v1/staff/access").json()["allowed"] is False
            assert client.get("/v1/staff/access", headers={"X-Snowfall-Discord-ID": STAFF}).json()["allowed"] is False
            assert client.get("/v1/staff/control").status_code == 401
            token,csrf = ids.new_session(6000000000000000001)
            client.cookies.set("snowfall_session", token)
            assert client.get("/v1/staff/access").json()["allowed"] is allowed
            wrong = {"X-Snowfall-Player":"999"}
            assert client.get("/v1/staff/access",headers=wrong).status_code == 409
            status = client.get("/v1/staff/control").status_code
            assert status == (200 if allowed else 403)
            assert client.post("/v1/staff/control").status_code == 405


def test_no_staff_config_is_fail_closed():
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    ids = StaffIdentity(discord=STAFF)
    app = attach_web_ui(FastAPI(), ids, cfg, env=qa_env(""),
                        game=SimpleNamespace(store=object(),season="web-qa-2026"))
    with TestClient(app, base_url="https://qa.example") as client:
        token,_ = ids.new_session(6000000000000000001)
        client.cookies.set("snowfall_session",token)
        assert client.get("/v1/staff/access").json() == {"allowed": False}
        assert client.get("/v1/staff/control").status_code == 403


def test_read_only_qa_dashboard_reflects_shared_ledger_no_prize_mutation(tmp_path):
    now = datetime(2026,12,20,18,tzinfo=timezone.utc)
    db = Store(tmp_path/"staff.sqlite3")
    db.initialize()
    db.ensure_season("qa",now)
    db.register("qa",101,"SnowDude","Chicago",now-timedelta(days=1))
    db.transition("qa",900,"start",now,"Staff QA only")
    report = control_centre_view(SharedGame(db,"qa"), now)
    assert report["read_only"] and report["scope"]=="ISOLATED_QA_ONLY"
    assert report["phase"]=="live" and report["game_day"]==1
    assert report["totals"]["players"]==1
    assert report["reconciliation_ok"]
    assert report["prize_preview"]==[]
    assert report["official_prizes_enabled"] is False
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0]==0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0]==0


def test_staff_invalid_ids_refused():
    cfg=APISettings("postgresql://unused/db","web-qa-2026","https://qa.example")
    with pytest.raises(ValueError,match="invalid staff"):
        attach_web_ui(FastAPI(),StaffIdentity(),cfg,env=qa_env("everyone"),
                      game=SimpleNamespace(store=object(),season="web-qa-2026"))


def test_discord_only_oauth_staff_access_and_play_guard(tmp_path):
    """Discord OAuth grants staff viewing, never game mutations."""
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example",
                      discord_client_id="test-client", discord_client_secret="secret",
                      discord_redirect_uri="https://qa.example/v1/auth/discord/callback")
    db = Store(tmp_path / "discord_staff.sqlite3")
    db.initialize()
    db.ensure_season("web-qa-2026", datetime(2026, 12, 20, 18, tzinfo=timezone.utc))
    identities = StaffIdentity(discord=None, underworld=False)
    game = SharedGame(db, "web-qa-2026")

    async def oauth_reply(req):
        if str(req.url).endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "verified-test-token"})
        assert req.headers.get("authorization") == "Bearer verified-test-token"
        return httpx.Response(200, json={"id": STAFF})

    oauth_client = httpx.AsyncClient(transport=httpx.MockTransport(oauth_reply))
    try:
        api = create_app(cfg, identity=identities, game=game, oauth_http=oauth_client)
        api = attach_web_ui(api, identities, cfg, env=qa_env(), game=game)
        with TestClient(api, base_url="https://qa.example", follow_redirects=False) as client:
            assert client.get("/v1/staff/access").json()["allowed"] is False
            start = client.post("/v1/auth/discord/start", json={"mode": "login"})
            assert start.status_code == 200
            url = urlsplit(start.json()["authorize_url"])
            assert url.hostname == "discord.com"
            state = parse_qs(url.query)["state"][0]
            login = client.get("/v1/auth/discord/callback", params={"code": "verified-code", "state": state})
            assert login.status_code == 303
            assert "httponly" in login.headers["set-cookie"].lower()
            session = client.get("/v1/auth/session")
            assert session.status_code == 200
            assert session.json()["links"] == [{"provider": "discord", "subject": STAFF}]
            assert client.get("/v1/staff/access").json() == {"allowed": True}
            dashboard = client.get("/v1/staff/control")
            assert dashboard.status_code == 200
            assert dashboard.json()["read_only"] is True
            assert dashboard.json()["scope"] == "ISOLATED_QA_ONLY"
            assert client.post("/v1/game/register",
                               json={"mr_username": "StaffOnly", "city": "Chicago"},
                               headers={"X-Snowfall-CSRF": "valid-csrf"}).status_code == 403
            assert client.post("/v1/staff/control").status_code == 405
    finally:
        asyncio.run(oauth_client.aclose())
