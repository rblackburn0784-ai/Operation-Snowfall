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
import json
import logging
import mimetypes
import os
import re
import secrets
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from snowfall.db.postgres import PostgresStore
from snowfall.platform.api import APISettings, create_app
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.release import VERSION, WEB_RELEASE
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


class StaffLabAction(BaseModel):
    action: Literal["start", "day", "pvp", "boss", "siege", "resupply", "end",
                    "configure", "arcade", "mission", "simulate_week", "reset_all"]
    day: int | None = Field(default=None, ge=1, le=7)
    reason: str = Field(min_length=8, max_length=220)
    confirmation: str = Field(default="", max_length=40)
    request_id: str = Field(min_length=16, max_length=96,
                            pattern=r"^[A-Za-z0-9_-]+$")
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    options: dict[str, str | int] = Field(default_factory=dict, max_length=8)


class StaffReviewAction(BaseModel):
    player_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    action: Literal["flag", "clear"]
    expected_state: Literal["self_declared", "cleared", "flagged", "disqualified"]
    confirmation: str = Field(min_length=12, max_length=40)
    reason: str = Field(min_length=12, max_length=220)
    request_id: str = Field(min_length=16, max_length=96,
                            pattern=r"^[A-Za-z0-9_-]+$")


def attach_web_ui(app: FastAPI, identities, cfg: APISettings, *, env=None, game=None) -> FastAPI:
    """Add client UI and temporary demo logins; callable with CI fakes."""
    env = dict(os.environ if env is None else env)
    require_staging(env)
    access_code = env.get("SNOWFALL_WEB_DEMO_ACCESS_CODE", "")
    if len(access_code) < 28:
        raise ValueError("WEB QA REFUSED: demo access code must be 28+ characters")
    attempts = {}
    gate = Lock()
    from snowfall.platform.staff_lab import WebStaffTestLab
    lab = WebStaffTestLab()  # Ephemeral; no access to shared Postgres resources.
    # Staff authorisation is a verified Discord OAuth subject in the explicit
    # allowlist. Underworld is intentionally NOT required for staff viewing;
    # it remains mandatory for game mutations. Client-provided IDs, account
    # names and Discord roles never grant access.
    raw_staff = env.get("SNOWFALL_WEB_STAFF_DISCORD_IDS", "").strip()
    staff_ids = frozenset(part.strip() for part in raw_staff.split(",") if part.strip())
    if len(staff_ids) > 30 or any(not re.fullmatch(r"[0-9]{15,25}", item)
                                  for item in staff_ids):
        raise ValueError("WEB QA REFUSED: invalid staff Discord ID allowlist")
    # Existing staff IDs retain organiser access and Test Lab access.
    # Shared-QA review writes require an *additional* explicit host allowlist.
    # With no host list configured, all web staff operations stay read-only.
    raw_hosts = env.get("SNOWFALL_WEB_HOST_DISCORD_IDS", "").strip()
    host_ids = frozenset(part.strip() for part in raw_hosts.split(",") if part.strip())
    if (len(host_ids) > 10 or not host_ids.issubset(staff_ids) or
            any(not re.fullmatch(r"[0-9]{15,25}", item) for item in host_ids)):
        raise ValueError("WEB QA REFUSED: host IDs must be a subset of staff IDs")

    def staff_allowed(request: Request, *, strict=False) -> bool:
        from snowfall.platform.api import COOKIE
        session = identities.session(request.cookies.get(COOKIE, ""))
        if session is None:
            if strict:
                raise HTTPException(401, "Authentication required")
            return False
        expected = request.headers.get("X-Snowfall-Player")
        if expected is not None and expected != str(session.player_id):
            raise HTTPException(409, "Account changed; sign in again")
        # Fail closed if identity lookup is not currently available.
        try:
            links = identities.links(session.player_id)
        except Exception:
            raise HTTPException(503, "Staff verification unavailable") from None
        verified_discord_staff = any(link["provider"] == "discord" and
                                     link["subject"] in staff_ids for link in links)
        allowed = bool(verified_discord_staff and
                       cfg.season_key == "web-qa-2026" and game is not None)
        if strict and not allowed:
            raise HTTPException(403, "Staff access required")
        return allowed

    @app.get("/v1/staff/access")
    def staff_access(request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"allowed": staff_allowed(request)}

    @app.get("/v1/staff/control")
    def control_centre(request: Request, response: Response):
        staff_allowed(request, strict=True)
        response.headers["Cache-Control"] = "no-store"
        from snowfall.platform.control_centre import control_centre_view
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder(control_centre_view(game))


    def staff_lab_actor(request: Request, *, mutate=False) -> str:
        from snowfall.platform.api import COOKIE
        staff_allowed(request, strict=True)
        token = request.cookies.get(COOKIE, "")
        session = identities.session(token)
        if mutate:
            if not identities.csrf_ok(token, request.headers.get("X-Snowfall-CSRF", "")):
                raise HTTPException(403, "Missing or invalid staff CSRF token")
            origin = request.headers.get("origin")
            if origin is not None and origin.rstrip("/") != cfg.public_base_url.rstrip("/"):
                raise HTTPException(403, "Cross-origin staff action refused")
        # Re-derive the trusted Discord actor from server-managed identity links.
        for link in identities.links(session.player_id):
            if link["provider"] == "discord" and link["subject"] in staff_ids:
                return link["subject"]
        raise HTTPException(403, "Staff Discord identity not verified")

    @app.get("/v1/staff/role")
    def staff_role_status(request: Request, response: Response):
        actor = staff_lab_actor(request)
        response.headers["Cache-Control"] = "no-store"
        return {"scope": "ISOLATED_QA_ONLY",
                "role": "host" if actor in host_ids else "organiser",
                "can_review": actor in host_ids,
                "can_edit_scores": False, "can_pay_prizes": False,
                "can_reset_event": False}

    @app.get("/v1/staff/players")
    def staff_player_search(request: Request, response: Response,
                            q: str = Query(default="", max_length=60),
                            city: str = Query(default="all", max_length=50),
                            state: str = Query(default="all", max_length=20),
                            page: int = Query(default=1, ge=1, le=100)):
        staff_lab_actor(request)
        from snowfall.platform.staff_operations import player_directory
        response.headers["Cache-Control"] = "no-store"
        try:
            return player_directory(game, query=q, city=city, state=state, page=page)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/v1/staff/players/{player_id}")
    def staff_player_details(player_id: str, request: Request, response: Response):
        staff_lab_actor(request)
        if not re.fullmatch(r"[1-9][0-9]{0,18}", player_id):
            raise HTTPException(400, "Invalid QA player ID")
        from snowfall.platform.staff_operations import player_dossier
        response.headers["Cache-Control"] = "no-store"
        try:
            return player_dossier(game, int(player_id))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/v1/staff/players/review")
    def staff_review_player(body: StaffReviewAction, request: Request,
                            response: Response):
        actor = staff_lab_actor(request, mutate=True)
        if actor not in host_ids:
            raise HTTPException(403, "Only explicitly authorised hosts can review players")
        from snowfall.platform.staff_operations import apply_player_review
        response.headers["Cache-Control"] = "no-store"
        try:
            return apply_player_review(
                game, actor_id=int(actor), player_id=int(body.player_id),
                action=body.action, expected_state=body.expected_state,
                confirmation=body.confirmation, reason=body.reason,
                request_id=body.request_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/staff/lab")
    def lab_status(request: Request, response: Response):
        actor = staff_lab_actor(request)
        response.headers["Cache-Control"] = "no-store"
        return lab.snapshot(actor)

    @app.post("/v1/staff/lab/action")
    def lab_action(body: StaffLabAction, request: Request, response: Response):
        actor = staff_lab_actor(request, mutate=True)
        response.headers["Cache-Control"] = "no-store"
        # All operations run against a disposable per-staff SQLite file.
        # Not a bot control relay and never a command against shared QA.
        return lab.act(actor, body.action, body.day, body.reason,
                       body.confirmation, body.request_id, body.session_id,
                       options=body.options)

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
            "web_artwork_version": WEB_RELEASE,
            "interactive_arcade_enabled": env.get("SNOWFALL_ARCADE_V299_ENABLED", "") == "1",
            "gallery_v299a_enabled": env.get("SNOWFALL_ARCADE_V299A_ENABLED", "") == "1",
            "safe_v299b_enabled": env.get("SNOWFALL_ARCADE_V299B_ENABLED", "") == "1",
            "snowman_v299c_enabled": env.get("SNOWFALL_ARCADE_V299C_ENABLED", "") == "1",
            "catch_v299d_enabled": env.get("SNOWFALL_ARCADE_V299D_ENABLED", "") == "1",
            "trivia_v299e_enabled": env.get("SNOWFALL_ARCADE_V299E_ENABLED", "") == "1",
            "hub_v299f_enabled": env.get("SNOWFALL_ARCADE_V299F_ENABLED", "") == "1",
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

    @app.get("/v1/web/community")
    def community_status(response: Response):
        from snowfall.platform.community_view import community_view
        if game is None:
            raise HTTPException(503, "Community feed unavailable")
        response.headers["Cache-Control"] = "no-store"
        return community_view(game)

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
    # v2.9.9h: enabled QA-only modes must not serve a half-migrated database.
    # Explicit migration remains manual; this check never installs tables.
    from snowfall.platform.arcade_readiness import require_arcade_schema
    require_arcade_schema(qa_url, env=env)
    # An aggregate, isolated-QA-only check. Never expose DSNs, player names,
    # IDs or exceptions. Keep readiness independent from audit reporting.
    from snowfall.platform.launch_audit import audit_qa_database

    logger = logging.getLogger(__name__)
    try:
        result = audit_qa_database(qa_url)
        logger.warning("QA_RELEASE_AUDIT %s", json.dumps({
            key: result[key] for key in (
                "scope", "season", "status", "linked_registered_players",
                "orphan_resources", "bad_resources", "prize_awards",
                "blockers", "warnings",
            )
        }, sort_keys=True))
    except Exception:
        logger.error("QA_RELEASE_AUDIT unavailable; no credentials logged")
    return attach_web_ui(create_app(cfg, identity=identities, game=shared),
                         identities, cfg, env=env, game=shared)


def main():
    import uvicorn
    app = create_staging_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")),
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
