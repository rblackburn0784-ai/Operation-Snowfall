"""Shared QA lifecycle: replay safety, reset isolation and actual event clock."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from snowfall.db.store import Store
from snowfall.platform.qa_lifecycle import apply_qa_lifecycle, CONFIRMATIONS, QA_SEASON

NOW = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "qa.sqlite3")
    store.initialize()
    start = NOW - timedelta(days=9)
    store.ensure_season(QA_SEASON, start)
    store.register(QA_SEASON, 101, "SnowDude", "Chicago", start)
    store.transition(QA_SEASON, 999, "start", start, "QA fixture")
    return SimpleNamespace(season=QA_SEASON, store=store)


def act(game, action, rid="request-00000000001", **kw):
    return apply_qa_lifecycle(
        game, actor_id=999, action=action, confirmation=CONFIRMATIONS[action],
        reason="Shared QA test", request_id=rid, now=NOW, **kw)


def test_restart_expired_event_preserves_player_and_audit(game):
    assert game.store.season(QA_SEASON).phase(NOW) == "closed"
    result = act(game, "restart")
    assert result["event"]["day"] == 1 and result["gameplay_reset"]
    assert game.store.season(QA_SEASON).projected_end(NOW) == NOW + timedelta(days=7)
    assert game.store.get_player(QA_SEASON, 101).mr_username == "SnowDude"
    with game.store.connect() as con:
        assert con.execute("SELECT snowballs,warmth FROM player_resources").fetchone()[:] == (8, 100)
        assert con.execute("SELECT COUNT(*) FROM admin_audit").fetchone()[0] == 2
    assert act(game, "restart")["replayed"]
    with pytest.raises(ValueError, match="different"):
        act(game, "day", day=5)


def test_select_day_and_extend_closed_or_live(game):
    result = act(game, "extend", extension_days=2)
    assert result["event"]["phase"] == "live"
    assert result["event"]["day"] == 7
    season = game.store.season(QA_SEASON)
    assert season.projected_end(NOW) >= NOW + timedelta(days=2)
    assert season.day(NOW + timedelta(days=1)) == 7
    assert season.phase(NOW + timedelta(days=3)) == "closed"
    assert act(game, "day", rid="request-00000000002", day=4)["event"]["day"] == 4
    assert game.store.season(QA_SEASON).qa_extension_seconds == 0


def test_reset_clears_ledger_restores_resources_and_immutability(game):
    act(game, "restart")
    with game.store.connect() as con:
        con.execute("UPDATE player_resources SET snowballs=1,snowflakes=55")
        con.execute("""INSERT INTO score_ledger
            (season_key,day,player_id,city,category,points,source_key,created_at_utc)
            VALUES(?,1,101,'Chicago','pvp',4,'qa-test',?)""",
                    (QA_SEASON, NOW.isoformat()))
    act(game, "reset", rid="request-00000000002")
    with game.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT snowballs,snowflakes FROM player_resources").fetchone()[:] == (8, 0)
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                           "AND name='score_ledger_immutable_delete'").fetchone()[0] == 1


def test_other_season_and_confirmation_are_refused(game):
    game.store.ensure_season("other", NOW)
    with pytest.raises(ValueError, match="exactly one"):
        act(game, "restart")
    assert game.store.season(QA_SEASON).phase(NOW) == "closed"
    with pytest.raises(ValueError, match="confirmation"):
        apply_qa_lifecycle(game, actor_id=999, action="restart", confirmation="wrong",
                           reason="Shared QA test", request_id="request-00000000001")


def test_host_route_requires_verified_discord_csrf_and_origin(game):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from snowfall.platform.api import APISettings
    from snowfall.platform.staging_web import attach_web_ui
    from test_v298c_staff import STAFF, StaffIdentity, qa_env

    cfg = APISettings("postgresql://unused/db", QA_SEASON, "https://qa.example")
    identity = StaffIdentity(discord=STAFF, underworld=False)
    env = qa_env()
    body = {"action": "restart", "confirmation": CONFIRMATIONS["restart"],
            "reason": "Shared QA test", "request_id": "request-00000000001"}
    token, csrf = identity.new_session(6000000000000000001)
    headers = {"X-Snowfall-CSRF": csrf, "Origin": "https://qa.example"}
    for is_host in (False, True):
        if is_host:
            env["SNOWFALL_WEB_HOST_DISCORD_IDS"] = STAFF
        app = attach_web_ui(FastAPI(), identity, cfg, env=env, game=game)
        with TestClient(app, base_url="https://qa.example") as client:
            assert client.post("/v1/staff/lifecycle", json=body).status_code == 401
            client.cookies.set("snowfall_session", token)
            assert client.get("/v1/staff/role").json()["can_manage_qa_event"] is is_host
            assert client.post("/v1/staff/lifecycle", json=body).status_code == 403
            assert client.post("/v1/staff/lifecycle", json=body, headers={
                **headers, "Origin": "https://evil.example"}).status_code == 403
            result = client.post("/v1/staff/lifecycle", json=body, headers=headers)
            assert result.status_code == (200 if is_host else 403)
            if is_host:
                assert result.json()["event"]["day"] == 1
                assert client.post("/v1/staff/lifecycle", json=body,
                                   headers=headers).json()["replayed"] is True
