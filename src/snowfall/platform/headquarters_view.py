"""Private HQ presentation based on the Discord HQ and trophy engines."""
from dataclasses import asdict
from datetime import datetime, timezone

from snowfall.services.achievements import AchievementEngine
from snowfall.services.combat import DAILY_PVP_CAP, SNOWBALL_CAP, WARMTH_CAP
from snowfall.services.experience import headquarters
from snowfall.services.winter_fun import COSMETICS, RARITY_ORDER, SLOTS, WinterFunEngine


def headquarters_view(store, season, player_id, now=None):
    """Expose only the current player's display data; no new rewards or writes.

    Existing engines may perform their normal resource/day synchronisation.
    Never expose Player records, account identifiers, raw ledger or other players.
    """
    now = now or datetime.now(timezone.utc)
    hq = headquarters(store, season, player_id, now)
    if hq.player is None:
        return {"registered": False, "phase": hq.phase, "day": hq.day}
    cabinet = AchievementEngine(store).cabinet(season, player_id)
    shop = WinterFunEngine(store).shop(season, player_id, now)
    equipped = {slot: key for slot, key in shop.equipped.items()
                if slot in SLOTS and key in shop.unlocked and key in COSMETICS
                and COSMETICS[key].category == slot}
    rarity = max((COSMETICS[key].rarity for key in equipped.values()),
                 default="Common", key=RARITY_ORDER.index)
    return {
        "registered": True, "phase": hq.phase, "day": hq.day,
        "server_time": now, "daily_points": hq.daily_points, "rank": hq.rank,
        "season_points": hq.season_points,
        "caps": {"snowballs": SNOWBALL_CAP, "warmth": WARMTH_CAP, "pvp": DAILY_PVP_CAP},
        "today_pvp": hq.resources.today_pvp,
        "timers": {"snowball": hq.next_snowball, "warmth": hq.next_warmth,
                   "throw": hq.next_throw, "reset": hq.next_reset,
                   "arena": hq.arena_until, "knockout": hq.knockout_due,
                   "shield": hq.shield_due},
        "next_action": hq.next_action, "next_action_route": hq.next_action_route,
        "daily_gift": hq.daily_gift, "bonus_gift": hq.bonus_gift,
        "quests": [asdict(q) for q in hq.quests],
        "title": cabinet.equipped_title, "rarity": rarity,
        "owned_count": len(shop.unlocked), "cosmetic_total": len(COSMETICS),
        "trophies": [{**asdict(t), "rarity": t.rarity} for t in cabinet.trophies],
        "records": {**asdict(cabinet.records), "accuracy": cabinet.records.accuracy},
    }
