"""Read-only web presentation of the Discord Snow Don's actual daily state."""
from datetime import datetime, timezone

from snowfall.graphics.snow_don import health_stage
from snowfall.services.boss_raid import RaidEngine
from snowfall.services.boss_personality import BOSS_PHASES

SCENES = "/art/v290/boss/"
PORTRAITS = "/art/boss/"


def visuals(hp: int, maximum: int, *, enabled: bool = True) -> dict:
    """Use the bot's exact integer tier function and existing cinematic assets.

    The four illustrated cinematic scenes are not ten distinct damage portraits.
    Assign them to the existing 75/50/25 announcement thresholds.
    """
    if maximum <= 0 or not enabled:
        return {"tier": None, "state": "disabled" if not enabled else "waiting",
                "portrait": PORTRAITS + "snow_don_100.png",
                "splash": SCENES + "phase_ice.webp",
                "title": "Boss disabled" if not enabled else "Awaiting the Snow Don"}
    hp = max(0, min(hp, maximum))
    if hp == 0:
        return {"tier": 0, "state": "defeated", "portrait": SCENES + "snow_don_0.webp",
                "splash": SCENES + "final_defeat.webp", "title": "The Final Snowfall"}
    tier = health_stage(hp, maximum)
    scene, state, title = "phase_ice", "healthy", "The Don Rules the Streets"
    for (threshold, label, _), art, phase in zip(
        BOSS_PHASES, ("rage_tommy", "rage_snowball", "phase_frostfire"),
        ("cracked", "wounded", "critical"),
    ):
        if hp * 100 <= threshold * maximum:
            scene, state, title = art, phase, label
    return {"tier": tier, "state": state, "portrait": PORTRAITS + f"snow_don_{tier}.png",
            "splash": SCENES + scene + ".webp", "title": title}


def current_boss(game, now=None) -> dict:
    """Read current day's persisted raid; never initialise days or award anything."""
    now = now or datetime.now(timezone.utc)
    season = game.store.season(game.season)
    phase = season.phase(now)
    day = season.day(now)
    if phase in ("closed", "finalized"):
        # Honour the final actually spawned day, not hypothetical future bosses.
        with game.store.connect() as con:
            row = con.execute("SELECT MAX(day) FROM world_days WHERE season_key=?",
                              (game.season,)).fetchone()
        day = int(row[0]) if row and row[0] else None
    result = {"day": day, "season_phase": phase, "hp": None, "max_hp": None,
              "hit_count": None, "misses": None, "contributors": None,
              "echo_attacks": None, **visuals(0, 0)}
    if day is None:
        return result
    try:
        report = RaidEngine(game.store).report(game.season, day)
    except ValueError as exc:
        if str(exc) != "The Snow Don has not spawned for this day.":
            raise
        return result
    return {**result, "hp": report.remaining_hp, "max_hp": report.max_hp,
            "hit_count": report.hit_count, "misses": report.misses,
            "contributors": report.contributors, "echo_attacks": report.echo_attacks,
            **visuals(report.remaining_hp, report.max_hp, enabled=report.enabled)}
