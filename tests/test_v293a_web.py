"""v2.9.3a isolated web UI, staging guard and secure demo-login contract."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from snowfall.db.store import Store
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import Session
from snowfall.platform.staging import (
    QA_CONFIRM, QA_DB, STAGING_ENVIRONMENT, STAGING_PROJECT, StagingError,
    StagingGame, _source_snapshot, database_url, require_staging,
)
from snowfall.platform.staging_web import attach_web_ui


def staging_env():
    return {
        "RAILWAY_PROJECT_ID": STAGING_PROJECT,
        "RAILWAY_ENVIRONMENT_ID": STAGING_ENVIRONMENT,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "SNOWFALL_WEB_QA_CONFIRM": QA_CONFIRM,
        "SNOWFALL_API_ENABLED": "1",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_WEB_DEMO_ACCESS_CODE": "test-private-code-with-at-least-32-bytes",
    }


def test_staging_isolation_fail_closed():
    env = staging_env()
    require_staging(env)
    for key, value in (
        ("RAILWAY_PROJECT_ID", "5e5d0e4e-730c-486c-b260-e266adf5bcbf"),
        ("RAILWAY_ENVIRONMENT_ID", "e636db32-f938-4a47-887c-ae6b5454066b"),
        ("RAILWAY_ENVIRONMENT_NAME", "production"),
        ("SNOWFALL_WEB_QA_CONFIRM", ""),
        ("SNOWFALL_API_ENABLED", "0"),
        ("SNOWFALL_DB_BACKEND", "sqlite"),
    ):
        with pytest.raises(StagingError, match="REFUSED"):
            require_staging({**env, key: value})
    with pytest.raises(StagingError, match="admin URL"):
        database_url("postgresql://tester:private@db.internal:5432/prod")
    url = database_url("postgresql://tester:private@db.internal:5432/railway")
    assert url.endswith("/" + QA_DB)


class DummyStore:
    def initialize(self):
        return None

    def season(self, name):
        assert name == "web-qa-2026"


class DummyGame:
    store = DummyStore()

    def me(self, player):
        return {"player_id": str(player), "registered": False}

    def leaderboard(self, limit):
        return [{"player_id": "42", "mr_username": "FakeMobster",
                 "city": "Chicago", "score": 0}]

    def cities(self):
        return []


class DummyIdentity:
    def __init__(self):
        self.session_token = ""
        self.player_id = 0
        self.calls = []

    def check(self):
        return None

    def resolve_underworld(self, account_id, character_id, nonce, expires_at):
        assert account_id.startswith("web-qa-account-")
        assert character_id.startswith("web-qa-character-")
        self.calls.append((account_id, character_id, nonce))
        return 6_000_000_000_000_000_001

    def new_session(self, player):
        self.player_id = player
        self.session_token = "fake-secure-test-token"
        return self.session_token, "fake-csrf"

    def session(self, token):
        return Session(self.player_id, "fake-csrf") if token and token == self.session_token else None

    def csrf_ok(self, token, csrf):
        return token == self.session_token and csrf == "fake-csrf"

    def links(self, player):
        return [{"provider": "underworld", "subject": "web-qa-character-1"}]

    def revoke(self, token):
        if token == self.session_token:
            self.session_token = ""


def test_ui_serves_without_client_side_secrets():
    env = staging_env()
    identities = DummyIdentity()
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    app = attach_web_ui(create_app(cfg, identity=identities, game=DummyGame()),
                        identities, cfg, env=env)
    with TestClient(app, base_url="https://qa.example") as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "OPERATION" in page.text and "NO PRIZES" in page.text
        assert "test-private-code" not in page.text
        css = client.get("/static/app.css")
        js = client.get("/static/app.js")
        assert css.status_code == 200 and "hero" in css.text
        assert js.status_code == 200 and "csrf" in js.text.lower()
        config = client.get("/v1/web/config").json()
        assert config["staging"] is True
        assert config["discord_oauth"] is False
        assert client.get("/v1/game/leaderboard").status_code == 200
        assert client.get("/v1/game/me").status_code == 401
        assert client.get("/v1/auth/session").status_code == 401


def test_fake_login_session_csrf_replay_and_rejection():
    env = staging_env()
    identities = DummyIdentity()
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    app = attach_web_ui(create_app(cfg, identity=identities, game=DummyGame()),
                        identities, cfg, env=env)
    with TestClient(app, base_url="https://qa.example") as client:
        bad = client.post("/v1/auth/demo", json={"code": "incorrect", "slot": 1})
        assert bad.status_code == 401
        good = client.post("/v1/auth/demo", json={
            "code": env["SNOWFALL_WEB_DEMO_ACCESS_CODE"], "slot": 1})
        assert good.status_code == 200
        assert good.json()["player_id"] == "6000000000000000001"
        assert "httponly" in good.headers["set-cookie"].lower()
        assert "secure" in good.headers["set-cookie"].lower()
        assert client.get("/v1/game/me").json()["player_id"] == "6000000000000000001"
        assert client.get("/v1/auth/session").json()["csrf"] == "fake-csrf"
        assert client.post("/v1/auth/logout").status_code == 403
        assert client.post("/v1/auth/logout", headers={
            "X-Snowfall-CSRF": "fake-csrf"}).status_code == 200
        assert client.get("/v1/game/me").status_code == 401
    assert len(identities.calls) == 1


def test_fake_login_rate_limit():
    env = staging_env()
    ids = DummyIdentity()
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    app = attach_web_ui(create_app(cfg, identity=ids, game=DummyGame()), ids, cfg, env=env)
    with TestClient(app, base_url="https://qa.example") as client:
        for _ in range(6):
            assert client.post("/v1/auth/demo", json={"code": "wrong", "slot": 1}).status_code == 401
        assert client.post("/v1/auth/demo", json={
            "code": env["SNOWFALL_WEB_DEMO_ACCESS_CODE"], "slot": 1}).status_code == 429


def test_staging_fixture_and_one_time_registration_bonus(tmp_path):
    now = datetime.now(timezone.utc)
    source = tmp_path / "fixture.sqlite3"
    _source_snapshot(source, "web-qa-2026")
    store = Store(source)
    assert store.schema_version() == 11
    assert store.season("web-qa-2026").phase(now) == "live"
    assert len(store.registrations("web-qa-2026")) == 6
    with store.connect() as db:
        db.execute("CREATE TABLE snowfall_web_qa_bonus(player_id INTEGER PRIMARY KEY)")
    facade = StagingGame(SharedGame(store, "web-qa-2026"))
    first = facade.register(6_000_000_000_000_000_001, "TestBrowser", "Chicago", now=now)
    second = facade.register(6_000_000_000_000_000_001, "TestBrowser", "Chicago", now=now)
    assert first == second
    assert facade.me(6_000_000_000_000_000_001, now=now)["resources"]["snowflakes"] == 60
    assert facade.targets(6_000_000_000_000_000_001, now=now)
