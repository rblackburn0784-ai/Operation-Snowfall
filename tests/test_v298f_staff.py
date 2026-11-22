"""v2.9.8f — staff player investigation, role separation and review safety."""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from snowfall.db.store import Store
from snowfall.platform.api import APISettings
from snowfall.platform.game import SharedGame
from snowfall.platform.staff_operations import (
    apply_player_review, player_directory, player_dossier)
from snowfall.platform.staging_web import attach_web_ui
from test_v298c_staff import STAFF, StaffIdentity, qa_env

SEASON = "web-qa-2026"
TIME = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
RID = "qa-review-request-0123456789"


@pytest.fixture()
def qa(tmp_path):
    db = Store(tmp_path / "isolated_qa.sqlite3")
    db.initialize()
    db.ensure_season(SEASON, TIME)
    db.register(SEASON, 101, "SNOW_DUDE", "Chicago", TIME-timedelta(hours=1))
    db.register(SEASON, 102, "SNOWXDUDE", "Detroit", TIME-timedelta(hours=1))
    db.register(SEASON, 103, "CaseThree", "Chicago", TIME-timedelta(hours=1))
    return SharedGame(db, SEASON)


def test_search_is_parameterized_literal_filtered_and_season_scoped(qa):
    report = player_directory(qa, query="SNOW_", page=1)
    assert report["total"] == 1 and report["players"][0]["mr_username"] == "SNOW_DUDE"
    assert player_directory(qa, query="SNOW%", city="Chicago")["total"] == 0
    assert player_directory(qa, city="Detroit")["total"] == 1
    assert player_directory(qa, state="flagged")["total"] == 0
    for kwargs in ({"page": 101}, {"city": "London"}, {"state": "new"},
                   {"query": "x" * 61}):
        with pytest.raises(ValueError):
            player_directory(qa, **kwargs)
    with pytest.raises(ValueError, match="isolated QA"):
        player_directory(SharedGame(qa.store, "real-season"))


def test_dossier_has_durable_activity_and_account_specific_alerts(qa):
    with qa.store.connect() as con:
        con.execute("""INSERT INTO score_ledger
          (season_key,day,player_id,city,category,points,source_key,created_at_utc)
          VALUES(?,?,?,?,?,?,?,?)""",
          (SEASON, 1, 101, "Chicago", "quest", 20, "test:quest:101", TIME.isoformat()))
    dossier = player_dossier(qa, 101)
    assert dossier["profile"]["player_id"] == "101"
    assert dossier["profile"]["score"] == 20
    assert dossier["score_history"][0]["points"] == 20
    assert dossier["links"] == {"underworld": None, "discord": None}
    assert dossier["alerts"] == []
    assert dossier["read_only"] is True
    with pytest.raises(ValueError, match="not registered"):
        player_dossier(qa, 999)


def test_host_review_is_audited_replay_safe_and_never_changes_ledger(qa):
    first = apply_player_review(qa, actor_id=int(STAFF), player_id=101,
                                action="flag", expected_state="self_declared",
                                confirmation="FLAG QA PLAYER",
                                reason="Investigate anomalous snowball history",
                                request_id=RID, now=TIME)
    assert first["audit_written"] and first["review_state"] == "flagged"
    assert qa.store.get_player(SEASON, 101).review_state == "flagged"
    repeated = apply_player_review(qa, actor_id=int(STAFF), player_id=101,
                                   action="flag", expected_state="self_declared",
                                   confirmation="FLAG QA PLAYER",
                                   reason="Investigate anomalous snowball history",
                                   request_id=RID, now=TIME)
    assert repeated["replayed"] is True and not repeated["audit_written"]
    with pytest.raises(ValueError, match="already used"):
        apply_player_review(qa, actor_id=int(STAFF), player_id=102, action="flag",
                            expected_state="self_declared", confirmation="FLAG QA PLAYER",
                            reason="Evidence on another player account", request_id=RID)
    with pytest.raises(ValueError, match="changed"):
        apply_player_review(qa, actor_id=int(STAFF), player_id=101, action="clear",
                            expected_state="self_declared", confirmation="CLEAR QA PLAYER",
                            reason="Conflicting stale browser review", request_id=RID+"-new")
    with pytest.raises(ValueError, match="Typed confirmation"):
        apply_player_review(qa, actor_id=int(STAFF), player_id=101, action="clear",
                            expected_state="flagged", confirmation="NO",
                            reason="Investigated flagged player evidence", request_id=RID+"-wrong")
    cleared = apply_player_review(qa, actor_id=int(STAFF), player_id=101, action="clear",
                                  expected_state="flagged", confirmation="CLEAR QA PLAYER",
                                  reason="Investigation completed: no violation",
                                  request_id=RID+"-clear", now=TIME)
    assert cleared["review_state"] == "cleared"
    with qa.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM admin_audit WHERE season_key=?",
                           (SEASON,)).fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM score_ledger WHERE season_key=?",
                           (SEASON,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards WHERE season_key=?",
                           (SEASON,)).fetchone()[0] == 0


