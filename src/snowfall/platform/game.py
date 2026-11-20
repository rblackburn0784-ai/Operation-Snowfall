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


class SharedGame:
    def __init__(self, store: Store, season: str):
        self.store = store
        self.season = season

    def register(self, player_id: int, mr_name: str, city: str, *, now=None) -> dict:
        player = self.store.register(self.season, player_id, mr_name, city, now or _time())
        return {"player_id": player.discord_user_id, "mr_username": player.mr_username,
                "city": player.city, "review_state": player.review_state}

    def me(self, player_id: int, *, now=None) -> dict:
        now = now or _time()
        season = self.store.season(self.season)
        player = self.store.get_player(self.season, player_id)
        response = {"player_id": player_id, "season": self.season,
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

    def leaderboard(self, *, limit=25) -> list[dict]:
        return [{"mr_username": name, "city": city, "player_id": player_id,
                 "score": score} for name, city, player_id, score in
                CombatEngine(self.store).leaderboard(self.season, limit=limit)]

    def targets(self, player_id: int, *, now=None) -> list[dict]:
        views = CombatEngine(self.store).targets(self.season, player_id, now or _time())
        return [{"player_id": v.discord_user_id, "mr_username": v.mr_username,
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
        return asdict(result)

    def boss(self, player_id: int, interaction_id: str, *, now=None) -> dict:
        result = WorldEngine(self.store).attack(
            self.season, player_id, "boss", interaction_id, now or _time(),
        )
        return asdict(result)

    def siege(self, player_id: int, interaction_id: str, *, now=None) -> dict:
        result = WorldEngine(self.store).attack(
            self.season, player_id, "siege", interaction_id, now or _time(),
        )
        return asdict(result)

    def raid(self, *, day: int) -> dict:
        return asdict(RaidEngine(self.store).report(self.season, day))

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
