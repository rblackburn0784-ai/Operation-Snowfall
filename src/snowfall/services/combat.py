"""v0.1.2 PvP engine. One IMMEDIATE SQLite transaction per combat action.

All gameplay clocks use effective (pause-adjusted) UTC. Physical timestamps
are retained for auditing. Injected RNG is reserved for deterministic tests;
production uses the operating system's cryptographically secure RNG.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import secrets
import sqlite3
from typing import Protocol

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, Season, _parse, _timestamp

SNOWBALL_CAP = 12
WARMTH_CAP = 100
SNOWFLAKE_CAP = 100
REGEN_SECONDS = 1200
THROW_COOLDOWN = timedelta(seconds=30)
KO_DURATION = timedelta(minutes=30)
SHIELD_DURATION = timedelta(minutes=15)
INCOMING_WINDOW = timedelta(minutes=30)
INACTIVITY_WINDOW = timedelta(hours=36)
DAILY_PVP_CAP = 300
ATTACKS = {"quick": (0.75, 8, 8), "standard": (0.60, 14, 12), "power": (0.40, 22, 18)}


class CombatError(ValueError):
    """A rejected request; no snowballs or points have been spent."""


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class ResourceView:
    snowballs: int
    warmth: int
    snowflakes: int
    armour_hp: int
    knockout_until: datetime | None
    shield_until: datetime | None
    last_throw_at: datetime | None
    today_pvp: int
    day: int | None
    next_snowball_at: datetime | None
    next_warmth_at: datetime | None


@dataclass(frozen=True)
class TargetView:
    discord_user_id: int
    mr_username: str
    city: str
    warmth: int
    hits_remaining: int


@dataclass(frozen=True)
class CombatResult:
    interaction_id: str
    day: int
    attacker_id: int
    target_id: int
    target_city: str
    style: str
    hit: bool
    critical: bool
    armour_damage: int
    warmth_damage: int
    knocked_out: bool
    points_awarded: int
    defense_points: int
    bonus_city: int
    bonus_ko: int
    hit_roll: float
    crit_roll: float | None
    repeated: bool = False


def _game_now(season: Season, now: datetime) -> datetime:
    value = season.effective_now(now)
    if season.started_at is not None:
        value = max(season.started_at, min(value, season.started_at + timedelta(days=7)))
    return value


def _row_to_result(row: sqlite3.Row, *, repeated: bool = False) -> CombatResult:
    return CombatResult(
        row["interaction_id"], row["day"], row["attacker_id"], row["target_id"],
        row["target_city"], row["style"], bool(row["hit"]), bool(row["critical"]),
        row["armour_damage"], row["warmth_damage"], bool(row["knocked_out"]),
        row["points_awarded"], row["defense_points"], row["bonus_city"],
        row["bonus_ko"], row["hit_roll"], row["crit_roll"], repeated,
    )


class CombatEngine:
    def __init__(self, store: Store, rng: RandomSource | None = None):
        self.store = store
        self.rng = rng if rng is not None else secrets.SystemRandom()

    @staticmethod
    def _season(con: sqlite3.Connection, key: str) -> Season:
        row = con.execute("SELECT * FROM season_state WHERE season_key=?", (key,)).fetchone()
        if row is None:
            raise CombatError("Season is not configured.")
        return Store._make_season(row)

    @staticmethod
    def _player(con: sqlite3.Connection, season: str, user_id: int):
        row = con.execute(
            "SELECT * FROM players WHERE season_key=? AND discord_user_id=?",
            (season, user_id),
        ).fetchone()
        if row is None:
            raise CombatError("Player is not registered. Use /snow join first.")
        if row["review_state"] == "disqualified":
            raise CombatError("This player is disqualified from the event.")
        return row

    @staticmethod
    def _need_live(season: Season, now: datetime) -> None:
        if season.phase(now) != "live":
            raise CombatError("Snowball battles are available only while the event is LIVE.")

    @staticmethod
    def _score(con: sqlite3.Connection, season: str, player_id: int, day: int) -> int:
        return int(con.execute(
            "SELECT COALESCE(SUM(points),0) FROM score_ledger "
            "WHERE season_key=? AND player_id=? AND day=? AND category IN ('pvp','defense')",
            (season, player_id, day),
        ).fetchone()[0])

    @staticmethod
    def _regen_amount(value: int, cap: int, step: int, last: datetime, now: datetime):
        # Never bank extra ticks when capped (even after a lengthy offline period).
        if value >= cap:
            return cap, now
        ticks = max(0, math.floor((now - last).total_seconds() / REGEN_SECONDS))
        if not ticks:
            return value, last
        value = min(cap, value + step * ticks)
        if value == cap:
            return value, now
        return value, last + timedelta(seconds=ticks * REGEN_SECONDS)

    def _resources(self, con: sqlite3.Connection, season: str, user_id: int,
                   game_now: datetime) -> sqlite3.Row:
        con.execute(
            """INSERT OR IGNORE INTO player_resources
            (season_key, discord_user_id, snowball_regen_at, warmth_regen_at)
            VALUES (?,?,?,?)""",
            (season, user_id, _timestamp(game_now), _timestamp(game_now)),
        )
        row = con.execute(
            "SELECT * FROM player_resources WHERE season_key=? AND discord_user_id=?",
            (season, user_id),
        ).fetchone()
        ko_end = _parse(row["knockout_until"])
        warmth = row["warmth"]
        warmth_at = _parse(row["warmth_regen_at"])
        if ko_end is not None and game_now >= ko_end:
            warmth = max(50, warmth)
            warmth_at = max(warmth_at, ko_end)
        # KO suspends warmth regeneration until the 30-minute recovery completes.
        if ko_end is not None and game_now < ko_end:
            warmth_at = game_now
        else:
            warmth, warmth_at = self._regen_amount(
                warmth, WARMTH_CAP, 5, warmth_at, game_now,
            )
        snowballs, snowball_at = self._regen_amount(
            row["snowballs"], SNOWBALL_CAP, 1, _parse(row["snowball_regen_at"]), game_now,
        )
        armour_until = _parse(row["armour_expires_at"])
        armour_hp = row["armour_hp"]
        if armour_until is not None and armour_until <= game_now:
            armour_hp, armour_until = 0, None
        con.execute("""UPDATE player_resources SET snowballs=?, snowball_regen_at=?,
            warmth=?, warmth_regen_at=?, knockout_until=?,
            armour_hp=?, armour_expires_at=?
            WHERE season_key=? AND discord_user_id=?""", (
            snowballs, _timestamp(snowball_at), warmth, _timestamp(warmth_at),
            _timestamp(ko_end) if ko_end is not None and game_now < ko_end else None,
            armour_hp, _timestamp(armour_until) if armour_until else None,
            season, user_id,
        ))
        return con.execute(
            "SELECT * FROM player_resources WHERE season_key=? AND discord_user_id=?",
            (season, user_id),
        ).fetchone()

    def snapshot(self, season_key: str, user_id: int, now: datetime) -> ResourceView:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            season = self._season(con, season_key)
            self._player(con, season_key, user_id)
            if season.started_at is None:
                return ResourceView(8, 100, 0, 0, None, None, None, 0, None, None, None)
            game_now = _game_now(season, now)
            row = self._resources(con, season_key, user_id, game_now)
            day = season.day(now)
            score = self._score(con, season_key, user_id, day) if day else 0
            ball_at = _parse(row["snowball_regen_at"])
            warm_at = _parse(row["warmth_regen_at"])
            ko = _parse(row["knockout_until"])
            return ResourceView(
                row["snowballs"], row["warmth"], row["snowflakes"], row["armour_hp"],
                ko, _parse(row["shield_until"]), _parse(row["last_throw_at"]),
                score, day,
                ball_at + timedelta(seconds=REGEN_SECONDS) if row["snowballs"] < 12 else None,
                warm_at + timedelta(seconds=REGEN_SECONDS)
                if row["warmth"] < 100 and ko is None else None,
            )

    def ready(self, season_key: str, user_id: int, now: datetime) -> datetime:
        """Explicit temporary target opt-in for the combat-only build.

        Until bosses/quests exist, players need a way to become target-eligible
        without requiring a previous PvP score. Does not award points or ammo.
        """
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            season = self._season(con, season_key)
            self._need_live(season, now)
            self._player(con, season_key, user_id)
            game_now = _game_now(season, now)
            row = self._resources(con, season_key, user_id, game_now)
            if (ko := _parse(row["knockout_until"])) is not None and game_now < ko:
                raise CombatError("You cannot enter the arena during KO recovery.")
            con.execute("UPDATE player_resources SET last_eligible_action_at=? "
                        "WHERE season_key=? AND discord_user_id=?",
                        (_timestamp(game_now), season_key, user_id))
            return game_now + INACTIVITY_WINDOW

    def targets(self, season_key: str, attacker_id: int, now: datetime,
                limit: int = 25) -> list[TargetView]:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            season = self._season(con, season_key)
            self._need_live(season, now)
            attacker = self._player(con, season_key, attacker_id)
            game_now = _game_now(season, now)
            attacker_res = self._resources(con, season_key, attacker_id, game_now)
            if _parse(attacker_res["knockout_until"]) is not None:
                return []
            day = season.day(now)
            rows = con.execute("""SELECT p.* FROM players p
                JOIN player_resources r ON r.season_key=p.season_key
                 AND r.discord_user_id=p.discord_user_id
                WHERE p.season_key=? AND p.discord_user_id!=? AND p.city!=?
                 AND p.review_state!='disqualified' AND r.last_eligible_action_at IS NOT NULL
                ORDER BY r.last_eligible_action_at DESC, p.id ASC""",
                (season_key, attacker_id, attacker["city"]),
            ).fetchall()
            found = []
            for p in rows:
                r = self._resources(con, season_key, p["discord_user_id"], game_now)
                active = _parse(r["last_eligible_action_at"])
                if active is None or game_now - active > INACTIVITY_WINDOW:
                    continue
                if (_parse(r["knockout_until"]) or datetime.min.replace(tzinfo=timezone.utc)) > game_now:
                    continue
                if (_parse(r["shield_until"]) or datetime.min.replace(tzinfo=timezone.utc)) > game_now:
                    continue
                hits = con.execute("""SELECT COUNT(*) FROM combat_events
                    WHERE season_key=? AND day=? AND attacker_id=? AND target_id=?
                    AND hit=1 AND points_awarded>0""",
                    (season_key, day, attacker_id, p["discord_user_id"]),
                ).fetchone()[0]
                if hits >= 2:
                    continue
                found.append(TargetView(p["discord_user_id"], p["mr_username"], p["city"],
                                        r["warmth"], 2 - hits))
                if len(found) >= max(1, min(25, limit)):
                    break
            return found

    def throw(self, season_key: str, attacker_id: int, target_id: int, style: str,
              interaction_id: str, now: datetime) -> CombatResult:
        now = as_utc(now)
        if not interaction_id or len(interaction_id) > 128:
            raise CombatError("A valid unique Discord interaction ID is required.")
        if style not in ATTACKS:
            raise CombatError("Choose quick, standard or power.")
        if attacker_id == target_id:
            raise CombatError("You cannot throw a snowball at yourself.")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT * FROM combat_events WHERE interaction_id=?",
                                   (interaction_id,)).fetchone()
            if existing is not None:
                if (existing["season_key"], existing["attacker_id"], existing["target_id"],
                    existing["style"]) != (season_key, attacker_id, target_id, style):
                    raise CombatError("Interaction ID has already been used for a different attack.")
                return _row_to_result(existing, repeated=True)
            season = self._season(con, season_key)
            self._need_live(season, now)
            attacker = self._player(con, season_key, attacker_id)
            target = self._player(con, season_key, target_id)
            if attacker["city"] == target["city"]:
                raise CombatError("Friendly fire disabled: choose another city's player.")
            game_now = _game_now(season, now)
            day = season.day(now)
            a = self._resources(con, season_key, attacker_id, game_now)
            t = self._resources(con, season_key, target_id, game_now)
            if _parse(a["knockout_until"]) is not None:
                raise CombatError("You're recovering from a knockout. Return when warm again.")
            if _parse(t["knockout_until"]) is not None:
                raise CombatError("Your target is knocked out and temporarily protected.")
            protected = _parse(t["shield_until"])
            if protected is not None and game_now < protected:
                raise CombatError("This target has a temporary anti-camping shield.")
            active = _parse(t["last_eligible_action_at"])
            if active is None or game_now - active > INACTIVITY_WINDOW:
                raise CombatError("Target is inactive; they must /snow ready before being targeted.")
            last = _parse(a["last_throw_at"])
            if last is not None and game_now - last < THROW_COOLDOWN:
                remaining = math.ceil((THROW_COOLDOWN - (game_now - last)).total_seconds())
                raise CombatError(f"Throw cooldown: {remaining} seconds remaining.")
            if a["snowballs"] < 1:
                raise CombatError("Out of snowballs. You regenerate one every 20 minutes.")
            before = self._score(con, season_key, attacker_id, day)
            if before >= DAILY_PVP_CAP:
                raise CombatError("Daily PvP score cap reached (300). Try again next game day.")
            successful_pair_hits = con.execute("""SELECT COUNT(*) FROM combat_events
                WHERE season_key=? AND day=? AND attacker_id=? AND target_id=?
                  AND hit=1 AND points_awarded>0""",
                (season_key, day, attacker_id, target_id),
            ).fetchone()[0]
            if successful_pair_hits >= 2:
                raise CombatError("Two scoring hits already landed on this target today.")
            # RNG calls run inside the locked transaction so parallel attempts
            # cannot both consume the final snowball or score against stale state.
            chance, damage, base_points = ATTACKS[style]
            hit_roll = self.rng.random()
            if not 0 <= hit_roll < 1:
                raise CombatError("RNG provider supplied a value outside [0, 1).")
            hit = hit_roll < chance
            crit_roll = self.rng.random() if hit else None
            if crit_roll is not None and not 0 <= crit_roll < 1:
                raise CombatError("RNG provider supplied a value outside [0, 1).")
            critical = bool(hit and crit_roll < 0.10)
            absorb = min(t["armour_hp"], damage + (4 if critical else 0)) if hit else 0
            warmth_damage = max(0, damage + (4 if critical else 0) - absorb) if hit else 0
            new_warmth = max(0, t["warmth"] - warmth_damage)
            knocked_out = bool(hit and t["warmth"] > 0 and new_warmth == 0)
            bonus_city = 0
            bonus_ko = 0
            awarded = 0
            defense_points = 0
            shield_until = _parse(t["shield_until"])
            shield_trigger_at = _parse(t["shield_trigger_at"])
            if hit:
                prior_city = con.execute("""SELECT 1 FROM combat_events
                    WHERE season_key=? AND day=? AND attacker_id=? AND target_city=?
                    AND hit=1 AND points_awarded>0 LIMIT 1""",
                    (season_key, day, attacker_id, target["city"]),
                ).fetchone()
                if prior_city is None:
                    bonus_city = 5
                prior_ko = con.execute("""SELECT COUNT(*) FROM combat_events
                    WHERE season_key=? AND day=? AND attacker_id=? AND bonus_ko>0""",
                    (season_key, day, attacker_id),
                ).fetchone()[0]
                if knocked_out and prior_ko < 3:
                    bonus_ko = 10
                raw_points = base_points + (3 if critical else 0) + bonus_city + bonus_ko
                awarded = min(raw_points, DAILY_PVP_CAP - before)
                # Under the daily cap truncation, prioritize the base score,
                # then crit, city and KO bonuses for accurate breakdown.
                remaining = awarded
                remaining -= min(base_points, remaining)
                remaining -= min(3 if critical else 0, remaining)
                city_used = min(bonus_city, remaining)
                remaining -= city_used
                ko_used = min(bonus_ko, remaining)
                bonus_city, bonus_ko = city_used, ko_used
                if absorb > 0:
                    defense_points = min(2, DAILY_PVP_CAP - self._score(con, season_key, target_id, day))
                # Third scored hit in 30 effective minutes grants a new shield.
                window_start = game_now - INCOMING_WINDOW
                if shield_trigger_at is not None:
                    window_start = max(window_start, shield_trigger_at)
                incoming = con.execute("""SELECT COUNT(*) FROM combat_events
                    WHERE season_key=? AND target_id=? AND hit=1 AND points_awarded>0
                      AND effective_at_utc>?""",
                    (season_key, target_id, _timestamp(window_start)),
                ).fetchone()[0]
                if incoming + 1 >= 3:
                    shield_until = game_now + SHIELD_DURATION
                    shield_trigger_at = game_now
            ko_until = game_now + KO_DURATION if knocked_out else _parse(t["knockout_until"])
            con.execute("""UPDATE player_resources SET snowballs=snowballs-1,
                snowball_regen_at=?, last_throw_at=?, last_eligible_action_at=?
                WHERE season_key=? AND discord_user_id=?""", (
                _timestamp(game_now) if a["snowballs"] == SNOWBALL_CAP else a["snowball_regen_at"],
                _timestamp(game_now), _timestamp(game_now) if awarded else a["last_eligible_action_at"],
                season_key, attacker_id,
            ))
            if hit:
                con.execute("""UPDATE player_resources SET warmth=?, warmth_regen_at=?,
                    armour_hp=?, armour_expires_at=?, knockout_until=?,
                    shield_until=?, shield_trigger_at=?,
                    snowflakes=MIN(100,snowflakes+?), last_scored_action_at=?,
                    last_eligible_action_at=?
                    WHERE season_key=? AND discord_user_id=?""", (
                    new_warmth, _timestamp(game_now) if t["warmth"] == 100 or knocked_out else t["warmth_regen_at"],
                    t["armour_hp"] - absorb,
                    t["armour_expires_at"] if t["armour_hp"] > absorb else None,
                    _timestamp(ko_until) if ko_until else None,
                    _timestamp(shield_until) if shield_until else None,
                    _timestamp(shield_trigger_at) if shield_trigger_at else None,
                    0, _timestamp(game_now) if defense_points else t["last_scored_action_at"],
                    _timestamp(game_now) if defense_points else t["last_eligible_action_at"],
                    season_key, target_id,
                ))
                con.execute("UPDATE player_resources SET snowflakes=MIN(100,snowflakes+1), "
                            "last_scored_action_at=? WHERE season_key=? AND discord_user_id=?",
                            (_timestamp(game_now), season_key, attacker_id))
            con.execute("""INSERT INTO combat_events (interaction_id,season_key,day,
                attacker_id,target_id,target_city,style,happened_at_utc,effective_at_utc,
                hit,critical,hit_roll,crit_roll,armour_damage,warmth_damage,knocked_out,
                points_awarded,bonus_city,bonus_ko,defense_points)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                interaction_id, season_key, day, attacker_id, target_id, target["city"],
                style, _timestamp(now), _timestamp(game_now), int(hit), int(critical),
                hit_roll, crit_roll, absorb, warmth_damage, int(knocked_out),
                awarded, bonus_city, bonus_ko, defense_points,
            ))
            if awarded:
                con.execute("""INSERT INTO score_ledger
                    (season_key,day,player_id,city,category,points,source_key,created_at_utc)
                    VALUES(?,?,?,?,?,?,?,?)""", (
                    season_key, day, attacker_id, attacker["city"], "pvp",
                    awarded, f"combat:{interaction_id}", _timestamp(now),
                ))
            if defense_points:
                con.execute("""INSERT INTO score_ledger
                    (season_key,day,player_id,city,category,points,source_key,created_at_utc)
                    VALUES(?,?,?,?,?,?,?,?)""", (
                    season_key, day, target_id, target["city"], "defense",
                    defense_points, f"combat:{interaction_id}", _timestamp(now),
                ))
            row = con.execute("SELECT * FROM combat_events WHERE interaction_id=?",
                              (interaction_id,)).fetchone()
            return _row_to_result(row)

    def leaderboard(self, season_key: str, limit: int = 10) -> list[tuple[str, str, int, int]]:
        """Aggregate immutable scores, excluding disqualified players."""
        with self.store.connect() as con:
            rows = con.execute("""SELECT p.mr_username, p.city, p.discord_user_id,
                COALESCE(SUM(l.points),0) AS score,
                (SELECT COUNT(DISTINCT c.target_id) FROM combat_events c
                 WHERE c.season_key=p.season_key AND c.attacker_id=p.discord_user_id
                   AND c.hit=1 AND c.points_awarded>0) AS unique_rivals,
                MAX(l.created_at_utc) AS score_reached_at
                FROM players p LEFT JOIN score_ledger l ON l.season_key=p.season_key
                AND l.player_id=p.discord_user_id
                WHERE p.season_key=? AND p.review_state!='disqualified'
                GROUP BY p.season_key,p.discord_user_id
                ORDER BY score DESC, unique_rivals DESC, score_reached_at ASC,
                         p.mr_username_norm ASC LIMIT ?""",
                (season_key, max(1, min(100, limit))),
            ).fetchall()
            return [(r["mr_username"], r["city"], r["discord_user_id"], r["score"]) for r in rows]

    def ledger_total(self, season_key: str, user_id: int, day: int | None = None) -> int:
        with self.store.connect() as con:
            if day is None:
                return int(con.execute("SELECT COALESCE(SUM(points),0) FROM score_ledger "
                                       "WHERE season_key=? AND player_id=?",
                                       (season_key, user_id)).fetchone()[0])
            return self._score(con, season_key, user_id, day)
