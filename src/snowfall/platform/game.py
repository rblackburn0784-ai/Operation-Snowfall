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
        """Eligible rivals, including their actual equipped public cosmetic outfit.

        Only the server-validated, unlocked cosmetic slots are exposed; no
        inventory, private profile or linked account identifiers are leaked.
        The existing combat eligibility and attack calculations remain intact.
        """
        from snowfall.services.winter_fun import COSMETICS, SLOTS

        views = CombatEngine(self.store).targets(self.season, player_id, now or _time())
        appearance = {v.discord_user_id: {} for v in views}
        if views:
            placeholders = ",".join("?" for _ in views)
            with self.store.connect() as con:
                rows = con.execute(
                    """SELECT e.discord_user_id,e.category,e.cosmetic_key
                       FROM cosmetic_equipped e
                       JOIN cosmetic_unlocks u
                         ON u.season_key=e.season_key
                        AND u.discord_user_id=e.discord_user_id
                        AND u.cosmetic_key=e.cosmetic_key
                       WHERE e.season_key=?
                         AND e.discord_user_id IN (""" + placeholders + ")",
                    (self.season, *(v.discord_user_id for v in views)),
                ).fetchall()
            for user, slot, key in rows:
                cosmetic = COSMETICS.get(key)
                if slot in SLOTS and cosmetic is not None and cosmetic.category == slot:
                    appearance[user][slot] = key
        return [{"player_id": str(v.discord_user_id), "mr_username": v.mr_username,
                 "city": v.city, "warmth": v.warmth,
                 "hits_remaining": v.hits_remaining,
                 "appearance": appearance[v.discord_user_id]}
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

    def activities(self, player_id: int, *, now=None) -> dict:
        from snowfall.platform.player_activities import activities_view
        return activities_view(self.store, self.season, player_id, now or _time())

    def activity_action(self, player_id: int, action: str, item: str, day: int | None,
                        interaction_id: str, *, now=None) -> dict:
        from snowfall.platform.player_activities import perform_activity
        return perform_activity(self.store, self.season, player_id, action, item,
                                day, interaction_id, now or _time())

    def arcade_lobby(self, player_id: int, *, now=None) -> dict:
        from snowfall.services.social_arcade import SocialArcadeEngine, GAMES, STAMPS, DAILY_GAME_CAP
        lobby = SocialArcadeEngine(self.store).lobby(self.season, player_id, now or _time())
        return {**asdict(lobby), "player_id": str(player_id),
                "games": [asdict(spec) for spec in GAMES.values()],
                "stamp_labels": STAMPS, "daily_cap": DAILY_GAME_CAP}

    def arcade_session(self, player_id: int, session_id: str, *, now=None) -> dict:
        from snowfall.services.social_arcade import SocialArcadeEngine
        return asdict(SocialArcadeEngine(self.store).session(
            self.season, player_id, session_id, now or _time()))

    def arcade_start(self, player_id: int, mode: str, day: int, attempts_today: int,
                     *, now=None) -> dict:
        from snowfall.services.social_arcade import SocialArcadeEngine
        return asdict(SocialArcadeEngine(self.store).begin(
            self.season, player_id, mode, now or _time(),
            expected_day=day, expected_used=attempts_today))

    def arcade_move(self, player_id: int, session_id: str, step: int, choice: str,
                    interaction_id: str, *, now=None) -> dict:
        from snowfall.services.social_arcade import SocialArcadeEngine
        return asdict(SocialArcadeEngine(self.store).move(
            self.season, player_id, session_id, step, choice, interaction_id,
            now or _time()))

    # Web-only v2.9.9 practice; deliberately isolated from SocialArcadeEngine.
    def arcade_practice_start(self, player_id: int, mode: str, *, now=None) -> dict:
        from snowfall.platform.interactive_arcade import InteractiveArcadePractice
        return InteractiveArcadePractice(self.store, self.season).start(player_id, mode, now=now)

    def arcade_practice_session(self, player_id: int, session_id: str, *, now=None) -> dict:
        from snowfall.platform.interactive_arcade import InteractiveArcadePractice
        return InteractiveArcadePractice(self.store, self.season).session(
            player_id, session_id, now=now)

    def arcade_practice_save(self, player_id: int, session_id: str, revision: int,
                             state: dict, *, finish=False, now=None) -> dict:
        from snowfall.platform.interactive_arcade import InteractiveArcadePractice
        return InteractiveArcadePractice(self.store, self.season).save(
            player_id, session_id, revision, state, finish=finish, now=now)

    # v2.9.9a: verified hit detection and replay-safe practice scores.
    # These never mutate the Discord classic arcade or any event resource.
    def gallery_start(self, player_id: int, *, now=None) -> dict:
        from snowfall.platform.gallery_arcade import GalleryEngine
        return GalleryEngine(self.store, self.season).start(player_id, now=now)

    def gallery_session(self, player_id: int, session_id: str, *, now=None) -> dict:
        from snowfall.platform.gallery_arcade import GalleryEngine
        return GalleryEngine(self.store, self.season).session(
            player_id, session_id, now=now)

    def gallery_control(self, player_id: int, session_id: str, action: str,
                        *, now=None) -> dict:
        from snowfall.platform.gallery_arcade import GalleryEngine
        return GalleryEngine(self.store, self.season).control(
            player_id, session_id, action, now=now)

    def gallery_shoot(self, player_id: int, session_id: str, shot_index: int,
                      x: int, y: int, interaction_id: str, *, now=None) -> dict:
        from snowfall.platform.gallery_arcade import GalleryEngine
        return GalleryEngine(self.store, self.season).shoot(
            player_id, session_id, shot_index, x, y, interaction_id, now=now)

    def gallery_record(self, player_id: int, *, now=None) -> dict:
        from snowfall.platform.gallery_arcade import GalleryEngine
        return GalleryEngine(self.store, self.season).record(player_id, now=now)

    # v2.9.9b: separate server-audited QA-only Frozen Safecracker.
    def safe_start(self, player_id: int, *, now=None) -> dict:
        from snowfall.platform.safecracker_arcade import SafecrackerEngine
        return SafecrackerEngine(self.store, self.season).start(player_id, now=now)

    def safe_session(self, player_id: int, session_id: str, *, now=None) -> dict:
        from snowfall.platform.safecracker_arcade import SafecrackerEngine
        return SafecrackerEngine(self.store, self.season).session(
            player_id, session_id, now=now)

    def safe_control(self, player_id: int, session_id: str, action: str,
                     *, now=None) -> dict:
        from snowfall.platform.safecracker_arcade import SafecrackerEngine
        return SafecrackerEngine(self.store, self.season).control(
            player_id, session_id, action, now=now)

    def safe_move(self, player_id: int, session_id: str, action_seq: int, action: str,
                  ticks: int, interaction_id: str, *, now=None) -> dict:
        from snowfall.platform.safecracker_arcade import SafecrackerEngine
        return SafecrackerEngine(self.store, self.season).move(
            player_id, session_id, action_seq, action, ticks, interaction_id,
            now=now)

    def safe_record(self, player_id: int, *, now=None) -> dict:
        from snowfall.platform.safecracker_arcade import SafecrackerEngine
        return SafecrackerEngine(self.store, self.season).record(player_id, now=now)

    def arcade_board(self, player_id: int, mode: str, *, daily=False, now=None) -> dict:
        from snowfall.services.social_arcade import SocialArcadeEngine
        engine = SocialArcadeEngine(self.store)
        now = now or _time()
        return {"mode": mode, "daily": daily,
                "players": [{"name": row.name, "city": row.city, "best": row.best,
                             "games": row.games} for row in engine.leaderboard(
                                 self.season, player_id, mode, now, daily=daily)],
                "cities": [asdict(row) for row in engine.city_table(
                    self.season, player_id, now, daily=daily)]}
