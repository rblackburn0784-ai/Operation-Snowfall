"""Player experience read model for the private Headquarters and guided UI.

All game decisions still belong to the existing combat/economy/world engines.
The UI never grants points, items or target eligibility on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, Season, Player
from snowfall.services.combat import CombatEngine, ResourceView, THROW_COOLDOWN
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
                            'Register your MafiaReturns username and choose a city.')

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

    game_now = season.effective_now(now)
    ball_due = _wall_due(season, now, resource.next_snowball_at)
    warm_due = _wall_due(season, now, resource.next_warmth_at)
    throw_due = _wall_due(season, now,
                          resource.last_throw_at + THROW_COOLDOWN if resource.last_throw_at else None)
    reset_due = _wall_due(season, now, season.started_at + timedelta(days=day)
                          if season.started_at and day else None)

    if phase == 'paused':
        action = 'Event paused: regeneration and daily timers are frozen.'
    elif phase in ('closed', 'finalized'):
        action = 'The event has finished. Check the final standings.'
    elif phase in ('not_open', 'registration', 'ready'):
        action = 'Registration complete. The host will announce the official kickoff.'
    elif resource.knockout_until and resource.knockout_until > game_now:
        action = 'Recover from your knockout before attacking again.'
    elif any(q.progress >= q.target and not q.claimed for q in quests):
        action = 'You have a finished quest ready to claim!'
    elif gift == 'Ready' or bonus == 'Ready':
        action = 'Open your unlocked mystery present!'
    elif resource.snowballs == 0:
        action = 'You are out of snowballs. Try again after regeneration.'
    elif throw_due is not None:
        action = 'Your shared 30-second throw cooldown is active.'
    else:
        action = 'Ready to play: find a rival, fight the Snow Don or help your city.'
    return Headquarters(player, phase, day, total, daily, rank, resource, quests, world,
                        gift, bonus, ball_due, warm_due, throw_due, reset_due, action)
