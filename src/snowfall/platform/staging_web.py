"""Opt-in Railway web entrypoint for isolated Operation Snowfall QA.

The live Discord process never imports this module. A staging-secret login
is permitted only in the explicitly identified staging Railway project.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
import mimetypes
import os
import re
import secrets
import time

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.release import VERSION
from snowfall.platform.staging import StagingGame, prepare_web_qa, require_staging

ASSETS = Path(__file__).resolve().parent / "static"
ART = Path(__file__).resolve().parents[1] / "graphics" / "art"


def safe_streets_url(value: str) -> str:
    """Allow links to a specific Discord guild text channel, not arbitrary URLs.

    This is a read-only external link, never a Discord chat relay or bot token.
    """
    raw = (value or "").strip()
    try:
        url = urlsplit(raw)
    except ValueError:
        return ""
    if (url.scheme != "https" or url.netloc != "discord.com" or
            url.query or url.fragment or
            not re.fullmatch(r"/channels/[0-9]{15,25}/[0-9]{15,25}", url.path)):
        return ""
    return raw



class DemoLogin(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    slot: int = Field(ge=1, le=3)


def attach_web_ui(app: FastAPI, identities, cfg: APISettings, *, env=None, game=None) -> FastAPI:
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
        from snowfall.services.combat import ATTACKS, DAILY_PVP_CAP
        from snowfall.services.economy import ITEM_COSTS, ITEM_CAPS
        from snowfall.services.world import BOSS_LIMIT, SIEGE_LIMIT, BOSS_CAP, SIEGE_CAP
        from snowfall.services.territory import schedule_for_day
        return {
            "version": VERSION, "staging": True,
            "branding": {"banner": (ASSETS / "snowfall-site-banner.webp").is_file(),
                         "icon": (ASSETS / "snowfall-site-icon.webp").is_file(),
                         "title": (ASSETS / "snowfall-title.png").is_file(),
                         "city_header": (ASSETS / "snowfall-header-city.webp").is_file(),
                         "wallpaper": (ASSETS / "snowfall-city-wallpaper.webp").is_file(),
                         "wire_template": (ASSETS / "snowfall-wire-frontpage.webp").is_file()},
            "web_artwork_version": "2.9.7c",
            "season": cfg.season_key,
            "demo_enabled": True,
            "underworld_url": cfg.underworld_origin,
            "rival_schedule": {day: schedule_for_day(day) for day in range(1, 8)},
            "play_rules": {"pvp_cap": DAILY_PVP_CAP, "boss_limit": BOSS_LIMIT,
                           "siege_limit": SIEGE_LIMIT, "boss_cap": BOSS_CAP,
                           "siege_cap": SIEGE_CAP, "styles": ATTACKS,
                           "craft_costs": ITEM_COSTS, "item_caps": ITEM_CAPS},
            "discord_oauth": bool(cfg.discord_client_id),
            "underworld_assertions": bool(cfg.underworld_secret),
            "streets_url": safe_streets_url(env.get("SNOWFALL_DISCORD_STREETS_URL", "")),
        }

    @app.get("/v1/web/boss")
    def boss_visual_status(response: Response):
        from snowfall.platform.boss_visuals import current_boss
        if game is None:
            raise HTTPException(503, "Boss visual status unavailable")
        response.headers["Cache-Control"] = "no-store"
        return current_boss(game)

    @app.get("/v1/web/territory")
    def territory_status(response: Response, day: int | None = Query(default=None, ge=1, le=7)):
        from snowfall.services.territory import TerritoryEngine, TerritoryError
        if game is None:
            raise HTTPException(503, "City Wars unavailable")
        try:
            board = TerritoryEngine(game.store).public_board(
                game.season, datetime.now(timezone.utc), day=day)
        except TerritoryError as exc:
            raise HTTPException(400, str(exc)) from exc
        response.headers["Cache-Control"] = "no-store"
        return {"day": board.day, "current_day": board.current_day, "phase": board.phase,
                "banners": [asdict(b) for b in board.banners],
                "matches": [asdict(m) for m in board.matches],
                "districts": [asdict(d) for d in board.districts],
                "honorary_only": True}

    @app.get("/v1/web/wire")
    def wire_status(response: Response, day: int | None = Query(default=None, ge=1, le=7)):
        from snowfall.platform.wire_view import wire_view
        from snowfall.services.wire import WireError
        if game is None:
            raise HTTPException(503, "Snowfall Wire unavailable")
        try:
            result = wire_view(game, day=day)
        except WireError as exc:
            raise HTTPException(400, str(exc)) from exc
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.post("/v1/auth/demo")
    def demo_login(body: DemoLogin, request: Request, response: Response):
        # This route must never be present in the production web application.
        host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with gate:
            # Bound transient unauthenticated rate-limit state without evicting
            # active blocked clients. Never trust arbitrary forwarded IP headers.
            for expired in [key for key, (_, end) in attempts.items() if end <= now]:
                attempts.pop(expired, None)
            if host not in attempts and len(attempts) >= 4096:
                raise HTTPException(429, "Too many attempts; try again later")
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

    # Reuse the artwork already bundled with the existing Discord bot. Mount
    # only the public art directory; no user data or game-write endpoint.
    # Slim Linux images may omit the system WebP MIME mapping. Register it
    # explicitly so both the original art and new branding decode in browsers.
    mimetypes.add_type("image/webp", ".webp", strict=True)
    app.mount("/art", StaticFiles(directory=str(ART)), name="snowfall-art")
    app.mount("/static", StaticFiles(directory=str(ASSETS)), name="snowfall-static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        icon = ASSETS / "snowfall-site-icon.webp"
        if icon.is_file():
            return FileResponse(icon, media_type="image/webp")
        return FileResponse(ASSETS / "favicon.svg", media_type="image/svg+xml")

    @app.get("/")
    def index():
        response = FileResponse(ASSETS / "index.html", media_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


def create_staging_app(env=None) -> FastAPI:
    env = dict(os.environ if env is None else env)
    require_staging(env)
    # The bot activates this same art registry at startup. The web process
    # otherwise would not reliably register the original female portrait keys.
    from snowfall.graphics import snowverhaul
    snowverhaul.activate()
    cfg = APISettings.from_env(env)
    qa_url = prepare_web_qa(env)
    cfg = replace(cfg, database_url=qa_url)
    identities = IdentityRepository(qa_url)
    store = PostgresStore(qa_url, practice_root=Path.cwd())
    shared = StagingGame(SharedGame(store, cfg.season_key))
    return attach_web_ui(create_app(cfg, identity=identities, game=shared),
                         identities, cfg, env=env, game=shared)


def main():
    import uvicorn
    app = create_staging_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")),
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
