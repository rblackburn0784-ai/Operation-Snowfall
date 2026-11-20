"""v2.9.3 optional PostgreSQL identity layer. Does not modify Snowfall v11 game tables.

All principals resolve to the existing positive BIGINT gameplay ID. Existing
Discord players retain their ID; Underworld-first players receive an ID from
a high, isolated range. Linking never merges two active game profiles.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

from snowfall.db.postgres import _psycopg

IDENTITY_VERSION = 1
LOCK = 849173002
PLAYER_START = 6_000_000_000_000_000_000


class IdentityError(ValueError):
    pass


class IdentityConflict(IdentityError):
    pass


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Session:
    player_id: int
    csrf: str | None = None


SCHEMA = (
    """CREATE SEQUENCE IF NOT EXISTS snowfall_identity_player_seq
       START WITH 6000000000000000000 INCREMENT BY 1 NO CYCLE""",
    """CREATE TABLE IF NOT EXISTS snowfall_identity_meta (
       singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS snowfall_identity_principals (
       player_id BIGINT PRIMARY KEY CHECK(player_id>0),
       created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS snowfall_identity_links (
       provider TEXT NOT NULL CHECK(provider IN ('discord','underworld')),
       subject TEXT NOT NULL,
       account_subject TEXT,
       player_id BIGINT NOT NULL REFERENCES snowfall_identity_principals(player_id),
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       PRIMARY KEY (provider, subject), UNIQUE(provider,account_subject),
       CHECK ((provider='underworld' AND account_subject IS NOT NULL)
              OR (provider='discord' AND account_subject IS NULL)))""",
    """CREATE INDEX IF NOT EXISTS idx_snowfall_identity_links_player
       ON snowfall_identity_links(player_id)""",
    """CREATE TABLE IF NOT EXISTS snowfall_identity_nonces (
       nonce_hash TEXT PRIMARY KEY, expires_at TIMESTAMPTZ NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS snowfall_identity_sessions (
       token_hash TEXT PRIMARY KEY,
       csrf_hash TEXT NOT NULL,
       player_id BIGINT NOT NULL REFERENCES snowfall_identity_principals(player_id),
       expires_at TIMESTAMPTZ NOT NULL,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE INDEX IF NOT EXISTS idx_snowfall_identity_sessions_player
       ON snowfall_identity_sessions(player_id)""",
    """CREATE TABLE IF NOT EXISTS snowfall_identity_oauth_states (
       state_hash TEXT PRIMARY KEY,
       session_hash TEXT,
       mode TEXT NOT NULL CHECK(mode IN ('login','link')),
       code_verifier TEXT NOT NULL,
       expires_at TIMESTAMPTZ NOT NULL)""",
)


class IdentityRepository:
    """Database-authoritative identity, single-use assertions and web sessions."""

    def __init__(self, dsn: str):
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise IdentityError("PostgreSQL URL required")
        self._dsn = dsn

    def _connect(self):
        return _psycopg().connect(self._dsn, connect_timeout=10)

    def provision(self, *, confirm: str) -> None:
        if confirm != "INSTALL_IDENTITY_SCHEMA":
            raise IdentityError("Explicit INSTALL_IDENTITY_SCHEMA confirmation required")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.snowfall_pg_meta')")
                if cur.fetchone()[0] is None:
                    raise IdentityError("Migrate and verify Snowfall game schema first")
                cur.execute("SELECT version FROM snowfall_pg_meta WHERE singleton=1")
                row = cur.fetchone()
                if row is None or row[0] != 11:
                    raise IdentityError("Requires verified Snowfall game schema v11")
                for statement in SCHEMA:
                    cur.execute(statement)
                cur.execute("""INSERT INTO snowfall_identity_meta(singleton,version)
                               VALUES(1,%s) ON CONFLICT(singleton) DO NOTHING""",
                            (IDENTITY_VERSION,))
                cur.execute("SELECT version FROM snowfall_identity_meta WHERE singleton=1")
                if cur.fetchone()[0] != IDENTITY_VERSION:
                    raise IdentityError("Unsupported identity schema version")

    def check(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version FROM snowfall_identity_meta WHERE singleton=1")
                row = cur.fetchone()
                if row is None or row[0] != IDENTITY_VERSION:
                    raise IdentityError("Identity schema not provisioned or wrong version")

    @staticmethod
    def _lock(cur):
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))

    def resolve_underworld(self, account_id: str, character_id: str, nonce: str,
                           expiry: datetime) -> int:
        """One character per account; a used signed assertion is never replayable."""
        if not account_id or not character_id or not nonce:
            raise IdentityError("Missing signed identity fields")
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._lock(cur)
                cur.execute("INSERT INTO snowfall_identity_nonces(nonce_hash,expires_at) "
                            "VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING nonce_hash",
                            (digest("underworld:" + nonce), expiry))
                if cur.fetchone() is None:
                    raise IdentityError("Underworld assertion already used")
                cur.execute("""SELECT subject,player_id FROM snowfall_identity_links
                               WHERE provider='underworld' AND account_subject=%s""",
                            (account_id,))
                previous = cur.fetchone()
                if previous:
                    if previous[0] != character_id:
                        raise IdentityConflict("Underworld account has a different character")
                    return previous[1]
                cur.execute("""SELECT account_subject FROM snowfall_identity_links
                               WHERE provider='underworld' AND subject=%s""",
                            (character_id,))
                if cur.fetchone():
                    raise IdentityConflict("Character already bound to another Underworld account")
                cur.execute("SELECT nextval('snowfall_identity_player_seq')")
                player_id = cur.fetchone()[0]
                cur.execute("INSERT INTO snowfall_identity_principals(player_id) VALUES(%s)",
                            (player_id,))
                cur.execute("""INSERT INTO snowfall_identity_links
                               (provider,subject,account_subject,player_id)
                               VALUES('underworld',%s,%s,%s)""",
                            (character_id, account_id, player_id))
                return player_id

    def resolve_discord(self, user_id: str) -> int:
        """OAuth-verified Discord identity. Legacy IDs keep all existing scores."""
        if not user_id.isdecimal() or not 0 < int(user_id) < PLAYER_START:
            raise IdentityError("Invalid Discord account ID")
        discord_id = int(user_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._lock(cur)
                cur.execute("""SELECT player_id FROM snowfall_identity_links
                               WHERE provider='discord' AND subject=%s""", (user_id,))
                linked = cur.fetchone()
                if linked:
                    return linked[0]
                cur.execute("INSERT INTO snowfall_identity_principals(player_id) VALUES(%s) "
                            "ON CONFLICT DO NOTHING", (discord_id,))
                cur.execute("""INSERT INTO snowfall_identity_links(provider,subject,player_id)
                               VALUES('discord',%s,%s)""", (user_id, discord_id))
                return discord_id

    def link_discord(self, player_id: int, user_id: str) -> None:
        """No silent cross-account merging or takeover of legacy Discord scores."""
        if not user_id.isdecimal() or not 0 < int(user_id) < PLAYER_START:
            raise IdentityError("Invalid Discord account ID")
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._lock(cur)
                cur.execute("SELECT 1 FROM snowfall_identity_principals WHERE player_id=%s",
                            (player_id,))
                if cur.fetchone() is None:
                    raise IdentityError("Unknown game principal")
                cur.execute("""SELECT player_id FROM snowfall_identity_links
                               WHERE provider='discord' AND subject=%s""", (user_id,))
                previous = cur.fetchone()
                if previous:
                    if previous[0] != player_id:
                        raise IdentityConflict("Discord account already belongs to another player")
                    return
                if int(user_id) != player_id:
                    cur.execute("SELECT 1 FROM players WHERE discord_user_id=%s LIMIT 1",
                                (int(user_id),))
                    if cur.fetchone():
                        raise IdentityConflict("Discord account already has game progress; manual reconciliation required")
                    cur.execute("SELECT 1 FROM snowfall_identity_principals WHERE player_id=%s",
                                (int(user_id),))
                    if cur.fetchone():
                        raise IdentityConflict("Discord ID already reserved by another principal")
                cur.execute("""INSERT INTO snowfall_identity_links(provider,subject,player_id)
                               VALUES('discord',%s,%s)""", (user_id, player_id))

    def links(self, player_id: int) -> list[dict[str, str]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT provider,subject FROM snowfall_identity_links
                               WHERE player_id=%s ORDER BY provider""", (player_id,))
                return [{"provider": provider, "subject": subject} for provider, subject in cur.fetchall()]

    def new_session(self, player_id: int) -> tuple[str, str]:
        token = secrets.token_urlsafe(36)
        csrf = digest('snowfall-csrf:' + token)
        expires = datetime.now(timezone.utc) + timedelta(hours=12)
        with self._connect() as conn:
            conn.execute("""INSERT INTO snowfall_identity_sessions
                            (token_hash,csrf_hash,player_id,expires_at) VALUES(%s,%s,%s,%s)""",
                         (digest(token), digest(csrf), player_id, expires))
        return token, csrf

    def session(self, token: str) -> Session | None:
        if not token or len(token) > 200:
            return None
        with self._connect() as conn:
            row = conn.execute("""SELECT player_id FROM snowfall_identity_sessions
                                  WHERE token_hash=%s AND expires_at>now()""",
                               (digest(token),)).fetchone()
        return Session(row[0], digest('snowfall-csrf:' + token)) if row else None

    def csrf_ok(self, token: str, csrf: str) -> bool:
        if not token or not csrf or len(csrf) > 200:
            return False
        with self._connect() as conn:
            row = conn.execute("""SELECT csrf_hash FROM snowfall_identity_sessions
                                  WHERE token_hash=%s AND expires_at>now()""",
                               (digest(token),)).fetchone()
        return bool(row and secrets.compare_digest(row[0], digest(csrf)))

    def revoke(self, token: str) -> None:
        if token:
            with self._connect() as conn:
                conn.execute("DELETE FROM snowfall_identity_sessions WHERE token_hash=%s",
                             (digest(token),))

    def new_oauth_state(self, mode: str, session_token: str | None, verifier: str) -> str:
        if mode not in ("login", "link") or (mode == "link" and not session_token):
            raise IdentityError("Invalid OAuth request")
        state = secrets.token_urlsafe(32)
        with self._connect() as conn:
            conn.execute("""INSERT INTO snowfall_identity_oauth_states
                            (state_hash,session_hash,mode,code_verifier,expires_at)
                            VALUES(%s,%s,%s,%s,now()+interval '5 minutes')""",
                         (digest(state), digest(session_token) if session_token else None,
                          mode, verifier))
        return state

    def consume_oauth_state(self, state: str, session_token: str | None) -> tuple[str, int | None, str]:
        if not state or len(state) > 200:
            raise IdentityError("Invalid OAuth state")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""DELETE FROM snowfall_identity_oauth_states
                               WHERE state_hash=%s AND expires_at>now()
                               RETURNING session_hash,mode,code_verifier""", (digest(state),))
                row = cur.fetchone()
                if not row:
                    raise IdentityError("Expired or reused OAuth state")
                session_hash, mode, verifier = row
                if mode == "link":
                    if not session_token or not secrets.compare_digest(
                            session_hash, digest(session_token)):
                        raise IdentityError("OAuth linking session changed")
                    cur.execute("""SELECT player_id FROM snowfall_identity_sessions
                                   WHERE token_hash=%s AND expires_at>now()""",
                                (digest(session_token),))
                    user = cur.fetchone()
                    if not user:
                        raise IdentityError("Linking session expired")
                    return mode, user[0], verifier
                return mode, None, verifier
