"""Player experience read model for the private Headquarters and guided UI.

All game decisions still belong to the existing combat/economy/world engines.
The UI never grants points, items or target eligibility on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, Season, Player, _parse
from snowfall.services.combat import (CombatEngine, ResourceView, THROW_COOLDOWN,
                                      INACTIVITY_WINDOW, DAILY_PVP_CAP)
from snowfall.services.economy import EconomyEngine, QuestView
from snowfall.services.world import WorldEngine, WorldStatus


@dataclass(frozen=True)
class Headquarters:
    player: Player | None
    phase: str
    day: int | None
    season_points: int
    daily_points: int
    rank: int | None
    resources: ResourceView | None
    quests: tuple[QuestView, ...]
    world: WorldStatus | None
    daily_gift: str
    bonus_gift: str
    next_snowball: datetime | None
    next_warmth: datetime | None
    next_throw: datetime | None
    next_reset: datetime | None
    next_action: str
    next_action_route: str = 'hq'
    arena_until: datetime | None = None
    knockout_due: datetime | None = None
    shield_due: datetime | None = None


def _wall_due(season: Season, now: datetime, effective_due: datetime | None) -> datetime | None:
    """Convert an effective-time deadline to UTC wall time; never count down pauses."""
    if effective_due is None or season.phase(now) != 'live':
        return None
    remaining = (effective_due - season.effective_now(now)).total_seconds()
    return now + timedelta(seconds=remaining) if remaining > 0 else None


def _gift_states(store: Store, season: str, user: int, day: int,
                 quests: tuple[QuestView, ...]) -> tuple[str, str]:
    with store.connect() as con:
        opened = {row[0] for row in con.execute(
            "SELECT source FROM mystery_gifts WHERE season_key=? AND discord_user_id=? AND day=?",
            (season, user, day))}
    claimed = sum(q.claimed for q in quests)
    daily = 'Opened' if 'daily' in opened else ('Ready' if claimed >= 1 else 'Claim a quest')
    bonus = 'Not today'
    if day == 4:
        bonus = 'Opened' if 'bonus' in opened else ('Ready' if claimed == 3 else 'Claim all three')
    return daily, bonus


def headquarters(store: Store, season_key: str, user_id: int, now: datetime) -> Headquarters:
    """Render current state for one account, respecting pauses and practice sessions."""
    now = as_utc(now)
    season = store.season(season_key)
    phase = season.phase(now)
    player = store.get_player(season_key, user_id)
    day = season.day(now)
    if player is None:
        return Headquarters(None, phase, day, 0, 0, None, None, (), None, 'Locked',
                            'Not today', None, None, None, None,
                            'Register your MafiaReturns username and choose a city.',
                            'join' if phase in ('registration', 'ready', 'live', 'paused') else 'guide')

    engine = CombatEngine(store)
    resource = engine.snapshot(season_key, user_id, now)
    total = engine.ledger_total(season_key, user_id)
    # The canonical ranking implementation caps its query at 100; never report
    # an invented exact place when outside the visible leaderboard.
    ranks = engine.leaderboard(season_key, 100)
    rank = (next((i for i, entry in enumerate(ranks, 1) if entry[2] == user_id), None)
            if total > 0 else None)
    daily = 0
    quests: tuple[QuestView, ...] = ()
    world = None
    gift, bonus = 'Not open', 'Not today'
    if day is not None:
        with store.connect() as con:
            daily = int(con.execute(
                "SELECT COALESCE(SUM(points),0) FROM score_ledger "
                "WHERE season_key=? AND player_id=? AND day=?",
                (season_key, user_id, day)).fetchone()[0])
        quests = tuple(EconomyEngine(store).quests(season_key, user_id, now))
        gift, bonus = _gift_states(store, season_key, user_id, day, quests)
        world = WorldEngine(store).status(season_key, user_id, now)

    # Arena participation is optional. This is a read-only hint; the combat
    # engine alone decides whether a player is targetable or may score.
    with store.connect() as con:
        active_row = con.execute(
            "SELECT last_eligible_action_at FROM player_resources "
            "WHERE season_key=? AND discord_user_id=?",
            (season_key, user_id),
        ).fetchone()
    active_at = _parse(active_row[0]) if active_row else None
    arena_until = _wall_due(season, now, active_at + INACTIVITY_WINDOW if active_at else None)
    game_now = season.effective_now(now)
    knockout_due = _wall_due(season, now, resource.knockout_until)
    shield_due = _wall_due(season, now, resource.shield_until)
    ball_due = _wall_due(season, now, resource.next_snowball_at)
    warm_due = _wall_due(season, now, resource.next_warmth_at)
    throw_due = _wall_due(season, now,
                          resource.last_throw_at + THROW_COOLDOWN if resource.last_throw_at else None)
    reset_due = _wall_due(season, now, season.started_at + timedelta(days=day)
                          if season.started_at and day else None)

    if phase == 'paused':
        action, route = 'Event paused: regeneration and daily timers are frozen.', 'hq'
    elif phase in ('closed', 'finalized'):
        action, route = 'The event has finished. Check the final standings.', 'rankings'
    elif phase in ('not_open', 'registration', 'ready'):
        action, route = ('Registration complete. The host will announce the kickoff.', 'guide')
    elif resource.knockout_until and resource.knockout_until > game_now:
        action, route = 'Recover from your knockout; the Winter Arcade is available meanwhile.', 'winter'
    elif any(q.progress >= q.target and not q.claimed for q in quests):
        action, route = 'Claim a completed daily mission to collect its rewards.', 'quests'
    elif gift == 'Ready' or bonus == 'Ready':
        action, route = 'Open the mystery present you have unlocked.', 'quests'
    elif resource.snowballs == 0:
        action, route = 'Snowballs are regenerating. Visit the Winter Arcade in the meantime.', 'winter'
    elif throw_due is not None:
        action, route = 'Throw cooldown is active; check your quests while it runs.', 'quests'
    elif arena_until is None:
        action, route = 'Enter the arena to let rivals challenge you for 36 active hours.', 'player'
    elif world and world.boss_enabled and world.boss_attempts < 6 and world.boss_points < 50:
        action, route = 'Help take on the Snow Don!', 'world'
    elif world and world.siege_attempts < 4 and world.siege_points < 50:
        action, route = 'Help your city attack its fortress!', 'world'
    elif resource.today_pvp < DAILY_PVP_CAP:
        action, route = 'Find a rival-city player for your next snowball fight.', 'fight'
    else:
        action, route = 'Try the Winter Arcade or review your daily progress.', 'winter'
    return Headquarters(player, phase, day, total, daily, rank, resource, quests, world,
                        gift, bonus, ball_due, warm_due, throw_due, reset_due, action,
                        route, arena_until, knockout_due, shield_due)
