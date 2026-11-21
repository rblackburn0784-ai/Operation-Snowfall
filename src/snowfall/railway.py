"""One existing Discord bot: guarded shared-QA cutover and SQLite rollback backup.

Defaults to original production SQLite game. Opt-in shared QA first validates
canonical staging PostgreSQL, securely backs up the unchanged SQLite volume,
and starts the *same* Discord bot/token against the web QA game database.
No second Discord worker is launched and no public HTTP listener is created.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from time import time
from typing import Mapping

LOG = logging.getLogger(__name__)


class RailwayConfigurationError(ValueError):
    """Invalid or unsafe hosting configuration; refuse to start."""


def _required(env: Mapping[str, str], key: str) -> str:
    result = env.get(key, "").strip()
    if not result:
        raise RailwayConfigurationError(f"Missing required environment variable: {key}")
    return result


def _positive_id(value: str, key: str, *, zero_ok: bool = False) -> int:
    if not value.isdecimal():
        raise RailwayConfigurationError(f"{key} must contain a numeric Discord ID")
    number = int(value)
    if number < 0 or (number == 0 and not zero_ok):
        raise RailwayConfigurationError(f"{key} must be {'nonnegative' if zero_ok else 'positive'}")
    return number


def _ids(env: Mapping[str, str], key: str, *, required: bool = False) -> list[int]:
    raw = env.get(key, "").strip()
    if required and not raw:
        raise RailwayConfigurationError(f"Missing required environment variable: {key}")
    if not raw:
        return []
    parts = [part.strip() for part in raw.replace(";", ",").split(",")]
    if any(not part for part in parts):
        raise RailwayConfigurationError(f"{key} contains an empty Discord ID")
    return list(dict.fromkeys(_positive_id(part, key) for part in parts))


def _volume(env: Mapping[str, str]) -> Path:
    on_railway = any(env.get(key) for key in ("RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID", "RAILWAY_ENVIRONMENT_ID"))
    mounted = env.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    chosen = env.get("SNOWFALL_DATA_DIR", "").strip()
    if on_railway and not mounted:
        raise RailwayConfigurationError(
            "Railway volume not detected. Attach a persistent volume to the bot service "
            "with mount path /data before starting the bot."
        )
    if mounted and chosen and Path(mounted).resolve() != Path(chosen).resolve():
        raise RailwayConfigurationError("SNOWFALL_DATA_DIR differs from the attached Railway volume")
    raw = chosen or mounted
    if not raw:
        raise RailwayConfigurationError("Set SNOWFALL_DATA_DIR (local) or attach a Railway volume")
    path = Path(raw)
    if not path.is_absolute():
        raise RailwayConfigurationError("Data directory must be an absolute path")
    path = path.resolve()
    if mounted and (not path.is_dir() or not Path(mounted).is_dir()):
        raise RailwayConfigurationError(f"Volume is not mounted: {path}")
    return path


def configuration(env: Mapping[str, str]) -> tuple[str, Path, Path, str]:
    """Validate settings and return TOML, DB path, backup dir and season key.

    Does not read or log the actual Discord token and has no storage side effects.
    """
    if not env.get("DISCORD_TOKEN", "").strip():
        raise RailwayConfigurationError("Missing required environment variable: DISCORD_TOKEN")
    backend = env.get("SNOWFALL_DB_BACKEND", "sqlite").strip().lower()
    if backend not in ("sqlite", "postgres"):
        raise RailwayConfigurationError("SNOWFALL_DB_BACKEND must be sqlite or postgres")
    if backend == "postgres" and not env.get("SNOWFALL_DATABASE_URL", "").strip():
        raise RailwayConfigurationError("PostgreSQL cutover needs SNOWFALL_DATABASE_URL")
    shared_mode = env.get("SNOWFALL_SHARED_MODE", "").strip().lower()
    if shared_mode:
        from snowfall.platform.unified_discord import validate_unified_environment
        validate_unified_environment(env)
    elif backend == "postgres" and (
        env.get("RAILWAY_SERVICE_ID") == "39d25075-0fb8-498a-b32c-7a982b7b38c1"
    ):
        raise RailwayConfigurationError(
            "The original bot cannot use PostgreSQL without guarded shared QA mode")
    guild = _positive_id(_required(env, "SNOWFALL_GUILD_ID"), "SNOWFALL_GUILD_ID")
    admins = _ids(env, "SNOWFALL_ADMIN_USER_IDS", required=True)
    staff = _ids(env, "SNOWFALL_STAFF_ROLE_IDS")
    announcement = _positive_id(env.get("SNOWFALL_ANNOUNCEMENT_CHANNEL_ID", "0"),
                                "SNOWFALL_ANNOUNCEMENT_CHANNEL_ID", zero_ok=True)
    leaderboard = _positive_id(env.get("SNOWFALL_LEADERBOARD_CHANNEL_ID", "0"),
                               "SNOWFALL_LEADERBOARD_CHANNEL_ID", zero_ok=True)
    if announcement and announcement == leaderboard:
        raise RailwayConfigurationError("Announcements and leaderboard require different channel IDs")
    date_text = _required(env, "SNOWFALL_STARTS_AT_UTC")
    try:
        start = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        if start.tzinfo is None or start.utcoffset().total_seconds() != 0:
            raise ValueError("not UTC")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RailwayConfigurationError("SNOWFALL_STARTS_AT_UTC must be ISO 8601 in UTC") from exc
    season = env.get("SNOWFALL_SEASON_KEY", "christmas-2026").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", season):
        raise RailwayConfigurationError("SNOWFALL_SEASON_KEY must use only letters, digits, _ and -")
    name = env.get("SNOWFALL_EVENT_NAME", "Operation Snowfall").strip()
    if not name or len(name) > 100 or any(ord(char) < 32 for char in name):
        raise RailwayConfigurationError("SNOWFALL_EVENT_NAME must be 1–100 printable characters")
    data = _volume(env)
    db = data / "snowfall.sqlite3"
    backup = data / "backups"
    toml = (
        "# Generated at runtime by Operation Snowfall v2.9.1. No bot token is stored here.\n"
        "[discord]\n"
        f"guild_id = {guild}\n"
        f"admin_user_ids = {json.dumps(admins)}\n"
        f"staff_role_ids = {json.dumps(staff)}\n"
        f"announcement_channel_id = {announcement}\n"
        f"leaderboard_channel_id = {leaderboard}\n\n"
        "[event]\n"
        f"season_key = {json.dumps(season)}\n"
        f"name = {json.dumps(name, ensure_ascii=True)}\n"
        f"starts_at_utc = {json.dumps(start.isoformat())}\n"
        "duration_days = 7\n"
        "registration_open_hours_before = 168\n"
        'identity_mode = "self_declaration"\n'
        'prize_mode = "individual_only"\n'
        'city_championship = "bragging_rights_only"\n\n'
        "[storage]\n"
        f"database_path = {json.dumps(str(db))}\n"
        f"backup_dir = {json.dumps(str(backup))}\n"
    )
    return toml, db, backup, season


def check_storage(db: Path) -> None:
    """Prove the volume is writable without altering an existing game database."""
    db.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".snowfall-storage-check-", dir=db.parent) as probe:
        probe.write(b"volume-ready")
        probe.flush()
    if db.exists():
        if not db.is_file() or db.stat().st_size == 0:
            raise RailwayConfigurationError("Existing Snowfall database is empty or not a file")
        # SQLite read-only URI: never create or mutate an unknown database.
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=10) as conn:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RailwayConfigurationError("Existing Snowfall SQLite database failed integrity check")


def backup_before_start(db: Path, backup_dir: Path) -> Path | None:
    """WAL-consistent prestart backup, at most once per 12h per storage volume."""
    if not db.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(backup_dir.glob("snowfall-*.sqlite3"), key=lambda p: p.stat().st_mtime)
    from snowfall.ops import backup_sqlite, check_backup
    if existing and time() - existing[-1].stat().st_mtime < 12 * 3600:
        try:
            check_backup(existing[-1])
        except (ValueError, OSError, KeyError, sqlite3.DatabaseError):
            LOG.warning("Recent backup failed verification; creating a fresh prestart backup")
        else:
            LOG.info("Recent backup verified; skipping duplicate prestart backup")
            return None
    saved = backup_sqlite(db, backup_dir)
    LOG.info("WAL-safe prestart backup written to persistent volume: %s", saved.name)
    return saved


def cutover_backup(db: Path, backup_dir: Path) -> Path:
    """Create and verify a durable, never-overwritten copy of original SQLite.

    A write-once marker proves the *same* pre-cutover snapshot is available
    even after Railway redeploys. Refuse activation if any marker, backup,
    SQLite integrity, or write operation cannot be verified on /data.
    """
    from snowfall.ops import backup_sqlite, check_backup

    if not db.is_file() or not db.stat().st_size:
        raise RailwayConfigurationError(
            "Existing SQLite game database is missing; refusing shared QA cutover")
    backup_dir.mkdir(parents=True, exist_ok=True)
    marker = backup_dir / "v294e1-original-sqlite-backup.txt"
    if marker.exists():
        if not marker.is_file():
            raise RailwayConfigurationError("Stored cutover backup marker is not a file")
        filename = marker.read_text(encoding="utf-8").strip()
        if not filename or Path(filename).name != filename or not filename.endswith(".sqlite3"):
            raise RailwayConfigurationError("Original SQLite backup marker is invalid")
        previous = backup_dir / filename
        if not previous.is_file():
            raise RailwayConfigurationError(
                "Previously verified cutover backup is missing; refusing launch")
        check_backup(previous)
        LOG.info("Original pre-cutover SQLite snapshot remains verified: %s", filename)
        return previous

    snapshot = backup_sqlite(db, backup_dir)
    check_backup(snapshot)
    filename = snapshot.name
    if Path(filename).name != filename or not filename.endswith(".sqlite3"):
        raise RailwayConfigurationError("Backup output is not a valid SQLite file")
    # Atomic write in the *same* attached volume.
    with tempfile.NamedTemporaryFile(
        mode="w", prefix=".v294e1-backup-", suffix=".tmp",
        dir=backup_dir, encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(filename + "\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_name = tmp.name
    os.replace(temp_name, marker)
    LOG.info("Original SQLite game backed up and verified before QA cutover: %s", filename)
    return snapshot


def verify_shared_qa_preflight(env: Mapping[str, str]) -> None:
    """Refuse a token connection unless staging ownership & schema are correct.

    Exception details from the remote database may contain a connection URL;
    print a stable, non-sensitive error rather than revealing credentials.
    """
    from snowfall.platform.unified_discord import (
        validate_unified_environment, verify_qa_database,
    )

    dsn = validate_unified_environment(env)
    try:
        verify_qa_database(dsn, season=env["SNOWFALL_SEASON_KEY"])
    except Exception:
        raise RailwayConfigurationError(
            "Shared QA PostgreSQL connection or schema verification failed. "
            "Check the public TCP endpoint, SSL mode, database and stage marker."
        ) from None


@contextmanager
def one_instance(data: Path):
    """Linux advisory lock guards against accidental duplicate workers on one mount."""
    path = data / ".snowfall-bot.lock"
    with path.open("a+b") as handle:
        if os.name == "posix":
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RailwayConfigurationError(
                    "Another Snowfall worker is using this volume. Stop the duplicate before starting."
                ) from exc
        try:
            yield
        finally:
            if os.name == "posix":
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operation Snowfall v2.9.4e1 Railway worker")
    parser.add_argument("--check", action="store_true", help="Verify Railway variables and mounted storage without starting Discord")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config_text, db, backup_dir, season = configuration(os.environ)
        check_storage(db)
        shared_qa = os.environ.get("SNOWFALL_SHARED_MODE", "").strip().lower() == "qa"
        if args.check:
            if shared_qa:
                verify_shared_qa_preflight(os.environ)
                # A check does not write a backup, but refuses missing SQLite.
                if not db.is_file():
                    raise RailwayConfigurationError(
                        "Cannot cut over without the existing /data/snowfall.sqlite3")
            print(f"OK: Railway worker configured; season={season}; data={db.parent}; "
                  f"database={'existing' if db.exists() else 'new'}; "
                  f"shared_qa={'ready' if shared_qa else 'off'}; token=present (hidden)")
            return 0
        with one_instance(db.parent), tempfile.TemporaryDirectory(prefix="snowfall-railway-") as temp:
            if shared_qa:
                # Fail closed BEFORE opening the Discord gateway or touching
                # any real scoreboard; the original on-volume SQLite file is
                # kept unchanged and a verified rollback snapshot is retained.
                verify_shared_qa_preflight(os.environ)
                cutover_backup(db, backup_dir)
            else:
                backup_before_start(db, backup_dir)
            config_file = Path(temp) / "config.toml"
            config_file.write_text(config_text, encoding="utf-8")
            config_file.chmod(0o600)
            os.environ["SNOWFALL_CONFIG"] = str(config_file)
            LOG.info("Starting Discord-only Snowfall worker. season=%s volume=%s", season, db.parent)
            from snowfall.app import main as bot_main
            bot_main([])
            return 0
    except (RailwayConfigurationError, OSError, sqlite3.DatabaseError, ValueError) as exc:
        LOG.error("Snowfall startup refused: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