def test_review_unavailable_after_finalization(qa):
    with qa.store.connect() as con:
        con.execute("UPDATE season_state SET finalized_at_utc=? WHERE season_key=?",
                    (TIME.isoformat(), SEASON))
    with pytest.raises(ValueError, match="finalized"):
        apply_player_review(qa, actor_id=int(STAFF), player_id=101, action="flag",
                            expected_state="self_declared", confirmation="FLAG QA PLAYER",
                            reason="This review must be refused once finalized",
                            request_id=RID)


def test_web_permissions_csrf_origin_confirmation_and_host_allowlist(qa):
    cfg = APISettings("postgresql://unused/db", SEASON, "https://qa.example")
    ids = StaffIdentity(discord=STAFF, underworld=False)
    env = qa_env()
    app = attach_web_ui(FastAPI(), ids, cfg, env=env, game=qa)
    review = dict(player_id="101", action="flag", expected_state="self_declared",
                  confirmation="FLAG QA PLAYER",
                  reason="Manual check of reported suspicious scoring",
                  request_id=RID)
    with TestClient(app, base_url="https://qa.example") as client:
        assert client.get("/v1/staff/players").status_code == 401
        assert client.get("/v1/staff/role").status_code == 401
        token,csrf = ids.new_session(6000000000000000001)
        client.cookies.set("snowfall_session", token)
        assert client.get("/v1/staff/role").json()["role"] == "organiser"
        assert client.get("/v1/staff/players").json()["total"] == 3
        assert client.get("/v1/staff/players/101").json()["profile"]["player_id"] == "101"
        assert client.get("/v1/staff/players/999").status_code == 404
        assert client.post("/v1/staff/players/review", json=review,
                           headers={"X-Snowfall-CSRF": csrf}).status_code == 403
    env["SNOWFALL_WEB_HOST_DISCORD_IDS"] = STAFF
    app = attach_web_ui(FastAPI(), ids, cfg, env=env, game=qa)
    with TestClient(app, base_url="https://qa.example") as client:
        client.cookies.set("snowfall_session", token)
        assert client.get("/v1/staff/role").json()["can_review"] is True
        assert client.post("/v1/staff/players/review", json=review).status_code == 403
        assert client.post("/v1/staff/players/review", json=review,
                           headers={"X-Snowfall-CSRF": csrf,
                                    "Origin": "https://evil.example"}).status_code == 403
        assert client.post("/v1/staff/players/review", json=review,
                           headers={"X-Snowfall-CSRF": csrf,
                                    "X-Snowfall-Player": "987"}).status_code == 409
        result = client.post("/v1/staff/players/review", json=review,
                             headers={"X-Snowfall-CSRF": csrf,
                                      "Origin": "https://qa.example"})
        assert result.status_code == 200 and result.json()["audit_written"]
        assert client.post("/v1/staff/players/review", json=review,
                           headers={"X-Snowfall-CSRF": csrf}).json()["replayed"] is True
    assert qa.store.get_player(SEASON, 101).review_state == "flagged"


def test_host_role_requires_existing_staff_allowlist(qa):
    cfg = APISettings("postgresql://unused/db", SEASON, "https://qa.example")
    bad = qa_env()
    bad["SNOWFALL_WEB_HOST_DISCORD_IDS"] = "999999999999999999"
    with pytest.raises(ValueError, match="subset of staff"):
        attach_web_ui(FastAPI(), StaffIdentity(discord=STAFF), cfg,
                      env=bad, game=qa)


def test_admin_ui_includes_player_review_without_exposing_prize_mutations():
    from snowfall.platform.staging_web import ASSETS
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    for element in ("staffPlayerSearchForm", "staffPlayerResults",
                    "staffPlayerDossier", "staffReviewForm", "staffPlayerExport"):
        assert f'id="{element}"' in html
    assert "/v1/staff/players/review" in js
    assert "/v1/staff/role" in js
    assert "CLEAR QA PLAYER" in js and "FLAG QA PLAYER" in js
