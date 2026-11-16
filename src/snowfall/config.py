"""Dedicated guild config. Secrets are never read from the TOML file."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path or os.getenv("SNOWFALL_CONFIG", "config.toml")).resolve()
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "PASTE_YOUR_BOT_TOKEN_LOCALLY":
        raise ValueError("Set DISCORD_TOKEN in .env / environment; never put it in config.toml")
    guild_id = int(config["discord"]["guild_id"])
    hosts = frozenset(int(n) for n in config["discord"].get("admin_user_ids", []))
    staff = frozenset(int(n) for n in config["discord"].get("staff_role_ids", []))
    announcements = int(config["discord"].get("announcement_channel_id", 0))
    if announcements < 0:
        raise ValueError("announcement_channel_id must be a positive channel ID or 0")
    if guild_id <= 0:
        raise ValueError("Set the dedicated event guild_id in config.toml")
    if not hosts or any(value <= 0 for value in hosts | staff):
        raise ValueError("Configure at least one valid host Discord USER ID in admin_user_ids")
    try:
        start = datetime.fromisoformat(config["event"]["starts_at_utc"])
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
    return Settings(token, guild_id, hosts, season_key,
                    config["event"].get("name", "Operation Snowfall"),
                    start.astimezone(timezone.utc), db_path, days, hours, staff, announcements)
