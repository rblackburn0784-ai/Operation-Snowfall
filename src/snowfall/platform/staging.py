"""Staging-only web demo: use a new logical DB, never the imported Railway DB.

All mutating bootstrap operations require the *exact* isolated Snowfall staging
project and environment IDs, a deliberate confirmation variable, and a source
PostgreSQL game schema v11. This creates snowfall_web_qa inside the existing
staging PostgreSQL cluster; it never edits the imported 'railway' database.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import secrets
import tempfile
from urllib.parse import urlsplit, urlunsplit

from snowfall.db.migrate_postgres import migrate
from snowfall.db.store import CITIES, DB_VERSION, Store
from snowfall.platform.identity import IdentityRepository

STAGING_PROJECT = "43bd3f71-137a-4302-a456-e4c2d637e7a0"
STAGING_ENVIRONMENT = "f618a365-51e8-4de7-bdfe-360b50868f98"
QA_DB = "snowfall_web_qa"
QA_CONFIRM = "CONFIRM_ISOLATED_WEB_QA_DATABASE"
QA_IDS = (910001, 910002, 910003, 910004, 910005, 910006)
QA_NAMES = ("FrostyFinn", "TheSnowman", "IcyMickey", "BlizzardBelle",
            "PolarPete", "ChillyCharlie")


class StagingError(ValueError):
    """Refuse to seed a database that is not explicitly isolated staging."""


def require_staging(env) -> None:
    if (env.get("RAILWAY_PROJECT_ID") != STAGING_PROJECT
            or env.get("RAILWAY_ENVIRONMENT_ID") != STAGING_ENVIRONMENT
            or env.get("RAILWAY_ENVIRONMENT_NAME") != "staging"
            or env.get("SNOWFALL_WEB_QA_CONFIRM") != QA_CONFIRM
            or env.get("SNOWFALL_API_ENABLED") != "1"
            or env.get("SNOWFALL_DB_BACKEND") != "postgres"):
        raise StagingError("WEB QA REFUSED: wrong project/environment or confirmation")


def database_url(admin_url: str) -> str:
    parts = urlsplit(admin_url)
    if parts.scheme not in ("postgres", "postgresql") or parts.path != "/railway":
        raise StagingError("WEB QA REFUSED: admin URL must point to imported /railway database")
    if not parts.hostname or parts.username is None:
        raise StagingError("WEB QA REFUSED: malformed staging Postgres URL")
    return urlunsplit(parts._replace(path="/" + QA_DB))


def _source_snapshot(path: Path, season: str) -> None:
    """Generate a real schema-v11 fixture from the existing trusted SQLite Store."""
    from snowfall.services.combat import CombatEngine
    now = datetime.now(timezone.utc)
    started = now - timedelta(minutes=2)
    store = Store(path)
    store.initialize()
    store.ensure_season(season, started)
    for uid, name, city in zip(QA_IDS, QA_NAMES, CITIES):
        store.register(season, uid, name, city, started)
    store.transition(season, 999999, "start", started, "Isolated web QA fixture")
    for uid in QA_IDS:
        CombatEngine(store).ready(season, uid, started)


def prepare_web_qa(env=None) -> str:
    """Idempotent protected boot. Do not call on the live worker."""
    env = os.environ if env is None else env
    require_staging(env)
    season = env.get("SNOWFALL_API_SEASON_KEY", "")
    if not season.startswith("web-qa-") or len(season) > 70:
        raise StagingError("WEB QA REFUSED: use a separate web-qa-* season")
    admin_url = env.get("SNOWFALL_DATABASE_URL", "")
    qa_url = database_url(admin_url)
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_url, autocommit=True, connect_timeout=12) as admin:
        original = admin.execute(
            "SELECT version FROM snowfall_pg_meta WHERE singleton=1").fetchone()
        if not original or original[0] != DB_VERSION:
            raise StagingError("WEB QA REFUSED: original imported game schema is not v11")
        existing = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (QA_DB,)).fetchone()
        if not existing:
            # Only a brand-new, correctly named logical database may be created.
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(QA_DB)))

    with psycopg.connect(qa_url, connect_timeout=12) as qa:
        metadata = qa.execute(
            "SELECT to_regclass('public.snowfall_pg_meta'),"
            "to_regclass('public.snowfall_web_qa_marker')").fetchone()

    if metadata[0] is None:
        if metadata[1] is not None:
            raise StagingError("WEB QA REFUSED: unexpected QA marker without schema")
        with tempfile.TemporaryDirectory(prefix="snowfall-web-qa-") as folder:
            seed = Path(folder) / "qa.sqlite3"
            _source_snapshot(seed, season)
            migrate(seed, qa_url, confirmation="OFFLINE_MIGRATE")

    identities = IdentityRepository(qa_url)
    identities.provision(confirm="INSTALL_IDENTITY_SCHEMA")
    identities.check()

    with psycopg.connect(qa_url, connect_timeout=12) as qa:
        with qa.cursor() as cur:
            cur.execute("SELECT version FROM snowfall_pg_meta WHERE singleton=1")
            if cur.fetchone()[0] != DB_VERSION:
                raise StagingError("WEB QA REFUSED: test game DB not schema v11")
            cur.execute("SELECT season_key FROM season_state")
            seasons = [r[0] for r in cur.fetchall()]
            if seasons != [season]:
                raise StagingError("WEB QA REFUSED: unknown or multiple QA seasons")
            cur.execute("""CREATE TABLE IF NOT EXISTS snowfall_web_qa_marker(
                singleton INT PRIMARY KEY CHECK(singleton=1),
                project_id TEXT NOT NULL, season_key TEXT NOT NULL)""")
            cur.execute("""INSERT INTO snowfall_web_qa_marker(singleton,project_id,season_key)
                VALUES(1,%s,%s) ON CONFLICT(singleton) DO NOTHING""",
                (STAGING_PROJECT, season))
            cur.execute("SELECT project_id,season_key FROM snowfall_web_qa_marker")
            if cur.fetchone() != (STAGING_PROJECT, season):
                raise StagingError("WEB QA REFUSED: unknown marker")
            cur.execute("""CREATE TABLE IF NOT EXISTS snowfall_web_qa_bonus(
                player_id BIGINT PRIMARY KEY, granted_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
    return qa_url


class StagingGame:
    """Wrap official game facade with isolated QA convenience only."""

    def __init__(self, game):
        self._game = game
        self.store = game.store
        self.season = game.season

    def __getattr__(self, key):
        return getattr(self._game, key)

    def register(self, player_id, mr_name, city, *, now=None):
        result = self._game.register(player_id, mr_name, city, now=now)
        # One-time sample snowflakes for QA of the real cosmetics and economy.
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            marker = con.execute("""INSERT INTO snowfall_web_qa_bonus(player_id)
                VALUES(?) ON CONFLICT DO NOTHING RETURNING player_id""",
                (player_id,)).fetchone()
            if marker:
                con.execute("""UPDATE player_resources SET snowflakes=LEAST(100,snowflakes+60)
                    WHERE season_key=? AND discord_user_id=?""", (self.season, player_id))
        return result

    def targets(self, player_id, *, now=None):
        from snowfall.services.combat import CombatEngine, CombatError
        now = now or datetime.now(timezone.utc)
        combat = CombatEngine(self.store)
        for uid in QA_IDS:
            try:
                combat.ready(self.season, uid, now)
            except CombatError:
                pass
        return self._game.targets(player_id, now=now)
