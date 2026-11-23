"""v2.9.8d — disposable staff practice: security, safety, replay and lifecycle."""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from snowfall.db.store import Store
from snowfall.platform.api import APISettings
from snowfall.platform.game import SharedGame
from snowfall.platform.staff_lab import WebStaffTestLab
from snowfall.platform.staging_web import attach_web_ui
from test_v298c_staff import STAFF, OTHER, StaffIdentity, qa_env


NOW = datetime(2026, 12, 22, 19, tzinfo=timezone.utc)
FIRST = "a" * 32
SECOND = "b" * 32


def run(lab, actor, action, day=None, confirm="", reason="QA rehearsal test",
        request_id=FIRST, session_id=None, now=NOW):
    return lab.act(actor, action, day, reason, confirm, request_id,
                   session_id, now=now)


def test_lab_days_replay_and_never_touches_shared_game(tmp_path):
    shared = Store(tmp_path / "canonical.sqlite3")
    shared.initialize()
    shared.ensure_season("web-qa-2026", NOW - timedelta(days=2))
    shared.register("web-qa-2026", 101, "SnowDude", "Chicago", NOW-timedelta(days=3))
    before = shared.audit_count("web-qa-2026")
    lab = WebStaffTestLab()
    actor = STAFF
    assert lab.snapshot(actor, now=NOW)["active"] is False
    started = run(lab, actor, "start", 3, "START TEST")
    assert started["day"] == 3 and started["active"]
    assert started["scope"] == "DISPOSABLE_WEB_TEST_LAB"
    assert started["shared_game_unchanged"] and started["discord_bot_unchanged"]
    assert started["official_prizes_enabled"] is False
    assert len(started["players"]) == 6
    assert len(started["sieges"]) == 6
    assert started["totals"]["awards"] == 0
    assert run(lab, actor, "start", 3, "START TEST") == started
    with pytest.raises(ValueError, match="different values"):
        run(lab, actor, "end", confirm="END TEST", request_id=FIRST,
            session_id=started["session_id"])
    with pytest.raises(ValueError, match="Finish the previous"):
        run(lab, actor, "start", 1, "START TEST", request_id=SECOND)
    session = started["session_id"]
    pv = run(lab, actor, "pvp", session_id=session, request_id="c"*32)
    assert pv["totals"]["pvp"] == 1
    assert pv["totals"]["awards"] == 0
    assert run(lab, actor, "pvp", session_id=session, request_id="c"*32) == pv
    with pytest.raises(ValueError, match="Type RESUPPLY TEST"):
        run(lab, actor, "resupply", session_id=session, request_id="d"*32)
    supply = run(lab, actor, "resupply", confirm="RESUPPLY TEST",
                 session_id=session, request_id="e"*32)
    assert supply["totals"]["pvp"] == 1
    boss = run(lab, actor, "boss", session_id=session, request_id="f"*32)
    assert boss["totals"]["pve"] == 1
    next_day = run(lab, actor, "day", 6, "RESET TEST DAY",
                   request_id="1"*32, session_id=session)
    assert next_day["session_id"] != session and next_day["day"] == 6
    assert next_day["totals"]["pvp"] == 0
    assert next_day["totals"]["pve"] == 0
    assert all(p["score"] == 0 for p in next_day["players"])
    with pytest.raises(ValueError, match="Test session changed"):
        run(lab, actor, "siege", request_id="2"*32, session_id=session)
    ended = run(lab, actor, "end", confirm="END TEST",
                request_id="3"*32, session_id=next_day["session_id"])
    assert not ended["active"]
    assert ended["history"][0]["action"] == "end"
    assert shared.audit_count("web-qa-2026") == before
    assert shared.get_player("web-qa-2026", 101).mr_username == "SnowDude"
    with shared.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM score_ledger WHERE season_key=?",
                           ("web-qa-2026",)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0


def test_lab_actors_are_separate_and_expire(tmp_path):
    lab = WebStaffTestLab()
    a = run(lab, STAFF, "start", 1, "START TEST")
    assert lab.snapshot(OTHER, now=NOW)["active"] is False
    b = run(lab, OTHER, "start", 7, "START TEST")
    assert b["day"] == 7 and a["day"] == 1
    assert a["session_id"] != b["session_id"]
    assert not lab.snapshot(STAFF, now=NOW+timedelta(minutes=91))["active"]
    assert not lab.snapshot(OTHER, now=NOW+timedelta(minutes=91))["active"]


def _client(tmp_path, discord=STAFF):
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    store = Store(tmp_path / "season.sqlite3")
    store.initialize()
    store.ensure_season("web-qa-2026", NOW)
    identity = StaffIdentity(discord=discord, underworld=False)
    app = attach_web_ui(FastAPI(), identity, cfg, env=qa_env(),
                        game=SharedGame(store, "web-qa-2026"))
    return TestClient(app, base_url="https://qa.example"), identity, store


def test_staff_lab_endpoints_require_verified_discord_csrf_and_origin(tmp_path):
    client, identity, shared = _client(tmp_path)
    start = dict(action="start", day=1, confirmation="START TEST",
                 reason="QA team test", request_id=FIRST)
    with client:
        assert client.get("/v1/staff/lab").status_code == 401
        assert client.post("/v1/staff/lab/action", json=start).status_code == 401
        token, csrf = identity.new_session(6000000000000000001)
        client.cookies.set("snowfall_session", token)
        assert client.get("/v1/staff/lab").status_code == 200
        assert client.post("/v1/staff/lab/action", json=start).status_code == 403
        hdr = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/staff/lab/action", json=start,
                           headers={**hdr, "Origin": "https://evil.example"}).status_code == 403
        assert client.post("/v1/staff/lab/action", json=start,
                           headers={**hdr, "X-Snowfall-Player": "999"}).status_code == 409
        response = client.post("/v1/staff/lab/action", json=start, headers=hdr)
        assert response.status_code == 200
        data = response.json()
        assert data["active"] and data["day"] == 1
        assert client.post("/v1/staff/lab/action", json=start,
                           headers=hdr).json()["session_id"] == data["session_id"]
        assert client.get("/v1/staff/control").status_code == 200
        with shared.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0


def test_unlisted_discord_and_unset_staff_allowlist_are_denied(tmp_path):
    client, identity, shared = _client(tmp_path, discord=OTHER)
    with client:
        token, csrf = identity.new_session(6000000000000000001)
        client.cookies.set("snowfall_session", token)
        assert client.get("/v1/staff/lab").status_code == 403
        assert client.post("/v1/staff/lab/action",
                           json=dict(action="start", day=1, confirmation="START TEST",
                                     reason="QA team test", request_id=FIRST),
                           headers={"X-Snowfall-CSRF": csrf}).status_code == 403
