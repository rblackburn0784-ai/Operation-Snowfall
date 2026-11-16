"""Announcement templates and snapshot reads, independent of the Discord API."""
from __future__ import annotations

from datetime import datetime, timezone
from snowfall.db.store import Store
from snowfall.services.world import THEMES

DAY_DETAILS = (
    ("The gates are open!", "Today: opening PvP barrage, daily quests, Snow Don and six city forts. "
     "Pick a rival city and start earning individual championship points."),
    ("Fortification Frenzy!", "Today's perk: Fort Kits cost **8 Snowflakes** rather than 10. "
     "Build your defences, clear your missions and attack the city forts."),
    ("The Great Whiteout!", "Today's perk: **+10 points** on your first claimed daily quest. "
     "The snowstorm is on; Snow Don and city sieges reset for a fresh day."),
    ("Christmas Supply Drop!", "Today's perk: complete **all three quests** to unlock "
     "an extra **non-Golden** mystery present. Your usual present is still available."),
    ("Snow Don's Revenge!", "Today's perk: your **first boss attempt** awards "
     "**+10 bonus points**. The Don has returned; find your team's new fort too."),
    ("Blizzard Blitz!", "Today's perk: **+20 bonus points** for your second "
     "legal PvE attack. Balance your boss and siege attempts strategically."),
    ("The Last Snowfall!", "Final 24 effective hours! Finish your remaining quests, "
     "boss attempts and city sieges. Individual rankings decide prizes; cities earn glory."),
)


def daily_announcement(day: int, *, paused: bool = False) -> str:
    if not 1 <= day <= 7:
        raise ValueError("Game day must be between 1 and 7")
    headline, detail = DAY_DETAILS[day - 1]
    paused_note = ("\n⏸️ The game is paused; actions resume when a host restarts the clock."
                   if paused else "")
    return (f"❄️ **OPERATION SNOWFALL — DAY {day}/7**\n"
            f"### {THEMES[day - 1]} — {headline}\n"
            f"{detail}\n\n"
            "☃️ **Snow Don:** six attempts per player today.\n"
            "🏰 **City Siege:** four attempts per player today, with training rubble after a clear.\n"
            "🎁 **Missions and presents:** refresh every event day.\n"
            "🏆 **#leaderboard:** refreshed every five minutes; **individual prizes only**."
            + paused_note)


def registration_announcement(starts_at: datetime, event_name: str) -> str:
    when = int(starts_at.astimezone(timezone.utc).timestamp())
    return (f"❄️ **{event_name} — REGISTRATION IS OPEN!**\n"
            "The seven-day snowball battle begins "
            f"<t:{when}:F> (<t:{when}:R>).\n"
            "Register your MafiaReturns username and choose your city with `/snow join`. "
            "Identity is self-declared; staff can review disputes.\n"
            "🏆 Prizes are **individual only**. The six-city championship is for bragging rights.")


def waiting_announcement(event_name: str) -> str:
    return (f"⏳ **{event_name} — READY FOR KICKOFF**\n"
            "Registration is open, but snowball combat has not begun. "
            "A host will start the seven-day clock; please don't begin PvP yet.")


def completed_announcement(event_name: str) -> str:
    return (f"🏁 **{event_name} — THE LAST SNOWBALL HAS LANDED!**\n"
            "Seven effective days have ended. The leaderboard now shows the final "
            "competition positions pending organiser review.\n"
            "🏆 Only **individual** awards have prizes; city champions earn bragging rights. "
            "Kat will confirm official winners and prizes separately.")


def boss_defeated_announcement(day: int) -> str:
    return (f"☃️💥 **SNOW DON DEFEATED — DAY {day}/7!**\n"
            "The giant snowman has fallen! Players who missed the shared fight can "
            "still complete their **six daily scoring attempts** against training echoes. "
            "The next boss arrives on the following event day.")


def world_snapshot(store: Store, season_key: str, day: int | None) -> tuple[str, str]:
    """Return boss and siege summary for leaderboard display; read-only."""
    if day is None:
        return "Awaiting kickoff", "Six city fortresses will appear once play begins"
    with store.connect() as con:
        boss = con.execute("SELECT boss_hp,boss_initial_hp FROM world_days "
                           "WHERE season_key=? AND day=?", (season_key, day)).fetchone()
        settings = con.execute("SELECT boss_enabled FROM world_settings WHERE season_key=?",
                               (season_key,)).fetchone()
        forts = con.execute("SELECT COUNT(*) AS total, "
                            "SUM(CASE WHEN hp=0 THEN 1 ELSE 0 END) AS cleared "
                            "FROM world_sieges WHERE season_key=? AND day=?",
                            (season_key, day)).fetchone()
    if not boss:
        boss_text = "Spawning for this event day"
    elif settings is not None and not settings["boss_enabled"]:
        boss_text = "Disabled by the event organiser"
    elif boss["boss_hp"] <= 0:
        boss_text = "Defeated — personal training echoes available"
    else:
        boss_text = f"{boss['boss_hp']:,}/{boss['boss_initial_hp']:,} HP remaining"
    cleared = int(forts["cleared"] or 0)
    return boss_text, f"{cleared}/6 city fortresses cleared today"


def boss_is_defeated(store: Store, season_key: str, day: int) -> bool:
    if not 1 <= day <= 7:
        return False
    with store.connect() as con:
        row = con.execute("SELECT w.boss_hp,COALESCE(s.boss_enabled,1) AS enabled "
                          "FROM world_days w LEFT JOIN world_settings s "
                          "ON s.season_key=w.season_key "
                          "WHERE w.season_key=? AND w.day=?",
                          (season_key, day)).fetchone()
    return bool(row and row["enabled"] and row["boss_hp"] == 0)
