"""Opt-in Railway web entrypoint for isolated Operation Snowfall QA.

The live Discord process never imports this module. A staging-secret login
is permitted only in the explicitly identified staging Railway project.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
import os
import secrets
import time

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.staging import StagingGame, prepare_web_qa, require_staging

ASSETS = Path(__file__).resolve().parent / "static"


class DemoLogin(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    slot: int = Field(ge=1, le=3)


def attach_web_ui(app: FastAPI, identities, cfg: APISettings, *, env=None) -> FastAPI:
    """Add client UI and temporary demo logins; callable with CI fakes."""
    env = dict(os.environ if env is None else env)
    require_staging(env)
    access_code = env.get("SNOWFALL_WEB_DEMO_ACCESS_CODE", "")
    if len(access_code) < 28:
        raise ValueError("WEB QA REFUSED: demo access code must be 28+ characters")
    attempts = {}
    gate = Lock()

    @app.get("/v1/web/config")
    def config():
        return {
            "version": "2.9.4", "staging": True,
            "season": cfg.season_key,
            "demo_enabled": True,
            "discord_oauth": bool(cfg.discord_client_id),
            "underworld_assertions": bool(cfg.underworld_secret),
        }

    @app.post("/v1/auth/demo")
    def demo_login(body: DemoLogin, request: Request, response: Response):
        # This route must never be present in the production web application.
        host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with gate:
            count, until = attempts.get(host, (0, now + 600))
            if until < now:
                count, until = 0, now + 600
            if count >= 6:
                raise HTTPException(429, "Too many attempts; try again later")
            if not secrets.compare_digest(body.code, access_code):
                attempts[host] = (count + 1, until)
                raise HTTPException(401, "Invalid staging access code")
            attempts.pop(host, None)
        # Test-only fictitious Underworld identities — never real account IDs.
        slot = body.slot
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        player = identities.resolve_underworld(
            f"web-qa-account-{slot}", f"web-qa-character-{slot}",
            secrets.token_urlsafe(24), expiry,
        )
        token, csrf = identities.new_session(player)
        response.set_cookie(
            "snowfall_session", token, httponly=True, secure=cfg.cookie_secure,
            samesite="lax", max_age=12 * 3600, path="/",
        )
        return {"authenticated": True, "player_id": str(player), "csrf": csrf,
                "demo_slot": slot}

    app.mount("/static", StaticFiles(directory=str(ASSETS)), name="snowfall-static")

    @app.get("/")
    def index():
        response = FileResponse(ASSETS / "index.html", media_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


def create_staging_app(env=None) -> FastAPI:
    env = dict(os.environ if env is None else env)
    require_staging(env)
    cfg = APISettings.from_env(env)
    qa_url = prepare_web_qa(env)
    cfg = replace(cfg, database_url=qa_url)
    identities = IdentityRepository(qa_url)
    store = PostgresStore(qa_url, practice_root=Path.cwd())
    shared = StagingGame(SharedGame(store, cfg.season_key))
    return attach_web_ui(create_app(cfg, identity=identities, game=shared),
                         identities, cfg, env=env)


def main():
    import uvicorn
    app = create_staging_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")),
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
