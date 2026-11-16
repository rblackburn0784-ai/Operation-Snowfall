"""Dedicated guild config. Secrets are never read from the TOML file."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int
    admin_user_ids: frozenset[int]
    season_key: str
    event_name: str
    starts_at_utc: datetime
    database_path: Path
    duration_days: int = 7
    registration_open_hours_before: int = 168
    staff_role_ids: frozenset[int] = frozenset()
    announcement_channel_id: int = 0
    leaderboard_channel_id: int = 0
    mode: str = "production"
    backup_dir: Path | None = None

    @property
    def is_test(self) -> bool:
        return self.mode == "test"


def load_settings(config_path: str | Path | None = None, *, test_mode: bool = False) -> Settings:
    production_path = Path(os.getenv("SNOWFALL_CONFIG", "config.toml")).resolve()
    path = Path(config_path or (os.getenv("SNOWFALL_TEST_CONFIG", "config.test.toml")
                                 if test_mode else production_path)).resolve()
    if test_mode and path == production_path:
        raise ValueError("TEST MODE REFUSED: test config must not be the live config")
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    production_token = os.getenv("DISCORD_TOKEN", "").strip()
    token = os.getenv("DISCORD_TEST_TOKEN" if test_mode else "DISCORD_TOKEN", "").strip()
    if not token or token == "PASTE_YOUR_BOT_TOKEN_LOCALLY":
        raise ValueError("Set the matching Discord token in .env / environment; never in TOML")
    if test_mode and (not production_token or token == production_token):
        raise ValueError("TEST MODE REFUSED: use a different DISCORD_TEST_TOKEN from DISCORD_TOKEN")
    guild_id = int(config["discord"]["guild_id"])
    hosts = frozenset(int(n) for n in config["discord"].get("admin_user_ids", []))
    staff = frozenset(int(n) for n in config["discord"].get("staff_role_ids", []))
    announcements = int(config["discord"].get("announcement_channel_id", 0))
    leaderboard = int(config["discord"].get("leaderboard_channel_id", 0))
    if announcements < 0 or leaderboard < 0:
        raise ValueError("Announcement and leaderboard IDs must be positive or 0")
    if announcements and announcements == leaderboard:
        raise ValueError("Use two different channels for leaderboards and announcements")
    if guild_id <= 0:
        raise ValueError("Set the dedicated event guild_id in config.toml")
    if not hosts or any(value <= 0 for value in hosts | staff):
        raise ValueError("Configure at least one valid host Discord USER ID in admin_user_ids")
    try:
        start_text = config["event"]["starts_at_utc"]
        start = (datetime.now(timezone.utc) - timedelta(seconds=1)
                 if test_mode and start_text == "AUTO" else datetime.fromisoformat(start_text))
    except (TypeError, ValueError) as exc:
        raise ValueError("Set a real UTC starts_at_utc in config.toml") from exc
    if start.tzinfo is None or start.utcoffset().total_seconds() != 0:
        raise ValueError("starts_at_utc must be timezone-aware UTC")
    if config["event"].get("identity_mode") != "self_declaration":
        raise ValueError("v1.0 requires self_declaration identity mode")
    if config["event"].get("prize_mode") != "individual_only":
        raise ValueError("v1.0 only permits individual prizes")
    if config["event"].get("city_championship") != "bragging_rights_only":
        raise ValueError("v1.0 city competition is for bragging rights only")
    days = int(config["event"].get("duration_days", 7))
    hours = int(config["event"].get("registration_open_hours_before", 168))
    if days != 7 or hours != 168:
        raise ValueError("Approved specification requires 7-day event and 7-day registration")
    db_path = Path(config["storage"].get("database_path", "data/snowfall.sqlite3"))
    if not db_path.is_absolute():
        db_path = path.parent / db_path
    season_key = config["event"].get("season_key", "christmas-2026")
    if not isinstance(season_key, str) or not season_key.strip():
        raise ValueError("season_key must be a nonempty string")
    backup_path = Path(config.get("storage", {}).get("backup_dir", "data/backups"))
    if not backup_path.is_absolute():
        backup_path = path.parent / backup_path
    if backup_path.resolve() == db_path.resolve() or backup_path.resolve().is_relative_to(db_path.resolve()):
        raise ValueError("Backup directory cannot be the database file")
    if test_mode:
        if not production_path.exists():
            raise ValueError("TEST MODE REFUSED: production config.toml required for comparison")
        with production_path.open("rb") as production_handle:
            live = tomllib.load(production_handle)
        live_guild = int(live["discord"]["guild_id"])
        live_db = Path(live.get("storage", {}).get("database_path", "data/snowfall.sqlite3"))
        if not live_db.is_absolute():
            live_db = production_path.parent / live_db
        live_channels = {int(live["discord"].get(name, 0)) for name in
                         ("leaderboard_channel_id", "announcement_channel_id")}
        if guild_id == live_guild or guild_id <= 0:
            raise ValueError("TEST MODE REFUSED: use a separate Discord test server")
        if db_path.resolve() == live_db.resolve():
            raise ValueError("TEST MODE REFUSED: test and production database must differ")
        if season_key == live["event"].get("season_key"):
            raise ValueError("TEST MODE REFUSED: use a different test season_key")
        if any(ch and ch in live_channels for ch in (leaderboard, announcements)):
            raise ValueError("TEST MODE REFUSED: test channels must not be production channels")
        prod_backup = Path(live.get("storage", {}).get("backup_dir", "data/backups"))
        if not prod_backup.is_absolute():
            prod_backup = production_path.parent / prod_backup
        if backup_path.resolve() == prod_backup.resolve():
            # The check is deliberately additional to distinct databases.
            raise ValueError("TEST MODE REFUSED: test backup directory must differ from production")
    return Settings(token, guild_id, hosts, season_key,
                    config["event"].get("name", "Operation Snowfall"),
                    start.astimezone(timezone.utc), db_path, days, hours, staff,
                    announcements, leaderboard, "test" if test_mode else "production",
                    backup_path.resolve())
