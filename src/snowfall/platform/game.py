"""Platform-neutral application facade. Discord and HTTP call the same engines.

The game's existing BIGINT user field is the canonical player ID for the
shared backend; the platform identity layer resolves verified identities
before invoking this facade. No separate web scores, rewards or boss state.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from snowfall.db.store import Store
from snowfall.services.boss_raid import RaidEngine
from snowfall.services.combat import CombatEngine
from snowfall.services.economy import EconomyEngine
from snowfall.services.winter_fun import WinterFunEngine
from snowfall.services.world import WorldEngine


def _time() -> datetime:
    return datetime.now(timezone.utc)


_PLAYER_ID_FIELDS = {"player_id", "user_id", "discord_user_id", "attacker_id", "target_id"}


def _wire(value):
    """Serialize BIGINT player references as decimal strings for JavaScript safety."""
    if isinstance(value, dict):
        return {k: str(v) if k in _PLAYER_ID_FIELDS and isinstance(v, int)
                else _wire(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(v) for v in value]
    return value


class SharedGame:
    def __init__(self, store: Store, season: str):
        self.store = store
        self.season = season

    def register(self, player_id: int, mr_name: str, city: str, *, now=None) -> dict:
        player = self.store.register(self.season, player_id, mr_name, city, now or _time())
        return {"player_id": str(player.discord_user_id), "mr_username": player.mr_username,
                "city": player.city, "review_state": player.review_state}

    def me(self, player_id: int, *, now=None) -> dict:
        now = now or _time()
        season = self.store.season(self.season)
        player = self.store.get_player(self.season, player_id)
        response = {"player_id": str(player_id), "season": self.season,
                    "phase": season.phase(now), "day": season.day(now),
                    "registered": bool(player)}
        if player is None:
            return response
        combat = CombatEngine(self.store)
        snapshot = combat.snapshot(self.season, player_id, now)
        response.update({
            "mr_username": player.mr_username, "city": player.city,
            "review_state": player.review_state,
            "score": combat.ledger_total(self.season, player_id),
            "resources": asdict(snapshot),
        })
        return response

    def headquarters(self, player_id: int, *, now=None) -> dict:
        from snowfall.platform.headquarters_view import headquarters_view
        return headquarters_view(self.store, self.season, player_id, now)

    def progress(self, player_id: int, *, now=None) -> dict:
        """Cross-platform comparison: one canonical game's persistent values.

        This intentionally queries the same engines as the browser and
        Discord adapters; there is no separate sync table or mirrored score.
        Regeneration may change live resource values between requests.
        """
        now = now or _time()
        profile = self.me(player_id, now=now)
        if not profile["registered"]:
            return {"player_id": str(player_id), "season": self.season,
                    "registered": False}
        items = self.inventory(player_id, now=now)
        world = self.world(player_id, now=now)
        return {
            "player_id": str(player_id),
            "season": self.season,
            "registered": True,
            "mr_username": profile["mr_username"],
            "city": profile["city"],
            "score": profile["score"],
            "snowballs": profile["resources"]["snowballs"],
            "snowflakes": items["snowflakes"],
            "warmth": items["warmth"],
            "inventory": items["quantities"],
            "boss_hp": world["boss_hp"],
            "boss_max_hp": world["boss_max_hp"],
        }

    def leaderboard(self, *, limit=25) -> list[dict]:
        return [{"mr_username": name, "city": city, "player_id": str(player_id),
                 "score": score} for name, city, player_id, score in
                CombatEngine(self.store).leaderboard(self.season, limit=limit)]

    def targets(self, player_id: int, *, now=None) -> list[dict]:
        views = CombatEngine(self.store).targets(self.season, player_id, now or _time())
        return [{"player_id": str(v.discord_user_id), "mr_username": v.mr_username,
                 "city": v.city, "warmth": v.warmth, "hits_remaining": v.hits_remaining}
                for v in views]

    def ready(self, player_id: int, *, now=None) -> dict:
        until = CombatEngine(self.store).ready(self.season, player_id, now or _time())
        return {"eligible_until": until}

    def throw(self, player_id: int, target_player_id: int, style: str,
              interaction_id: str, *, now=None) -> dict:
        result = CombatEngine(self.store).throw(
            self.season, player_id, target_player_id, style, interaction_id, now or _time(),
        )
        return _wire(asdict(result))

    def boss(self, player_id: int, interaction_id: str, *, now=None) -> dict:
        result = WorldEngine(self.store).attack(
            self.season, player_id, "boss", interaction_id, now or _time(),
        )
        return _wire(asdict(result))

    def siege(self, player_id: int, interaction_id: str, *, now=None) -> dict:
        result = WorldEngine(self.store).attack(
            self.season, player_id, "siege", interaction_id, now or _time(),
        )
        return _wire(asdict(result))

    def raid(self, *, day: int) -> dict:
        return _wire(asdict(RaidEngine(self.store).report(self.season, day)))

    def world(self, player_id: int, *, now=None) -> dict:
        return _wire(asdict(WorldEngine(self.store).status(
            self.season, player_id, now or _time())))

    def cities(self, *, now=None) -> list[dict]:
        return _wire([asdict(item) for item in
                      WorldEngine(self.store).standings(self.season, now or _time())])

    def quests(self, player_id: int, *, now=None) -> list[dict]:
        return _wire([asdict(q) for q in
                      EconomyEngine(self.store).quests(self.season, player_id, now or _time())])

    def claim_quest(self, player_id: int, quest: str, *, now=None) -> dict:
        return _wire(asdict(EconomyEngine(self.store).claim_quest(
            self.season, player_id, quest, now or _time())))

    def inventory(self, player_id: int, *, now=None) -> dict:
        return asdict(EconomyEngine(self.store).inventory(
            self.season, player_id, now or _time(),
        ))

    def craft(self, player_id: int, item: str, interaction_id: str, *, now=None) -> dict:
        return asdict(EconomyEngine(self.store).craft(
            self.season, player_id, item, interaction_id, now or _time(),
        ))

    def wardrobe(self, player_id: int, *, now=None) -> dict:
        return asdict(WinterFunEngine(self.store).shop(
            self.season, player_id, now or _time(),
        ))

    def purchase(self, player_id: int, item: str, interaction_id: str, *, now=None) -> dict:
        text = WinterFunEngine(self.store).buy(
            self.season, player_id, item, interaction_id, now or _time(),
        )
        return {"message": text}

    def equip(self, player_id: int, item: str, *, now=None) -> dict:
        return {"message": WinterFunEngine(self.store).equip(
            self.season, player_id, item, now or _time(),
        )}
