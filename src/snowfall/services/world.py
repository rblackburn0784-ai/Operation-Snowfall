"""v0.1.4 group gameplay: deterministic daily boss/siege, score snapshots, and themes.

This module has no Discord dependency. All mutations are SQLite BEGIN IMMEDIATE;
public and personal PvE use the existing pause-adjusted seven-day clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import secrets
import sqlite3
from typing import Protocol

from snowfall.core.clock import as_utc
from snowfall.db.store import CITIES, Store, Season, _parse, _timestamp
from snowfall.services.combat import (
    CombatEngine, CombatError, SNOWBALL_CAP, THROW_COOLDOWN, _game_now,
)

THEMES = (
    "Opening Barrage", "Fortification Frenzy", "The Great Whiteout",
    "Christmas Supply Drop", "Snow Don's Revenge", "Blizzard Blitz",
    "The Last Snowfall",
)
BOSS_LIMIT = 6
SIEGE_LIMIT = 4
BOSS_CAP = 50
SIEGE_CAP = 50
PVE_HIT_CHANCE = 0.65


class WorldError(CombatError):
    """Rejected PvE action; no ammo or score spent."""


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class WorldStatus:
    day: int | None
    phase: str
    theme: str | None
    boss_hp: int
    boss_max_hp: int
    boss_attempts: int
    boss_points: int
    siege_hp: int
    siege_max_hp: int
    siege_attempts: int
    siege_points: int
    city: str | None
    boss_enabled: bool = True


@dataclass(frozen=True)
class PveResult:
    interaction_id: str
    kind: str
    day: int
    city: str
    hit: bool
    damage: int
    points: int
    theme_points: int
    hp_after: int
    max_hp: int
    echo: bool
    final_blow: bool
    repeated: bool = False


@dataclass(frozen=True)
class CityStanding:
    city: str
    score_x100: int
    active_players: int
    siege_clears: int
    daily_wins: int
    siege_damage: int
    qualifying_today: bool
    todays_score_x100: int
    provisional: bool


class WorldEngine:
    def __init__(self, store: Store, rng: RandomSource | None = None):
        self.store = store
        self.rng = rng if rng is not None else secrets.SystemRandom()

    def configure_boss(self, season_key: str, actor: int, enabled: bool,
                       hp_override: int | None, reason: str, now: datetime) -> None:
        """Host-only caller: pre-start settings, with mandatory audit entry."""
        if not reason.strip():
            raise WorldError('A reason is required to change boss settings.')
        if hp_override is not None and not 150 <= hp_override <= 100000:
            raise WorldError('Boss HP must be 150–100,000, or unset for automatic scaling.')
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            season = CombatEngine._season(con, season_key)
            if season.started_at is not None:
                raise WorldError('Boss configuration is locked once the event has started.')
            previous = con.execute('SELECT boss_enabled,boss_hp_override FROM world_settings '
                                   'WHERE season_key=?', (season_key,)).fetchone()
            before = dict(previous) if previous else {'boss_enabled': 1, 'boss_hp_override': None}
            con.execute('''INSERT INTO world_settings(season_key,boss_enabled,boss_hp_override)
                VALUES (?,?,?) ON CONFLICT(season_key) DO UPDATE SET
                boss_enabled=excluded.boss_enabled,boss_hp_override=excluded.boss_hp_override''',
                (season_key, int(enabled), hp_override))
            Store._audit(con, season_key, actor, 0, 'world:boss_settings', reason.strip(), now,
                         before, {'boss_enabled': int(enabled), 'boss_hp_override': hp_override})

    @staticmethod
    def _boss_settings(con, season_key):
        record = con.execute('SELECT boss_enabled,boss_hp_override FROM world_settings '
                             'WHERE season_key=?', (season_key,)).fetchone()
        return (bool(record['boss_enabled']), record['boss_hp_override']) if record else (True,None)

    @staticmethod
    def _sum(con, season, user, day, category):
        return int(con.execute("SELECT COALESCE(SUM(points),0) FROM score_ledger "
                               "WHERE season_key=? AND player_id=? AND day=? AND category=?",
                               (season, user, day, category)).fetchone()[0])

    @staticmethod
    def _score(con, season, user, city, day, category, points, source, now):
        if points <= 0:
            return 0
        con.execute("""INSERT OR IGNORE INTO score_ledger
            (season_key,day,player_id,city,category,points,source_key,created_at_utc)
            VALUES (?,?,?,?,?,?,?,?)""",
            (season, day, user, city, category, points, source, _timestamp(now)))
        return points

    @staticmethod
    def _world_day(con: sqlite3.Connection, key: str, day: int) -> sqlite3.Row:
        return con.execute("SELECT * FROM world_days WHERE season_key=? AND day=?",
                           (key, day)).fetchone()

    @staticmethod
    def _active_player_count(con: sqlite3.Connection, key: str, day: int, at: datetime,
                             city: str | None = None) -> int:
        if day == 1:
            query = ("SELECT COUNT(*) FROM players WHERE season_key=? "
                     "AND review_state NOT IN ('disqualified','flagged') "
                     "AND joined_at_utc<=?")
            params: tuple = (key, _timestamp(at))
            if city is not None:
                query += " AND city=?"
                params += (city,)
        else:
            query = ("""SELECT COUNT(DISTINCT l.player_id) FROM score_ledger l
                     JOIN players p ON p.season_key=l.season_key
                        AND p.discord_user_id=l.player_id
                     WHERE l.season_key=? AND l.day=? AND l.points>0
                        AND p.review_state NOT IN ('disqualified','flagged')""")
            params = (key, day - 1)
            if city is not None:
                query += " AND p.city=?"
                params += (city,)
        return int(con.execute(query, params).fetchone()[0])

    @staticmethod
    def _registered_city_at(con, key: str, city: str, at: datetime) -> int:
        return int(con.execute("SELECT COUNT(*) FROM players WHERE season_key=? "
                               "AND city=? AND review_state NOT IN ('disqualified','flagged') "
                               "AND joined_at_utc<=?",
                               (key, city, _timestamp(at))).fetchone()[0])

    def _sync(self, con: sqlite3.Connection, season_key: str, state: Season,
              now: datetime) -> tuple[int, list[int], list[int]]:
        """Initialize each elapsed day once; lock past daily city scores once.

        Scheduler calls this every minute, while write commands also call it
        transactionally, so a restart does not cause duplicate spawns/rewards.
        """
        if state.started_at is None:
            return 0, [], []
        effective = _game_now(state, now)
        elapsed = max(0.0, (effective - state.started_at).total_seconds())
        if state.phase(now) in ("closed", "finalized"):
            active_day, completed = 7, 7
        else:
            active_day = min(7, 1 + int(elapsed // 86400))
            completed = active_day - 1
        created, locked = [], []
        for day in range(1, active_day + 1):
            if self._world_day(con, season_key, day) is None:
                start = state.started_at + timedelta(days=day - 1)
                # Daily boss size is prior-day *active* player count; Day 1
                # uses those registered when the host started the season.
                boss_players = self._active_player_count(con, season_key, day,
                                                         state.started_at, None)
                enabled, override = self._boss_settings(con, season_key)
                boss_hp = override if override is not None else max(150, 28 * boss_players)
                con.execute("""INSERT INTO world_days
                    (season_key,day,effective_start_utc,theme,boss_initial_hp,boss_hp,created_at_utc)
                    VALUES (?,?,?,?,?,?,?)""",
                    (season_key, day, _timestamp(start), THEMES[day - 1],
                     boss_hp, boss_hp if enabled else 0, _timestamp(now)))
                for city in CITIES:
                    # Day-one count is frozen at start; later days freeze the
                    # eligible registered population at the first rollover tick.
                    cutoff = state.started_at if day == 1 else now
                    registered = self._registered_city_at(con, season_key, city, cutoff)
                    hp = 24 * max(3, min(10, registered))
                    con.execute("""INSERT INTO world_sieges
                        (season_key,day,city,initial_hp,hp) VALUES (?,?,?,?,?)""",
                        (season_key, day, city, hp, hp))
                created.append(day)
            if day <= completed:
                for city in CITIES:
                    exists = con.execute("SELECT 1 FROM city_day_snapshots WHERE "
                                         "season_key=? AND day=? AND city=?",
                                         (season_key, day, city)).fetchone()
                    if exists is None:
                        result = self._city_day(con, season_key, day, city)
                        con.execute("""INSERT INTO city_day_snapshots
                            (season_key,day,city,score_x100,active_players,qualified,
                             siege_cleared,siege_damage,locked_at_utc)
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                            (season_key, day, city, *result, _timestamp(now)))
                        locked.append(day)
        return active_day, created, sorted(set(locked))

    def tick(self, season_key: str, now: datetime) -> tuple[int, list[int], list[int]]:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            state = CombatEngine._season(con, season_key)
            return self._sync(con, season_key, state, now)

    @staticmethod
    def _city_day(con, season: str, day: int, city: str) -> tuple[int, int, int, int, int]:
        # A Golden Snowball's *city* credit is capped at 10 although its
        # individual award remains intact. Other category points count normally.
        rows = con.execute("""SELECT p.discord_user_id,
                   SUM(CASE WHEN l.category='pvp' AND c.id IS NOT NULL
                            THEN MIN(l.points, COALESCE(c.city_credit,l.points))
                            ELSE l.points END) AS contribution
                 FROM score_ledger l
                 JOIN players p ON p.season_key=l.season_key
                     AND p.discord_user_id=l.player_id
                 LEFT JOIN combat_events c ON l.category='pvp'
                     AND l.source_key=('combat:' || c.interaction_id)
                     AND c.season_key=l.season_key AND c.attacker_id=l.player_id
                 WHERE l.season_key=? AND l.day=? AND p.city=?
                     AND p.review_state NOT IN ('disqualified','flagged') AND l.points>0
                 GROUP BY p.discord_user_id
                 ORDER BY contribution DESC,p.discord_user_id ASC""",
                 (season, day, city)).fetchall()
        active = len(rows)
        contributions = [min(300, max(0, int(r['contribution']))) for r in rows]
        siege = con.execute("SELECT initial_hp,hp,cleared_at_utc FROM world_sieges WHERE "
                            "season_key=? AND day=? AND city=?", (season, day, city)).fetchone()
        cleared = int(bool(siege and siege['cleared_at_utc']))
        progress = int(siege['initial_hp'] - siege['hp']) if siege else 0
        if active < 3:
            return 0, active, 0, cleared, progress
        score_x100 = (sum(sorted(contributions, reverse=True)[:5]) * 100 // 5)
        score_x100 += min(40, 4 * max(0, active - 5)) * 100
        score_x100 += cleared * 2500
        return score_x100, active, 1, cleared, progress

    def standings(self, season_key: str, now: datetime) -> list[CityStanding]:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            state = CombatEngine._season(con, season_key)
            day, _, _ = self._sync(con, season_key, state, now)
            score_by_day: dict[int, dict[str, tuple[int, int, int, int, int]]] = {}
            for d in range(1, day + 1):
                score_by_day[d] = {}
                for city in CITIES:
                    snap = con.execute("SELECT * FROM city_day_snapshots WHERE season_key=? "
                                       "AND day=? AND city=?", (season_key, d, city)).fetchone()
                    score_by_day[d][city] = (
                        (snap['score_x100'], snap['active_players'], snap['qualified'],
                         snap['siege_cleared'], snap['siege_damage']) if snap else
                        self._city_day(con, season_key, d, city)
                    )
            day_wins = {city: 0 for city in CITIES}
            for d, values in score_by_day.items():
                best = max((v[0] for v in values.values() if v[2]), default=0)
                if best > 0:
                    for city, stats in values.items():
                        if stats[2] and stats[0] == best:
                            day_wins[city] += 1
            results = []
            for city in CITIES:
                rows = [score_by_day[d][city] for d in score_by_day]
                today = rows[-1] if rows else (0, 0, 0, 0, 0)
                results.append(CityStanding(city, sum(r[0] for r in rows), today[1],
                                            sum(r[3] for r in rows), day_wins[city],
                                            sum(r[4] for r in rows), bool(today[2]),
                                            today[0], bool(day and not con.execute(
                                                "SELECT 1 FROM city_day_snapshots WHERE "
                                                "season_key=? AND day=? AND city=?",
                                                (season_key, day, city)).fetchone())))
            return sorted(results, key=lambda r: (-r.score_x100, -r.daily_wins,
                                                   -r.siege_damage, r.city))

    def status(self, season_key: str, user: int, now: datetime) -> WorldStatus:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            state = CombatEngine._season(con, season_key)
            player = CombatEngine._player(con, season_key, user)
            day, _, _ = self._sync(con, season_key, state, now)
            if not day:
                return WorldStatus(None, state.phase(now), None, 0, 0, 0, 0, 0, 0, 0, 0,
                                   player['city'], self._boss_settings(con, season_key)[0])
            boss = self._world_day(con, season_key, day)
            fort = con.execute("SELECT * FROM world_sieges WHERE season_key=? AND day=? "
                               "AND city=?", (season_key, day, player['city'])).fetchone()
            return WorldStatus(day, state.phase(now), boss['theme'], boss['boss_hp'],
                               boss['boss_initial_hp'], self._attempts(con, season_key, user, day, 'boss'),
                               self._sum(con, season_key, user, day, 'boss'),
                               fort['hp'], fort['initial_hp'],
                               self._attempts(con, season_key, user, day, 'siege'),
                               self._sum(con, season_key, user, day, 'siege'), player['city'],
                               self._boss_settings(con, season_key)[0])

    @staticmethod
    def _attempts(con, key, user, day, kind):
        return int(con.execute("SELECT COUNT(*) FROM pve_events WHERE season_key=? "
                               "AND attacker_id=? AND day=? AND kind=?",
                               (key, user, day, kind)).fetchone()[0])

    @staticmethod
    def _repeat(con, key, user, kind, interaction):
        row = con.execute("SELECT * FROM pve_events WHERE interaction_id=?", (interaction,)).fetchone()
        if row is None:
            return None
        if (row['season_key'], row['attacker_id'], row['kind']) != (key, user, kind):
            raise WorldError('This interaction ID belongs to a different attack.')
        return PveResult(interaction, kind, row['day'], row['city'], bool(row['hit']),
                         row['damage'], row['points_awarded'], row['theme_points'],
                         row['hp_after'], row['max_hp'], bool(row['echo']),
                         bool(row['final_blow']), True)

    def attack(self, season_key: str, user_id: int, kind: str, interaction_id: str,
               now: datetime) -> PveResult:
        if kind not in ('boss', 'siege'):
            raise WorldError('Choose boss or siege.')
        if not isinstance(interaction_id, str) or not 1 <= len(interaction_id) <= 128:
            raise WorldError('A unique Discord interaction ID is required.')
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            repeated = self._repeat(con, season_key, user_id, kind, interaction_id)
            if repeated is not None:
                return repeated
            state = CombatEngine._season(con, season_key)
            if state.phase(now) != 'live':
                raise WorldError('Boss and siege attacks are available only while LIVE.')
            player = CombatEngine._player(con, season_key, user_id)
            if kind == 'boss' and not self._boss_settings(con, season_key)[0]:
                raise WorldError('The host has disabled the Snow Don for this season.')
            game_now = _game_now(state, now)
            day, _, _ = self._sync(con, season_key, state, now)
            combat = CombatEngine(self.store)
            resource = combat._resources(con, season_key, user_id, game_now)
            if _parse(resource['knockout_until']) is not None:
                raise WorldError('You must recover from your knockout before attacking NPCs.')
            last = _parse(resource['last_throw_at'])
            if last is not None and game_now - last < THROW_COOLDOWN:
                remaining = math.ceil((THROW_COOLDOWN - (game_now - last)).total_seconds())
                raise WorldError(f'Throw cooldown: {remaining} seconds remaining.')
            if resource['snowballs'] <= 0:
                raise WorldError('No snowballs available. They regenerate every 20 minutes.')
            attempts = self._attempts(con, season_key, user_id, day, kind)
            max_attempts = BOSS_LIMIT if kind == 'boss' else SIEGE_LIMIT
            if attempts >= max_attempts:
                raise WorldError(f'{kind.title()} attempt limit reached ({max_attempts} per day).')
            remaining_budget = max(0, (BOSS_CAP if kind == 'boss' else SIEGE_CAP)
                                   - self._sum(con, season_key, user_id, day, kind))
            if not remaining_budget:
                raise WorldError('Daily NPC score cap reached.')
            if kind == 'boss':
                npc = self._world_day(con, season_key, day)
                hp, max_hp, npc_key = npc['boss_hp'], npc['boss_initial_hp'], None
            else:
                npc = con.execute("SELECT * FROM world_sieges WHERE season_key=? AND day=? "
                                  "AND city=?", (season_key, day, player['city'])).fetchone()
                hp, max_hp, npc_key = npc['hp'], npc['initial_hp'], player['city']
            echo = hp == 0
            roll = self.rng.random()
            if not 0 <= roll < 1:
                raise WorldError('RNG returned an invalid accuracy roll.')
            hit = roll < PVE_HIT_CHANCE
            damage_roll = self.rng.random() if hit and kind == 'boss' else None
            if damage_roll is not None and not 0 <= damage_roll < 1:
                raise WorldError('RNG returned an invalid damage roll.')
            potential = (12 + int(damage_roll * 7)) if hit and kind == 'boss' else (14 if hit else 0)
            damage = (min(hp, potential) if not echo else potential) if hit else 0
            hp_after = max(0, hp - damage) if not echo else 0
            final_blow = bool(hit and not echo and hp > 0 and hp_after == 0)
            score = min(5 if kind == 'boss' else 8, remaining_budget) if hit else 0
            con.execute("UPDATE player_resources SET snowballs=snowballs-1, "
                        "snowball_regen_at=?, last_throw_at=?, "
                        "last_scored_action_at=CASE WHEN ? > 0 THEN ? ELSE last_scored_action_at END, "
                        "last_eligible_action_at=CASE WHEN ? > 0 THEN ? ELSE last_eligible_action_at END "
                        "WHERE season_key=? AND discord_user_id=?", (
                            _timestamp(game_now) if resource['snowballs'] == SNOWBALL_CAP
                            else resource['snowball_regen_at'],
                            _timestamp(game_now), score, _timestamp(game_now), score, _timestamp(game_now),
                            season_key, user_id,
                        ))
            if kind == 'boss' and not echo:
                con.execute('UPDATE world_days SET boss_hp=?, boss_defeated_at=CASE WHEN ? THEN ? '
                            'ELSE boss_defeated_at END WHERE season_key=? AND day=?',
                            (hp_after, int(final_blow), _timestamp(game_now), season_key, day))
            if kind == 'siege' and not echo:
                con.execute('UPDATE world_sieges SET hp=?,cleared_at_utc=CASE WHEN ? THEN ? '
                            'ELSE cleared_at_utc END WHERE season_key=? AND day=? AND city=?',
                            (hp_after, int(final_blow), _timestamp(game_now), season_key, day, player['city']))
            if score:
                self._score(con, season_key, user_id, player['city'], day, kind,
                            score, f'{kind}:hit:{interaction_id}', now)
            # Only the first genuine boss defeat awards +10 to the final hitter
            # and +10 once to every earlier successful contributor. Echoes
            # never grant these shared bonuses, preserving late time-zone fairness.
            if kind == 'boss' and final_blow:
                final_extra = min(10, max(0, BOSS_CAP - self._sum(con, season_key, user_id, day, 'boss')))
                if final_extra:
                    self._score(con, season_key, user_id, player['city'], day, 'boss',
                                final_extra, f'boss:final:{day}', now)
                    score += final_extra
                participants = con.execute("""SELECT DISTINCT attacker_id FROM pve_events
                        WHERE season_key=? AND day=? AND kind='boss' AND echo=0 AND hit=1
                        UNION SELECT ?""", (season_key, day, user_id)).fetchall()
                for person in participants:
                    aid = int(person[0])
                    prow = con.execute('SELECT city FROM players WHERE season_key=? AND discord_user_id=?',
                                      (season_key, aid)).fetchone()
                    if not prow:
                        continue
                    extra = min(10, max(0, BOSS_CAP - self._sum(con, season_key, aid, day, 'boss')))
                    if extra:
                        self._score(con, season_key, aid, prow['city'], day, 'boss',
                                    extra, f'boss:clear:{day}', now)
                        if aid == user_id:
                            score += extra
                    # A public clear is also a scored action for contributors
                    con.execute('UPDATE player_resources SET last_scored_action_at=?, '
                                'last_eligible_action_at=? WHERE season_key=? AND discord_user_id=?',
                                (_timestamp(game_now), _timestamp(game_now), season_key, aid))
            theme_points = 0
            if day == 5 and kind == 'boss':
                if not con.execute("SELECT 1 FROM score_ledger WHERE season_key=? AND day=5 "
                                   "AND player_id=? AND category='theme' AND source_key='theme:d5:boss'",
                                   (season_key, user_id)).fetchone():
                    theme_points = self._score(con, season_key, user_id, player['city'], day,
                                               'theme', 10, 'theme:d5:boss', now)
            elif day == 6:
                # Day-six challenge: two legal NPC throws of any kind; once per person.
                attempts_today = int(con.execute("SELECT COUNT(*) FROM pve_events "
                                                 "WHERE season_key=? AND day=6 AND attacker_id=?",
                                                 (season_key, user_id)).fetchone()[0])
                if attempts_today + 1 >= 2 and not con.execute(
                    "SELECT 1 FROM score_ledger WHERE season_key=? AND day=6 AND "
                    "player_id=? AND category='theme' AND source_key='theme:d6:two_npc'",
                    (season_key, user_id)).fetchone():
                    theme_points = self._score(con, season_key, user_id, player['city'], day,
                                               'theme', 20, 'theme:d6:two_npc', now)
            if theme_points and not score:
                con.execute('UPDATE player_resources SET last_scored_action_at=?, '
                            'last_eligible_action_at=? WHERE season_key=? AND discord_user_id=?',
                            (_timestamp(game_now), _timestamp(game_now), season_key, user_id))
            con.execute("""INSERT INTO pve_events (interaction_id,season_key,day,kind,
                attacker_id,city,happened_at_utc,effective_at_utc,hit_roll,damage_roll,
                hit,damage,echo,final_blow,points_awarded,theme_points,hp_after,max_hp)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (interaction_id, season_key, day, kind, user_id, player['city'], _timestamp(now),
                 _timestamp(game_now), roll, damage_roll, int(hit), damage, int(echo),
                 int(final_blow), score, theme_points, hp_after, max_hp))
            return PveResult(interaction_id, kind, day, player['city'], hit, damage, score,
                             theme_points, hp_after, max_hp, echo, final_blow)
