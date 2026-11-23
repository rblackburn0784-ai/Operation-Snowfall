"""v2.9.9f — five-game Arcade Hub read model for isolated QA sessions.

A single authenticated, read-only overview of the five FULL interactive
mini-games. Never starts a game or modifies classic Discord results, wallet,
prizes or day limits. Each game is independently feature-gated; an active
game is synchronized using its existing server-owned timer before display.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os

from snowfall.core.clock import as_utc
from snowfall.db.store import Store
from snowfall.services.social_arcade import SocialArcadeEngine

GAMES = (
    ("gallery", "Snowball Target Gallery", "Aim and hit moving targets",
     "Reflexes", "45 sec", "SNOWFALL_ARCADE_V299A_ENABLED",
     "web_arcade_gallery_sessions", 45_000),
    ("safe", "Frozen Safecracker", "Turn the dial and crack the code",
     "Precision", "90 sec", "SNOWFALL_ARCADE_V299B_ENABLED",
     "web_arcade_safe_sessions", 90_000),
    ("snowman", "Snowman Builder", "Build three festive snowmen",
     "Creativity", "150 sec", "SNOWFALL_ARCADE_V299C_ENABLED",
     "web_arcade_snowman_sessions", 150_000),
    ("catch", "Snowflake Catch", "Catch bonuses and dodge icy hazards",
     "Reflexes", "60 sec", "SNOWFALL_ARCADE_V299D_ENABLED",
     "web_arcade_catch_sessions", 60_000),
    ("trivia", "Christmas Trivia", "Open presents and solve festive puzzles",
     "Knowledge", "15 questions", "SNOWFALL_ARCADE_V299E_ENABLED",
     "web_arcade_trivia_sessions", 210_000),
)


def _engine(key: str, store: Store, season: str):
    if key == "gallery":
        from snowfall.platform.gallery_arcade import GalleryEngine
        return GalleryEngine(store, season)
    if key == "safe":
        from snowfall.platform.safecracker_arcade import SafecrackerEngine
        return SafecrackerEngine(store, season)
    if key == "snowman":
        from snowfall.platform.snowman_arcade import SnowmanBuilderEngine
        return SnowmanBuilderEngine(store, season)
    if key == "catch":
        from snowfall.platform.catch_arcade import SnowflakeCatchEngine
        return SnowflakeCatchEngine(store, season)
    if key == "trivia":
        from snowfall.platform.trivia_arcade import ChristmasTriviaEngine
        return ChristmasTriviaEngine(store, season)
    raise ValueError("Unsupported full arcade game.")


def _progress(key: str, view: dict) -> tuple[int, str]:
    if key == "gallery":
        value = min(32, int(view["shots_used"]))
        return round(value * 100 / 32), f"{value} / 32 snowballs used"
    if key == "safe":
        value = min(3, int(view["stage"]))
        return round(value * 100 / 3), f"{value} / 3 tumblers opened"
    if key == "snowman":
        value = min(20, int(view["placed_total"]))
        return round(value * 100 / 20), f"{value} / 20 parts fitted"
    if key == "catch":
        seconds = min(60, int(view["elapsed_ms"]) // 1000)
        return round(seconds * 100 / 60), f"{seconds} / 60 seconds played"
    value = min(15, int(view["step"]))
    return round(value * 100 / 15), f"{value} / 15 questions answered"


class ArcadeHubEngine:
    """Projection only: opt-in modes never consume Discord daily starts."""

    def __init__(self, store: Store, season: str, *, env=None):
        self.store = store
        self.season = season
        self.env = env if env is not None else os.environ

    def overview(self, player_id: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        # Reuse the canonical event/player/day eligibility gate.
        with self.store.connect() as con:
            day = SocialArcadeEngine._eligible(
                con, self.season, player_id, now, active=False)[1]
        result = []
        active_count = 0
        finished_total = 0
        for (key, name, description, skill, duration_label,
             flag, table, duration_ms) in GAMES:
            enabled = self.env.get(flag, "") == "1"
            item = {
                "key": key, "name": name, "description": description,
                "skill": skill, "duration_label": duration_label,
                "enabled": enabled, "session_id": None, "status": "unavailable",
                "can_resume": False, "progress_percent": 0,
                "progress_label": "No practice started",
                "personal_best": 0, "finished_runs": 0,
                "duration_ms": duration_ms, "last_played_at": None,
                "practice": True, "competitive": False,
            }
            if enabled:
                # Query only tables that should exist under this mode's
                # guarded QA migration. No start, award or write via this path.
                with self.store.connect() as con:
                    row = con.execute(
                        f"SELECT session_id FROM {table} WHERE season_key=? "
                        "AND player_id=? AND day=? AND status IN ('active','paused') "
                        "ORDER BY updated_at_utc DESC LIMIT 1",
                        (self.season, player_id, day)).fetchone()
                    latest = con.execute(
                        f"SELECT MAX(updated_at_utc) FROM {table} "
                        "WHERE season_key=? AND player_id=?",
                        (self.season, player_id)).fetchone()
                engine = _engine(key, self.store, self.season)
                record = engine.record(player_id, now=now)
                item.update({
                    "status": "ready",
                    "personal_best": int(record["personal_best"]),
                    "finished_runs": int(record["finished_runs"]),
                    "last_played_at": latest[0] if latest else None,
                })
                if row is not None:
                    # Timeout processing is authoritative and identical to
                    # resuming that individual mode, without another start.
                    session = engine.session(player_id, row["session_id"], now=now)
                    if session["status"] in ("paused", "active"):
                        progress, label = _progress(key, session)
                        item.update({
                            "session_id": session["session_id"],
                            "status": session["status"],
                            "can_resume": True,
                            "progress_percent": progress,
                            "progress_label": label,
                        })
                        active_count += 1
            finished_total += item["finished_runs"]
            result.append(item)
        available = [i for i in result if i["enabled"]]
        resumable = [i for i in available if i["can_resume"]]
        resumable.sort(key=lambda i: i["last_played_at"] or "", reverse=True)
        suggested = (
            resumable[0]["key"] if resumable else
            next((i["key"] for i in available if not i["finished_runs"]), None) or
            (available[0]["key"] if available else None)
        )
        return {
            "version": "2.9.9f", "player_id": str(player_id),
            "day": day, "practice": True, "competitive": False,
            "modes": result, "available_games": len(available),
            "resumable_games": active_count,
            "completed_practice_runs": finished_total,
            "suggested_mode": suggested,
            "classic": {
                "label": "Classic Arcade · Discord-shared",
                "description": "Classic choice-based games retain their original "
                               "shared passport, daily starts and official records.",
                "separate_records": True,
            },
        }
