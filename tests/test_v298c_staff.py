"""v2.9.8c staff-only control centre and safety regression."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.platform.control_centre import control_centre_view
from snowfall.platform.api import APISettings
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


def test_staff_routes_require_both_underworld_and_explicit_staff_discord():
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    store = Store(__import__("tempfile").mkdtemp() + "/authstaff.sqlite3")
    store.initialize()
    now = datetime(2026,12,20,18,tzinfo=timezone.utc)
    store.ensure_season("web-qa-2026", now)
    store.register("web-qa-2026",101,"StaffFixture","Chicago",now-timedelta(days=1))
    for discord, underworld, allowed in [(STAFF, True, True),
                                         (STAFF, False, False),
                                         (OTHER, True, False),
                                         (None, True, False)]:
        ids = StaffIdentity(discord=discord, underworld=underworld)
        app = attach_web_ui(FastAPI(), ids, cfg, env=qa_env(),
                            game=SharedGame(store,"web-qa-2026"))
        with TestClient(app, base_url="https://qa.example") as client:
            assert client.get("/v1/staff/access").json()["allowed"] is False
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
