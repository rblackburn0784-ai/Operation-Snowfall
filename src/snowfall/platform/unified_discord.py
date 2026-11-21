"""Existing Discord application adapter for isolated v2.9.4b shared-game QA.

One existing Discord worker, one token, one guild. The established /snow
engines and menus remain in use; their Discord snowflake inputs are resolved
to the same canonical BIGINT player IDs used by Underworld and Snowfall web.

This adapter is *only* activated with the deliberately guarded QA flag.
Production cutover requires a separate release and explicit reconciliation.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from urllib.parse import urlsplit

from snowfall.db.postgres import PostgresStore
from snowfall.platform.staging import QA_DB, STAGING_PROJECT

# Reuse the already running, single-token worker; never create another bot.
EXISTING_BOT_PROJECT = "5e5d0e4e-730c-486c-b260-e266adf5bcbf"
EXISTING_BOT_SERVICE = "39d25075-0fb8-498a-b32c-7a982b7b38c1"
QA_SEASON = "web-qa-2026"


class UnifiedConfigurationError(ValueError):
    """Refuse accidental production scoring or a second Discord worker."""


def validate_unified_environment(env=None) -> str | None:
    """Return the staging DSN for enabled mode, or None for the old worker.

    This release has NO shared production mode. It must never silently select
    a live database, season or an additional Discord application/token.
    """
    env = os.environ if env is None else env
    mode = env.get("SNOWFALL_SHARED_MODE", "").strip().lower()
    if not mode:
        return None
    if mode != "qa":
        raise UnifiedConfigurationError("v2.9.4b only permits SNOWFALL_SHARED_MODE=qa")
    expected = {
        "RAILWAY_PROJECT_ID": EXISTING_BOT_PROJECT,
        "RAILWAY_SERVICE_ID": EXISTING_BOT_SERVICE,
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_SEASON_KEY": QA_SEASON,
    }
    if any(env.get(key) != value for key, value in expected.items()):
        raise UnifiedConfigurationError(
            "Existing-bot QA requires the original Railway service, PostgreSQL and web-qa-2026")
    if env.get("SNOWFALL_DISCORD_BRIDGE_ENABLED") == "1" or env.get(
            "SNOWFALL_DISCORD_BRIDGE_TOKEN"):
        raise UnifiedConfigurationError("Do not launch a second Discord bridge worker")
    dsn = env.get("SNOWFALL_DATABASE_URL", "").strip()
    parts = urlsplit(dsn)
    if parts.scheme not in ("postgres", "postgresql") or parts.path != "/" + QA_DB:
        raise UnifiedConfigurationError(
            "Existing-bot QA must use the isolated snowfall_web_qa logical database")
    if not parts.hostname or not parts.username:
        raise UnifiedConfigurationError("Invalid isolated PostgreSQL connection URL")
    return dsn


def verify_qa_database(dsn: str, *, season: str = QA_SEASON) -> None:
    """Prove we are connected to the isolated database, not the migrated source."""
    import psycopg

    if season != QA_SEASON:
        raise UnifiedConfigurationError("QA database season mismatch")
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        marker = conn.execute(
            "SELECT to_regclass('public.snowfall_web_qa_marker')").fetchone()[0]
        if marker is None:
            raise UnifiedConfigurationError("Isolated web QA database marker is missing")
        row = conn.execute(
            "SELECT project_id, season_key FROM snowfall_web_qa_marker "
            "WHERE singleton=1").fetchone()
        if row != (STAGING_PROJECT, QA_SEASON):
            raise UnifiedConfigurationError("Wrong project or season in QA marker")
        identity = conn.execute(
            "SELECT version FROM snowfall_identity_meta WHERE singleton=1").fetchone()
        if identity != (1,):
            raise UnifiedConfigurationError("Verified identity schema is required")


class MappedConnection:
    """Translate bound Discord user IDs to linked principals at the SQL boundary.

    Every existing engine and UI component already passes IDs as SQL bound
    parameters. A single mapping snapshot is taken within the connection's
    transaction, so web and Discord update the exact same gameplay rows.

    We intentionally do not rewrite SQL text, opaque strings, Discord
    interaction IDs, or response models. An unlinked player's commands must
    be refused by the Discord tree's link check before gameplay runs.
    """

    def __init__(self, underlying):
        self._underlying = underlying
        rows = underlying.execute(
            "SELECT subject, player_id FROM snowfall_identity_links "
            "WHERE provider='discord'").fetchall()
        self._linked = {int(row[0]): int(row[1]) for row in rows}

    def _one(self, value):
        if isinstance(value, int) and not isinstance(value, bool):
            return self._linked.get(value, value)
        return value

    def execute(self, statement, parameters=()):
        if isinstance(parameters, dict):
            mapped = {key: self._one(value) for key, value in parameters.items()}
        else:
            mapped = tuple(self._one(value) for value in parameters)
        return self._underlying.execute(statement, mapped)

    def __getattr__(self, name):
        return getattr(self._underlying, name)


class UnifiedDiscordStore(PostgresStore):
    """Legacy Discord game engines on authoritative canonical PostgreSQL IDs."""

    backend = "postgres"
    unified_discord = True

    def __init__(self, dsn: str, *, practice_root: Path):
        super().__init__(dsn, practice_root=practice_root)

    @contextmanager
    def connect(self):
        with super().connect() as conn:
            yield MappedConnection(conn)
