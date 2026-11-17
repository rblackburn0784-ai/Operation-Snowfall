"""Seven rotating three-mission sets; the approved reward budget never changes.

Keys remain throws/rivals/community for compatibility with quest claims, item
rewards, the final scoreboard and pre-existing daily rows. Each daily variant
has an achievable PvE/preparation fallback when few PvP opponents are online.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class Mission:
    key: str
    title: str
    target: int
    detail: str
    metric: str


# Individual award remains 20 points + up to two Snowflakes per claim.
# These variants only change how completion is earned, not how it's paid.
MISSION_POOLS: dict[int, tuple[Mission, Mission, Mission]] = {
    1: (Mission("throws", "Get your gloves on", 5, "Make five legal attacks.", "total"),
        Mission("rivals", "Spread the misery", 2, "Hit two different rival players.", "unique"),
        Mission("community", "Community effort", 1, "Help a siege/boss or prepare an item.", "help")),
    2: (Mission("throws", "Fortification Drill", 4, "Make four legal attacks.", "total"),
        Mission("rivals", "Frontline Skirmish", 2, "Land two hits, or three PvE hits.", "hits_or_pve"),
        Mission("community", "Barricade Builder", 1, "Attack an NPC or prepare equipment.", "help")),
    3: (Mission("throws", "Whiteout Barrage", 5, "Make five legal attacks.", "total"),
        Mission("rivals", "Snowstorm Hunters", 2, "Hit two rivals, or land three PvE hits.", "unique_or_pve"),
        Mission("community", "Scout the Streets", 1, "Make a PvE attack or prepare equipment.", "help")),
    4: (Mission("throws", "Holiday Hustle", 4, "Make four legal attacks.", "total"),
        Mission("rivals", "Citywide Clash", 2, "Land two hits, or three PvE hits.", "hits_or_pve"),
        Mission("community", "Supply Run", 1, "Craft/use equipment or take on an NPC.", "help")),
    5: (Mission("throws", "The Don's Hitlist", 3, "Make three boss/siege attacks, or four PvP throws.", "pve_or_pvp"),
        Mission("rivals", "Avenge the Crew", 2, "Hit two rivals, or land three PvE hits.", "unique_or_pve"),
        Mission("community", "Winter Preparation", 1, "Prepare equipment or attack an NPC.", "help")),
    6: (Mission("throws", "Blizzard Barrage", 5, "Make five legal attacks.", "total"),
        Mission("rivals", "Frostbite Crossfire", 2, "Land two hits, or three PvE hits.", "hits_or_pve"),
        Mission("community", "Hold the Line", 1, "Prepare equipment or attack an NPC.", "help")),
    7: (Mission("throws", "The Last Snowfall", 5, "Make five legal attacks.", "total"),
        Mission("rivals", "Final Score Settler", 2, "Hit two rivals, or land three PvE hits.", "unique_or_pve"),
        Mission("community", "Final Supply Check", 1, "Prepare equipment or attack an NPC.", "help")),
}


def missions_for_day(day: int | None) -> tuple[Mission, Mission, Mission]:
    return MISSION_POOLS.get(day or 1, MISSION_POOLS[1])


def _count(con: sqlite3.Connection, query: str, parameters: tuple) -> int:
    return int(con.execute(query, parameters).fetchone()[0] or 0)


def daily_progress(con: sqlite3.Connection, season: str, user: int, day: int) -> dict[str, int]:
    """Calculate progress from immutable combat/item event rows. No score writes."""
    pvp = _count(con, "SELECT COUNT(*) FROM combat_events WHERE season_key=? AND attacker_id=? AND day=?",
                 (season, user, day))
    hits = _count(con, "SELECT COUNT(*) FROM combat_events WHERE season_key=? AND attacker_id=? AND day=? "
                  "AND hit=1 AND points_awarded>0", (season, user, day))
    unique = _count(con, "SELECT COUNT(DISTINCT target_id) FROM combat_events WHERE season_key=? "
                    "AND attacker_id=? AND day=? AND hit=1 AND points_awarded>0", (season, user, day))
    pve = _count(con, "SELECT COUNT(*) FROM pve_events WHERE season_key=? AND attacker_id=? AND day=?",
                 (season, user, day))
    pve_hits = _count(con, "SELECT COUNT(*) FROM pve_events WHERE season_key=? AND attacker_id=? "
                      "AND day=? AND hit=1", (season, user, day))
    preparation = _count(con, "SELECT COUNT(*) FROM item_events WHERE season_key=? "
                         "AND discord_user_id=? AND day=? AND operation IN ('craft','use','guard_on')",
                         (season, user, day))
    def progress(kind: str) -> int:
        if kind == "total":
            return pvp + pve
        if kind == "unique":
            return unique
        if kind == "help":
            return pve + preparation
        if kind == "unique_or_pve":
            return max(unique, pve_hits * 2 // 3)
        if kind == "hits_or_pve":
            return max(hits, pve_hits * 2 // 3)
        if kind == "pve_or_pvp":
            return max(pve, pvp * 3 // 4)
        raise ValueError(f"Unknown mission metric: {kind}")
    return {mission.key: progress(mission.metric) for mission in missions_for_day(day)}
