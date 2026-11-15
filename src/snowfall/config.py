"""Load dedicated guild + season configuration; token is only read from env."""
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


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path or os.getenv("SNOWFALL_CONFIG", "config.toml")).resolve()
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    guild_id = int(config["discord"]["guild_id"])
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "PASTE_YOUR_BOT_TOKEN_LOCALLY":
        raise ValueError("Set DISCORD_TOKEN in your environment; never put it in config.toml")
    if guild_id <= 0:
        raise ValueError("Set the dedicated event Discord guild_id in config.toml")
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
    duration = int(config["event"].get("duration_days", 7))
    open_hours = int(config["event"].get("registration_open_hours_before", 168))
    if duration != 7 or open_hours != 168:
        raise ValueError("Approved v1.0 requires a 7-day event and 7-day preregistration")
    db_path = Path(config["storage"].get("database_path", "data/snowfall.sqlite3"))
    if not db_path.is_absolute():
        db_path = path.parent / db_path
    return Settings(
        token=token,
        guild_id=guild_id,
        admin_user_ids=frozenset(int(n) for n in config["discord"].get("admin_user_ids", [])),
        season_key=config["event"].get("season_key", "christmas-2026"),
        event_name=config["event"].get("name", "Operation Snowfall"),
        starts_at_utc=start.astimezone(timezone.utc),
        database_path=db_path,
        duration_days=duration,
        registration_open_hours_before=open_hours,
    )
