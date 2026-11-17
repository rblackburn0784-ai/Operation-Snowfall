"""Season-scoped read model for v0.2.2 illustrated player cards.

Uses the existing purchase ledger and trophy history. The read model does not
award points, change inventory, or grant cosmetics; equipped items are shown
only when the player actually owns them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from snowfall.db.store import Player, Store
from snowfall.services.achievements import AchievementEngine, Trophy
from snowfall.services.combat import CombatEngine, ResourceView, CombatError
from snowfall.services.winter_fun import (
    COSMETICS, RARITY_ORDER, SLOTS, WinterFunEngine, WinterFunError,
)


class ShowcaseError(ValueError):
    pass


@dataclass(frozen=True)
class Showcase:
    player: Player
    resources: ResourceView
    points: int
    title: str
    equipped: dict[str, str]
    badges: tuple[Trophy, ...]
    badge_count: int
    badge_total: int
    owned_count: int
    cosmetic_total: int
    best_rarity: str

    @property
    def featured_badges(self) -> tuple[Trophy, ...]:
        # Always show the badge matching the equipped title first, if earned.
        featured = sorted(self.badges, key=lambda trophy: (
            trophy.title != self.title,
            -RARITY_ORDER.index(trophy.rarity) if trophy.rarity in RARITY_ORDER else 0,
            trophy.badge.casefold(),
        ))
        return tuple(featured[:3])


def showcase(store: Store, season: str, user: int, now: datetime,
             *, public: bool = False) -> Showcase:
    player = store.get_player(season, user)
    if player is None:
        raise ShowcaseError('Register with /snow join to create a player card.')
    if public and player.review_state in ('flagged', 'disqualified'):
        raise ShowcaseError('Your account is under identity review; public cards are unavailable.')

    try:
        combat = CombatEngine(store)
        resources = combat.snapshot(season, user, now)
        score = combat.ledger_total(season, user)
        cabinet = AchievementEngine(store).cabinet(season, user)
        # The existing shop is the only authority for cosmetic ownership.
        snapshot = WinterFunEngine(store).shop(season, user, now)
        equipped = {
            slot: key for slot, key in snapshot.equipped.items()
            if slot in SLOTS and key in snapshot.unlocked and key in COSMETICS
            and COSMETICS[key].category == slot
        }
        owned = len(snapshot.unlocked)
    except (CombatError, WinterFunError) as exc:
        raise ShowcaseError(str(exc)) from exc

    rarity = max((COSMETICS[key].rarity for key in equipped.values()), default="Common",
                 key=lambda value: RARITY_ORDER.index(value))
    return Showcase(player, resources, score, cabinet.equipped_title,
                    equipped, tuple(t for t in cabinet.trophies if t.unlocked),
                    cabinet.unlocked_count, len(cabinet.trophies), owned,
                    len(COSMETICS), rarity)
