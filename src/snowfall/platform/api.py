"""Opt-in web API: shared real game engines, verified sessions, no separate scores.

Deploy as a *separate* Railway service with Dockerfile.web, never as the live
Discord worker. Identity tables must be explicitly provisioned first.
"""
from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
import logging
import os
from pathlib import Path
import re
import secrets
from typing import Literal
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from snowfall.db.postgres import PostgresStore
from snowfall.platform.assertions import AssertionError as UnderworldAssertionError
from snowfall.platform.assertions import parse_underworld_assertion
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityConflict, IdentityError, IdentityRepository
from snowfall.platform.discard import CONFIRM_PHRASE, DiscardService, QA_SEASON
from snowfall.platform.verification import CrossPlatformVerifier
from snowfall.platform.release import VERSION


COOKIE = "snowfall_session"
DISCARD_COOKIE = "snowfall_discard_challenge"
IDEMPOTENCY = re.compile(r"^[a-zA-Z0-9_-]{12,100}$")


@dataclass(frozen=True)
class APISettings:
    database_url: str
    season_key: str
    public_base_url: str
    underworld_secret: str = ""
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""
    cookie_secure: bool = True
    cors_origins: tuple[str, ...] = ()
    underworld_origin: str = ""

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        if env.get("SNOWFALL_API_ENABLED") != "1":
            raise ValueError("API disabled. Explicitly enable it on a separate web service.")
        if env.get("SNOWFALL_DB_BACKEND") != "postgres":
            raise ValueError("Shared web API requires explicit PostgreSQL backend")
        dsn = env.get("SNOWFALL_DATABASE_URL", "").strip()
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("Set the private PostgreSQL connection URL")
        season = env.get("SNOWFALL_API_SEASON_KEY", "").strip()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", season):
            raise ValueError("Set a valid SNOWFALL_API_SEASON_KEY")
        base = env.get("SNOWFALL_WEB_PUBLIC_BASE_URL", "").rstrip("/")
        url = urlsplit(base)
        insecure = (env.get("SNOWFALL_ALLOW_INSECURE_LOCALHOST") == "1"
                    and url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1"))
        if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("Public base URL must be an origin, without credentials or path")
        if not url.hostname or (url.scheme != "https" and not insecure):
            raise ValueError("Public web origin must be HTTPS (except explicit local development)")
        origins = tuple(o.strip() for o in env.get("SNOWFALL_WEB_ALLOWED_ORIGINS", "").split(",")
                        if o.strip())
        for origin in origins:
            u = urlsplit(origin)
            if not u.hostname or u.path not in ("", "/") or (
                u.scheme != "https" and not (insecure and u.scheme == "http"
                                            and u.hostname in ("localhost", "127.0.0.1"))
            ):
                raise ValueError("CORS origins must be explicit secure origins")
        client_id = env.get("SNOWFALL_DISCORD_OAUTH_CLIENT_ID", "")
        client_secret = env.get("SNOWFALL_DISCORD_OAUTH_CLIENT_SECRET", "")
        redirect = env.get("SNOWFALL_DISCORD_OAUTH_REDIRECT_URI", "")
        if any((client_id, client_secret, redirect)) and not all((client_id, client_secret, redirect)):
            raise ValueError("Complete all Discord OAuth configuration variables")
        if redirect and redirect != base + "/v1/auth/discord/callback":
            raise ValueError("Discord OAuth redirect must exactly match the configured web origin")
        secret = env.get("SNOWFALL_UNDERWORLD_ASSERTION_SECRET", "")
        if secret and len(secret.encode()) < 32:
            raise ValueError("Underworld assertion secret must contain at least 32 bytes")
        underworld_origin = env.get("SNOWFALL_UNDERWORLD_TRUSTED_ORIGIN", "").rstrip("/")
        if underworld_origin:
            parsed = urlsplit(underworld_origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("Underworld origin must be a strict HTTPS origin")
        if bool(secret) != bool(underworld_origin):
            raise ValueError("Underworld integration requires both secret and trusted origin")
        return cls(dsn, season, base, secret, client_id, client_secret, redirect,
                   not insecure, origins, underworld_origin)


class UnderworldLogin(BaseModel):
    assertion: str = Field(min_length=30, max_length=4096)


class RegisterBody(BaseModel):
    mr_username: str = Field(min_length=2, max_length=28)
    city: str = Field(min_length=2, max_length=50)


class ThrowBody(BaseModel):
    target_player_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    style: Literal["quick", "standard", "power", "golden"]


class ItemBody(BaseModel):
    item: str = Field(min_length=1, max_length=60)


class ActivityBody(BaseModel):
    action: Literal["clue", "accuse", "secret", "encounter", "quest", "gift", "use", "guard", "title"]
    item: str = Field(min_length=1, max_length=60)
    day: int | None = Field(default=None, ge=1, le=7)


class ArcadeStart(BaseModel):
    mode: Literal["gallery", "safe", "snowman", "catch", "trivia"]
    day: int = Field(ge=1, le=7)
    attempts_today: int = Field(ge=0, le=3)


class ArcadeTurn(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    step: int = Field(ge=0, le=4)
    choice: str = Field(min_length=1, max_length=96)


class ArcadePracticeStart(BaseModel):
    mode: Literal["gallery", "safe", "snowman", "catch", "trivia"]


class ArcadePracticeCheckpoint(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=0, le=10000)
    state: dict[str, int | float]
    finish: bool = False


class GalleryShotBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    shot_index: int = Field(ge=0, le=31)
    x: int = Field(ge=0, le=640)
    y: int = Field(ge=0, le=360)


class GalleryControlBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["pause", "resume", "finish"]


class SafecrackerActionBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action_seq: int = Field(ge=0, le=299)
    action: Literal["turn", "set"]
    ticks: int = Field(ge=-80, le=80)


class SafecrackerControlBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["pause", "resume", "finish"]


class SnowmanPlaceBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action_seq: int = Field(ge=0, le=119)
    piece_id: str = Field(pattern=r"^[a-z_]{3,24}$")
    x: int = Field(ge=0, le=640)
    y: int = Field(ge=0, le=360)


class SnowmanControlBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["pause", "resume", "finish"]


class SnowflakeCatchUpdateBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action_seq: int = Field(ge=0, le=359)
    x: int = Field(ge=66, le=574)


class SnowflakeCatchControlBody(BaseModel):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["pause", "resume", "finish"]


class OAuthStart(BaseModel):
    mode: Literal["login", "link"] = "login"


class DiscardConsent(BaseModel):
    acknowledged_loss: Literal[True]
    confirmation: Literal["DISCARD DISCORD CHARACTER"]



def _idempotency(principal_id: int, operation: str, key: str | None) -> str:
    if not key or not IDEMPOTENCY.fullmatch(key):
        raise HTTPException(400, "Idempotency-Key must be 12–100 alphanumeric/_/- characters")
    return "web:" + sha256(f"{principal_id}:{operation}:{key}".encode()).hexdigest()


def _link_conflict_code(exc: IdentityConflict) -> str:
    """Stable, non-identifying error categories for an already-verified OAuth user.

    Only permit fixed labels in the browser redirect. Never include raw
    exception text, Discord IDs, session cookies or Underworld account IDs.
    The actual database remains authoritative; no conflict is bypassed here.
    """
    description = str(exc)
    if "existing gameplay" in description or "game progress" in description:
        return "gameplay"
    if "existing activity" in description:
        return "activity"
    if ("another linked identity" in description or "another player with linked progress" in description
            or "already belongs to another player" in description):
        return "linked-elsewhere"
    if "already has a Discord account linked" in description:
        return "character-occupied"
    if "Discord ID already reserved" in description:
        return "reserved"
    if "Sign in through Underworld" in description:
        return "underworld-required"
    return "manual-review"


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(
        b"=").decode("ascii")


def create_app(settings: APISettings | None = None, *, identity=None, game=None,
               oauth_http=None) -> FastAPI:
    """Dependency-injected ASGI factory for isolated tests and Railway web."""
    cfg = settings or APISettings.from_env()
    identities = identity or IdentityRepository(cfg.database_url)
    shared = game or SharedGame(PostgresStore(cfg.database_url, practice_root=Path.cwd()),
                                cfg.season_key)

    @asynccontextmanager
    async def lifespan(app):
        # No implicit schema creation or season start: fail closed if not provisioned.
        identities.check()
        shared.store.initialize()
        shared.store.season(cfg.season_key)
        yield

    app = FastAPI(title="Operation Snowfall Shared API", version=VERSION,
                  lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    if cfg.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins),
                           allow_credentials=True, allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "X-Snowfall-CSRF", "Idempotency-Key",
                                          "X-Snowfall-Player"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        result = await call_next(request)
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["X-Frame-Options"] = "DENY"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        result.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'; "
            "frame-src https://e.widgetbot.io"
        )
        if cfg.cookie_secure:
            result.headers["Strict-Transport-Security"] = "max-age=31536000"
        return result

    @app.exception_handler(IdentityConflict)
    async def identity_conflict(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(UnderworldAssertionError)
    async def underworld_assertion_invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Invalid or expired Underworld assertion"},
                            status_code=401)

    @app.exception_handler(IdentityError)
    async def identity_invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=401)

    @app.exception_handler(ValueError)
    async def game_invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=409)

    def cookie(response: Response, token: str):
        response.set_cookie(COOKIE, token, max_age=12 * 3600, httponly=True,
                            secure=cfg.cookie_secure, samesite="lax", path="/")

    def authenticated(request: Request, *, mutate=False) -> int:
        token = request.cookies.get(COOKIE, "")
        session = identities.session(token)
        if not session:
            raise HTTPException(401, "Authentication required")
        expected = request.headers.get("X-Snowfall-Player")
        if expected is not None and expected != str(session.player_id):
            raise HTTPException(409, "Account changed in another tab; sign in again")
        if mutate and not identities.csrf_ok(
                token, request.headers.get("X-Snowfall-CSRF", "")):
            raise HTTPException(403, "Missing or invalid CSRF token")
        return session.player_id

    def player(request: Request) -> int:
        return authenticated(request)

    def writer(request: Request) -> int:
        return authenticated(request, mutate=True)

    def game_writer(request: Request) -> int:
        """Shared QA gameplay always belongs to an Underworld character.

        Discord-first OAuth may create a temporary authentication principal.
        That identity may browse and link but must never register, spend,
        earn rewards or launch a second character before Underworld linking.
        """
        principal = authenticated(request, mutate=True)
        if cfg.season_key == "web-qa-2026":
            try:
                linked = any(link["provider"] == "underworld"
                             for link in identities.links(principal))
            except Exception:
                raise HTTPException(503, "Account linking temporarily unavailable") from None
            if not linked:
                raise HTTPException(
                    403, "Sign in through Underworld before playing Snowfall")
        return principal

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "version": VERSION, "backend": "postgres",
                "season": cfg.season_key}

    @app.get("/v1/ready")
    def readiness():
        """Read-only live dependency check; liveness alone cannot prove game access.

        Do not return DB errors, OAuth secrets or connection URLs in responses.
        Railway can monitor this independently from the cheap /v1/health.
        """
        try:
            identities.check()
            if shared.store.season(cfg.season_key) is None:
                raise RuntimeError("Missing season configuration")
            if cfg.season_key == "web-qa-2026":
                from snowfall.platform.unified_discord import verify_qa_database
                verify_qa_database(cfg.database_url, season=cfg.season_key)
        except Exception:
            logging.getLogger(__name__).warning(
                "Snowfall readiness dependency check failed; no credentials logged")
            raise HTTPException(503, "Game database not ready") from None
        return {"status": "ready", "backend": "postgres",
                "season": cfg.season_key}

    @app.post("/v1/auth/underworld")
    def underworld(body: UnderworldLogin, response: Response):
        if not cfg.underworld_secret:
            raise HTTPException(503, "Underworld login is not configured")
        verified = parse_underworld_assertion(body.assertion, cfg.underworld_secret)
        principal = identities.resolve_underworld(
            verified.account_id, verified.character_id, verified.nonce, verified.expires_at,
        )
        token, csrf = identities.new_session(principal)
        cookie(response, token)
        return {"authenticated": True, "player_id": str(principal), "csrf": csrf,
                "character_name": verified.character_name}

    @app.post("/v1/auth/underworld/handoff")
    async def underworld_handoff(request: Request):
        """Cross-site form POST: never put a bearer assertion in a URL."""
        if not cfg.underworld_secret or not cfg.underworld_origin:
            raise HTTPException(503, "Underworld login is not configured")
        if request.headers.get("origin") != cfg.underworld_origin:
            raise HTTPException(403, "Untrusted Underworld login origin")
        if request.headers.get("content-type", "").split(";")[0].strip() != (
                "application/x-www-form-urlencoded"):
            raise HTTPException(415, "Handoff requires an encoded form")
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > 8192:
                raise HTTPException(413, "Handoff is too large")
            content.extend(chunk)
        try:
            fields = parse_qs(content.decode("ascii"), strict_parsing=True,
                              max_num_fields=2)
        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(400, "Malformed handoff") from exc
        if set(fields) != {"assertion"} or len(fields["assertion"]) != 1:
            raise HTTPException(400, "One assertion is required")
        assertion = fields["assertion"][0]
        if len(assertion) > 4096 or len(assertion) < 30:
            raise HTTPException(400, "Invalid assertion length")
        verified = parse_underworld_assertion(assertion, cfg.underworld_secret)
        principal = identities.resolve_underworld(
            verified.account_id, verified.character_id, verified.nonce, verified.expires_at,
        )
        token, _ = identities.new_session(principal)
        response = RedirectResponse(cfg.public_base_url + "/", status_code=303)
        cookie(response, token)
        return response

    @app.get("/v1/auth/session")
    def session(request: Request):
        token = request.cookies.get(COOKIE, "")
        current = identities.session(token)
        if not current:
            raise HTTPException(401, "Authentication required")
        return {"player_id": str(current.player_id), "csrf": current.csrf,
                "links": identities.links(current.player_id)}

    @app.post("/v1/auth/logout")
    def logout(request: Request, response: Response, principal: int = Depends(writer)):
        identities.revoke(request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE, path="/", secure=cfg.cookie_secure, httponly=True,
                               samesite="lax")
        response.delete_cookie(DISCARD_COOKIE, path="/", secure=cfg.cookie_secure,
                               httponly=True, samesite="lax")
        return {"logged_out": True}

    @app.post("/v1/auth/discord/start")
    def discord_start(body: OAuthStart, request: Request):
        if not cfg.discord_client_id:
            raise HTTPException(503, "Discord OAuth not configured")
        token = request.cookies.get(COOKIE, "") if body.mode == "link" else None
        if body.mode == "link":
            authenticated(request, mutate=True)
        verifier = secrets.token_urlsafe(48)
        state = identities.new_oauth_state(body.mode, token, verifier)
        params = {
            "response_type": "code", "scope": "identify",
            "client_id": cfg.discord_client_id,
            "redirect_uri": cfg.discord_redirect_uri,
            "state": state, "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
        return {"authorize_url": "https://discord.com/oauth2/authorize?" + urlencode(params)}

    @app.get("/v1/auth/discord/callback")
    async def discord_callback(request: Request, code: str = Query(min_length=2, max_length=512),
                               state: str = Query(min_length=20, max_length=200)):
        if not cfg.discord_client_id:
            raise HTTPException(503, "Discord OAuth not configured")
        mode, principal, verifier = identities.consume_oauth_state(
            state, request.cookies.get(COOKIE),
        )
        # Identity comes only from Discord's authenticated /users/@me response.
        import httpx
        try:
            if oauth_http is None:
                async with httpx.AsyncClient(timeout=10) as client:
                    user_id = await _discord_subject(client, cfg, code, verifier)
            else:
                user_id = await _discord_subject(oauth_http, cfg, code, verifier)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(502, "Discord identity exchange failed") from exc
        if mode == "link":
            try:
                identities.link_discord(principal, user_id)
            except IdentityConflict as exc:
                # The link failure must remain fail-closed, but let the
                # verified account owner see which safe next step applies.
                # Only server-defined categories are included in the URL.
                reason = _link_conflict_code(exc)
                logging.getLogger(__name__).warning(
                    "Discord account-link denied: category=%s", reason)
                if reason == "gameplay" and cfg.season_key == QA_SEASON:
                    # The signed-in Underworld player and a freshly OAuth-
                    # verified Discord ID may offer an explicit replacement.
                    # No game data or identity is changed at this stage.
                    try:
                        challenge = DiscardService(identities, cfg.season_key).begin(
                            principal, user_id, request.cookies.get(COOKIE, ""))
                    except IdentityError:
                        # Prize awards, another linked character, finalised
                        # seasons and unforeseen profiles remain blocked.
                        pass
                    else:
                        response = RedirectResponse(
                            cfg.public_base_url + "/?discord=discard-offer",
                            status_code=303)
                        response.set_cookie(
                            DISCARD_COOKIE, challenge, max_age=600, httponly=True,
                            secure=cfg.cookie_secure, samesite="lax", path="/")
                        return response
                return RedirectResponse(
                    cfg.public_base_url + "/?discord=conflict&reason=" + reason,
                    status_code=303)
            return RedirectResponse(cfg.public_base_url + "/?linked=discord",
                                    status_code=303)
        resolved = identities.resolve_discord(user_id)
        token, _ = identities.new_session(resolved)
        response = RedirectResponse(cfg.public_base_url + "/?login=ok", status_code=303)
        cookie(response, token)
        return response

    @app.get("/v1/auth/discord/discard/preview")
    def discard_preview(request: Request, principal: int = Depends(player)):
        """No user-provided identity: a session-bound, OAuth-confirmed cookie."""
        if cfg.season_key != QA_SEASON:
            raise HTTPException(404, "Not available")
        return DiscardService(identities, cfg.season_key).preview(
            principal, request.cookies.get(COOKIE, ""),
            request.cookies.get(DISCARD_COOKIE, ""))

    @app.post("/v1/auth/discord/discard/confirm")
    def discard_confirm(body: DiscardConsent, request: Request, response: Response,
                        principal: int = Depends(writer)):
        """Explicit irreversible retirement; game records retained for audit."""
        if cfg.season_key != QA_SEASON:
            raise HTTPException(404, "Not available")
        if body.confirmation != CONFIRM_PHRASE or body.acknowledged_loss is not True:
            raise HTTPException(400, "Explicit consent required")
        result = DiscardService(identities, cfg.season_key).confirm(
            principal, request.cookies.get(COOKIE, ""),
            request.cookies.get(DISCARD_COOKIE, ""),
            acknowledged=body.acknowledged_loss, phrase=body.confirmation)
        response.delete_cookie(DISCARD_COOKIE, path="/", secure=cfg.cookie_secure,
                               httponly=True, samesite="lax")
        return result

    @app.post("/v1/auth/discord/discard/cancel")
    def discard_cancel(request: Request, response: Response,
                       principal: int = Depends(writer)):
        if cfg.season_key != QA_SEASON:
            raise HTTPException(404, "Not available")
        DiscardService(identities, cfg.season_key).cancel(
            principal, request.cookies.get(COOKIE, ""),
            request.cookies.get(DISCARD_COOKIE, ""))
        response.delete_cookie(DISCARD_COOKIE, path="/", secure=cfg.cookie_secure,
                               httponly=True, samesite="lax")
        return {"cancelled": True}

    @app.post("/v1/verification/start")
    def verification_start(principal: int = Depends(writer)):
        """Snapshot authenticated canonical progress; no score/gameplay writes."""
        if cfg.season_key != QA_SEASON:
            raise HTTPException(404, "QA-only cross-platform verification")
        return jsonable_encoder(CrossPlatformVerifier(
            identities, shared, cfg.season_key).start(principal))

    @app.get("/v1/verification/status")
    def verification_status(principal: int = Depends(player)):
        """Status requires the same authenticated player's browser session."""
        if cfg.season_key != QA_SEASON:
            raise HTTPException(404, "QA-only cross-platform verification")
        return jsonable_encoder(CrossPlatformVerifier(
            identities, shared, cfg.season_key).status(principal))

    @app.get("/v1/game/leaderboard")
    def leaderboard(limit: int = Query(default=25, ge=1, le=50)):
        return {"players": shared.leaderboard(limit=limit)}

    @app.get("/v1/game/me")
    def me(principal: int = Depends(player)):
        return jsonable_encoder(shared.me(principal))

    @app.get("/v1/game/headquarters")
    def headquarters(response: Response, principal: int = Depends(player)):
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.headquarters(principal))

    @app.get("/v1/game/progress")
    def progress(principal: int = Depends(player)):
        """Same authoritative snapshot consumed by /snowbridge progress."""
        return jsonable_encoder(shared.progress(principal))

    @app.post("/v1/game/register")
    def register(body: RegisterBody, principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.register(principal, body.mr_username, body.city))

    @app.get("/v1/game/targets")
    def targets(response: Response, principal: int = Depends(player)):
        # Equipped rival artwork changes on either platform, so never cache
        # a stale character look across wardrobe changes or identity switches.
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder({"targets": shared.targets(principal)})

    @app.post("/v1/game/ready")
    def ready(principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.ready(principal))

    @app.post("/v1/game/throw")
    def throw(body: ThrowBody, idempotency_key: str | None = Header(default=None),
              principal: int = Depends(game_writer)):
        iid = _idempotency(principal, "throw", idempotency_key)
        return jsonable_encoder(shared.throw(principal, int(body.target_player_id), body.style, iid))

    @app.post("/v1/game/boss")
    def boss(idempotency_key: str | None = Header(default=None),
             principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.boss(
            principal, _idempotency(principal, "boss", idempotency_key)))

    @app.post("/v1/game/siege")
    def siege(idempotency_key: str | None = Header(default=None),
              principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.siege(
            principal, _idempotency(principal, "siege", idempotency_key)))

    @app.get("/v1/game/world")
    def world(principal: int = Depends(player)):
        return jsonable_encoder(shared.world(principal))

    @app.get("/v1/game/cities")
    def cities():
        return jsonable_encoder({"cities": shared.cities()})

    @app.get("/v1/game/catalog")
    def catalog():
        from snowfall.services.winter_fun import COSMETICS
        return {"items": [{"key": item.key, "name": item.name,
                           "category": item.category, "cost": item.cost,
                           "detail": item.detail, "rarity": item.rarity}
                          for item in COSMETICS.values()]}

    @app.get("/v1/game/quests")
    def quests(principal: int = Depends(player)):
        return jsonable_encoder({"quests": shared.quests(principal)})

    @app.post("/v1/game/quests/claim")
    def claim_quest(body: ItemBody, principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.claim_quest(principal, body.item))

    @app.get("/v1/game/raid")
    def raid(day: int = Query(ge=1, le=7)):
        return jsonable_encoder(shared.raid(day=day))

    @app.get("/v1/game/activities")
    def activities(response: Response, principal: int = Depends(player)):
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.activities(principal))

    @app.post("/v1/game/activities/action")
    def activity_action(body: ActivityBody, idempotency_key: str | None = Header(default=None),
                        principal: int = Depends(game_writer)):
        iid = _idempotency(principal, "activities:" + body.action, idempotency_key)
        return jsonable_encoder(shared.activity_action(
            principal, body.action, body.item, body.day, iid))

    @app.get("/v1/game/arcade")
    def arcade_lobby(response: Response, principal: int = Depends(player)):
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.arcade_lobby(principal))

    @app.get("/v1/game/arcade/session/{session_id}")
    def arcade_session(session_id: str, response: Response, principal: int = Depends(player)):
        response.headers["Cache-Control"] = "no-store"
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid arcade session")
        return jsonable_encoder(shared.arcade_session(principal, session_id))

    @app.post("/v1/game/arcade/start")
    def arcade_start(body: ArcadeStart, principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.arcade_start(
            principal, body.mode, body.day, body.attempts_today))

    @app.post("/v1/game/arcade/move")
    def arcade_move(body: ArcadeTurn, idempotency_key: str | None = Header(default=None),
                    principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.arcade_move(
            principal, body.session_id, body.step, body.choice,
            _idempotency(principal, "arcade:move", idempotency_key)))

    def practice_enabled():
        if os.environ.get("SNOWFALL_ARCADE_V299_ENABLED", "") != "1":
            raise HTTPException(503, "Interactive arcade practice is not enabled on this server")

    # v2.9.9: isolated web-only training sessions. No leaderboard, award,
    # paid resource, or Discord social_arcade table is modified by these.
    @app.post("/v1/game/arcade/practice/start")
    def arcade_practice_start(body: ArcadePracticeStart,
                              principal: int = Depends(game_writer)):
        practice_enabled()
        return jsonable_encoder(shared.arcade_practice_start(principal, body.mode))

    @app.get("/v1/game/arcade/practice/session/{session_id}")
    def arcade_practice_session(session_id: str, response: Response,
                                principal: int = Depends(player)):
        practice_enabled()
        response.headers["Cache-Control"] = "no-store"
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid practice session")
        return jsonable_encoder(shared.arcade_practice_session(principal, session_id))

    @app.post("/v1/game/arcade/practice/save")
    def arcade_practice_save(body: ArcadePracticeCheckpoint,
                             principal: int = Depends(game_writer)):
        practice_enabled()
        return jsonable_encoder(shared.arcade_practice_save(
            principal, body.session_id, body.revision, body.state, finish=body.finish))

    def gallery_enabled():
        # The full web-only gallery remains hidden until its QA migration
        # and explicit independent feature flag have been applied.
        if os.environ.get("SNOWFALL_ARCADE_V299A_ENABLED", "") != "1":
            raise HTTPException(503, "Full Target Gallery is not enabled on this server")

    @app.post("/v1/game/arcade/gallery/start")
    def arcade_gallery_start(principal: int = Depends(game_writer)):
        gallery_enabled()
        return jsonable_encoder(shared.gallery_start(principal))

    @app.get("/v1/game/arcade/gallery/session/{session_id}")
    def arcade_gallery_session(session_id: str, response: Response,
                               principal: int = Depends(player)):
        gallery_enabled()
        response.headers["Cache-Control"] = "no-store"
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid gallery session")
        return jsonable_encoder(shared.gallery_session(principal, session_id))

    @app.post("/v1/game/arcade/gallery/control")
    def arcade_gallery_control(body: GalleryControlBody,
                               principal: int = Depends(game_writer)):
        gallery_enabled()
        return jsonable_encoder(shared.gallery_control(
            principal, body.session_id, body.action))

    @app.post("/v1/game/arcade/gallery/shot")
    def arcade_gallery_shot(body: GalleryShotBody,
                            idempotency_key: str | None = Header(default=None),
                            principal: int = Depends(game_writer)):
        gallery_enabled()
        return jsonable_encoder(shared.gallery_shoot(
            principal, body.session_id, body.shot_index, body.x, body.y,
            _idempotency(principal, "gallery:shot", idempotency_key)))

    @app.get("/v1/game/arcade/gallery/record")
    def arcade_gallery_record(response: Response, principal: int = Depends(player)):
        gallery_enabled()
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.gallery_record(principal))

    def safecracker_enabled():
        if os.environ.get("SNOWFALL_ARCADE_V299B_ENABLED", "") != "1":
            raise HTTPException(503, "Full Frozen Safecracker is not enabled on this server")

    @app.post("/v1/game/arcade/safecracker/start")
    def arcade_safe_start(principal: int = Depends(game_writer)):
        safecracker_enabled()
        return jsonable_encoder(shared.safe_start(principal))

    @app.get("/v1/game/arcade/safecracker/session/{session_id}")
    def arcade_safe_session(session_id: str, response: Response,
                            principal: int = Depends(player)):
        safecracker_enabled()
        response.headers["Cache-Control"] = "no-store"
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid safecracker session")
        return jsonable_encoder(shared.safe_session(principal, session_id))

    @app.post("/v1/game/arcade/safecracker/control")
    def arcade_safe_control(body: SafecrackerControlBody,
                            principal: int = Depends(game_writer)):
        safecracker_enabled()
        return jsonable_encoder(shared.safe_control(
            principal, body.session_id, body.action))

    @app.post("/v1/game/arcade/safecracker/move")
    def arcade_safe_move(body: SafecrackerActionBody,
                         idempotency_key: str | None = Header(default=None),
                         principal: int = Depends(game_writer)):
        safecracker_enabled()
        return jsonable_encoder(shared.safe_move(
            principal, body.session_id, body.action_seq, body.action, body.ticks,
            _idempotency(principal, "safecracker:move", idempotency_key)))

    @app.get("/v1/game/arcade/safecracker/record")
    def arcade_safe_record(response: Response, principal: int = Depends(player)):
        safecracker_enabled()
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.safe_record(principal))

    def snowman_enabled():
        if os.environ.get("SNOWFALL_ARCADE_V299C_ENABLED", "") != "1":
            raise HTTPException(503, "Snowman Builder is not enabled on this server")

    @app.post("/v1/game/arcade/snowman/start")
    def arcade_snowman_start(principal: int = Depends(game_writer)):
        snowman_enabled()
        return jsonable_encoder(shared.snowman_start(principal))

    @app.get("/v1/game/arcade/snowman/session/{session_id}")
    def arcade_snowman_session(session_id: str, response: Response,
                               principal: int = Depends(player)):
        snowman_enabled()
        response.headers["Cache-Control"] = "no-store"
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid Snowman Builder session")
        return jsonable_encoder(shared.snowman_session(principal, session_id))

    @app.post("/v1/game/arcade/snowman/control")
    def arcade_snowman_control(body: SnowmanControlBody,
                               principal: int = Depends(game_writer)):
        snowman_enabled()
        return jsonable_encoder(shared.snowman_control(
            principal, body.session_id, body.action))

    @app.post("/v1/game/arcade/snowman/place")
    def arcade_snowman_place(body: SnowmanPlaceBody,
                             idempotency_key: str | None = Header(default=None),
                             principal: int = Depends(game_writer)):
        snowman_enabled()
        return jsonable_encoder(shared.snowman_place(
            principal, body.session_id, body.action_seq, body.piece_id, body.x, body.y,
            _idempotency(principal, "snowman:place", idempotency_key)))

    @app.get("/v1/game/arcade/snowman/record")
    def arcade_snowman_record(response: Response, principal: int = Depends(player)):
        snowman_enabled()
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.snowman_record(principal))

    def catch_enabled():
        if os.environ.get("SNOWFALL_ARCADE_V299D_ENABLED", "") != "1":
            raise HTTPException(503, "Snowflake Catch is not enabled on this server")

    @app.post("/v1/game/arcade/catch/start")
    def arcade_catch_start(principal: int = Depends(game_writer)):
        catch_enabled()
        return jsonable_encoder(shared.catch_start(principal))

    @app.get("/v1/game/arcade/catch/session/{session_id}")
    def arcade_catch_session(session_id: str, response: Response,
                             principal: int = Depends(player)):
        catch_enabled()
        response.headers["Cache-Control"] = "no-store"
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid Snowflake Catch session")
        return jsonable_encoder(shared.catch_session(principal, session_id))

    @app.post("/v1/game/arcade/catch/control")
    def arcade_catch_control(body: SnowflakeCatchControlBody,
                             principal: int = Depends(game_writer)):
        catch_enabled()
        return jsonable_encoder(shared.catch_control(
            principal, body.session_id, body.action))

    @app.post("/v1/game/arcade/catch/update")
    def arcade_catch_update(body: SnowflakeCatchUpdateBody,
                            idempotency_key: str | None = Header(default=None),
                            principal: int = Depends(game_writer)):
        catch_enabled()
        return jsonable_encoder(shared.catch_update(
            principal, body.session_id, body.action_seq, body.x,
            _idempotency(principal, "catch:update", idempotency_key)))

    @app.get("/v1/game/arcade/catch/record")
    def arcade_catch_record(response: Response, principal: int = Depends(player)):
        catch_enabled()
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.catch_record(principal))

    @app.get("/v1/game/arcade/board")
    def arcade_board(response: Response,
                     mode: Literal["gallery", "safe", "snowman", "catch", "trivia"] = "gallery",
                     daily: bool = False, principal: int = Depends(player)):
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(shared.arcade_board(principal, mode, daily=daily))

    @app.get("/v1/game/inventory")
    def inventory(principal: int = Depends(player)):
        return jsonable_encoder(shared.inventory(principal))

    @app.post("/v1/game/craft")
    def craft(body: ItemBody, idempotency_key: str | None = Header(default=None),
              principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.craft(
            principal, body.item, _idempotency(principal, "craft", idempotency_key)))

    @app.get("/v1/game/wardrobe")
    def wardrobe(principal: int = Depends(player)):
        return jsonable_encoder(shared.wardrobe(principal))

    @app.post("/v1/game/wardrobe/purchase")
    def purchase(body: ItemBody, idempotency_key: str | None = Header(default=None),
                 principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.purchase(
            principal, body.item, _idempotency(principal, "purchase", idempotency_key)))

    @app.post("/v1/game/wardrobe/equip")
    def equip(body: ItemBody, principal: int = Depends(game_writer)):
        return jsonable_encoder(shared.equip(principal, body.item))

    return app


async def _discord_subject(client, cfg: APISettings, code: str, verifier: str) -> str:
    token_result = await client.post(
        "https://discord.com/api/oauth2/token",
        data={"client_id": cfg.discord_client_id, "client_secret": cfg.discord_client_secret,
              "grant_type": "authorization_code", "code": code,
              "redirect_uri": cfg.discord_redirect_uri, "code_verifier": verifier},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token_result.raise_for_status()
    access_token = token_result.json()["access_token"]
    result = await client.get("https://discord.com/api/users/@me",
                              headers={"Authorization": "Bearer " + access_token})
    result.raise_for_status()
    user_id = result.json()["id"]
    if not isinstance(user_id, str) or not user_id.isdecimal():
        raise ValueError("Invalid verified Discord ID")
    return user_id


def main():
    import uvicorn
    settings = APISettings.from_env()
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(create_app(settings), host="0.0.0.0", port=port,
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
