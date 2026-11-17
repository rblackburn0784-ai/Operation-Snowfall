"""Transactional SQLite persistence for Operation Snowfall v0.1.6.

All wall-clock values are UTC ISO strings. Existing v0.1.0 player records
remain intact when the version-2 schema is migrated.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import unicodedata

from snowfall.core.clock import as_utc

CITIES = ("Chicago", "New York", "Detroit", "Philadelphia", "Las Vegas", "Los Angeles")
DB_VERSION = 8


class RegistrationError(ValueError):
    pass


class LifecycleError(ValueError):
    pass


@dataclass(frozen=True)
class Player:
    discord_user_id: int
    mr_username: str
    city: str
    joined_at_utc: str
    review_state: str


@dataclass(frozen=True)
class Season:
    season_key: str
    planned_start: datetime
    started_at: datetime | None
    paused_at: datetime | None
    paused_seconds: float
    finalized_at: datetime | None

    def registration_opens(self) -> datetime:
        return self.planned_start - timedelta(hours=168)

    def effective_now(self, now: datetime) -> datetime:
        now = as_utc(now)
        frozen = self.paused_at if self.paused_at else now
        return frozen - timedelta(seconds=self.paused_seconds)

    def phase(self, now: datetime) -> str:
        now = as_utc(now)
        if self.finalized_at is not None:
            return "finalized"
        if self.paused_at is not None:
            return "paused"
        if self.started_at is not None:
            if now < self.started_at:
                return "ready"  # never permit simulated or misordered actions pre-start
            if self.effective_now(now) >= self.started_at + timedelta(hours=168):
                return "closed"
            return "live"
        if now < self.registration_opens():
            return "not_open"
        if now < self.planned_start:
            return "registration"
        return "ready"  # scheduled start reached; host must start the game

    def day(self, now: datetime) -> int | None:
        if self.started_at is None or self.phase(now) not in ("live", "paused"):
            return None
        elapsed = self.effective_now(now) - self.started_at
        return min(7, max(1, elapsed.days + 1))

    def projected_end(self, now: datetime) -> datetime | None:
        """End if no additional pauses. On pause, end keeps extending with time."""
        if self.started_at is None:
            return None
        extra = timedelta(0)
        if self.paused_at is not None:
            extra = as_utc(now) - self.paused_at
        return self.started_at + timedelta(hours=168, seconds=self.paused_seconds) + extra


def normalize_mr_username(raw: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", raw).strip()
    if not 2 <= len(display) <= 32:
        raise RegistrationError("MR username must be between 2 and 32 characters")
    if any(unicodedata.category(c).startswith("C") for c in display):
        raise RegistrationError("MR username contains unsupported control characters")
    if any(c in display for c in ("@", "<", ">", "\\", "`", "~", "|")):
        raise RegistrationError("MR username contains unsupported Discord formatting")
    return display, display.casefold()


def _timestamp(value: datetime) -> str:
    return as_utc(value).isoformat()


def _parse(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw).astimezone(timezone.utc) if raw else None


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("BEGIN IMMEDIATE")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version > DB_VERSION:
                raise RuntimeError(f"Database version {version} is newer than this bot")
            if version < 1:
                con.execute("""CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    mr_username TEXT NOT NULL, mr_username_norm TEXT NOT NULL,
                    city TEXT NOT NULL, joined_at_utc TEXT NOT NULL,
                    review_state TEXT NOT NULL DEFAULT 'self_declared',
                    UNIQUE(season_key,discord_user_id), UNIQUE(season_key,mr_username_norm)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS admin_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_key TEXT NOT NULL, actor_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )""")
                con.execute("PRAGMA user_version=1")
            if version < 2:
                columns = {r[1] for r in con.execute("PRAGMA table_info(admin_audit)")}
                if "before_json" not in columns:
                    con.execute("ALTER TABLE admin_audit ADD COLUMN before_json TEXT")
                if "after_json" not in columns:
                    con.execute("ALTER TABLE admin_audit ADD COLUMN after_json TEXT")
                con.execute("""CREATE TABLE IF NOT EXISTS season_state (
                    season_key TEXT PRIMARY KEY, planned_start_utc TEXT NOT NULL,
                    started_at_utc TEXT, paused_at_utc TEXT,
                    paused_seconds INTEGER NOT NULL DEFAULT 0,
                    finalized_at_utc TEXT
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS published_messages (
                    season_key TEXT NOT NULL, message_kind TEXT NOT NULL,
                    channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
                    PRIMARY KEY (season_key,message_kind)
                )""")
                con.execute("PRAGMA user_version=2")
            if version < 3:
                con.execute("""CREATE TABLE IF NOT EXISTS player_resources (
                    season_key TEXT NOT NULL,
                    discord_user_id INTEGER NOT NULL,
                    snowballs INTEGER NOT NULL DEFAULT 8 CHECK(snowballs BETWEEN 0 AND 12),
                    snowball_regen_at TEXT NOT NULL,
                    warmth INTEGER NOT NULL DEFAULT 100 CHECK(warmth BETWEEN 0 AND 100),
                    warmth_regen_at TEXT NOT NULL,
                    snowflakes INTEGER NOT NULL DEFAULT 0 CHECK(snowflakes BETWEEN 0 AND 100),
                    armour_hp INTEGER NOT NULL DEFAULT 0 CHECK(armour_hp BETWEEN 0 AND 25),
                    armour_expires_at TEXT,
                    knockout_until TEXT,
                    shield_until TEXT,
                    shield_trigger_at TEXT,
                    last_throw_at TEXT,
                    last_eligible_action_at TEXT,
                    last_scored_action_at TEXT,
                    PRIMARY KEY (season_key, discord_user_id),
                    FOREIGN KEY (season_key, discord_user_id)
                       REFERENCES players(season_key, discord_user_id)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS combat_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id TEXT NOT NULL UNIQUE,
                    season_key TEXT NOT NULL,
                    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    attacker_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
                    target_city TEXT NOT NULL, style TEXT NOT NULL,
                    happened_at_utc TEXT NOT NULL, effective_at_utc TEXT NOT NULL,
                    hit INTEGER NOT NULL, critical INTEGER NOT NULL,
                    hit_roll REAL NOT NULL, crit_roll REAL,
                    armour_damage INTEGER NOT NULL, warmth_damage INTEGER NOT NULL,
                    knocked_out INTEGER NOT NULL, points_awarded INTEGER NOT NULL,
                    bonus_city INTEGER NOT NULL, bonus_ko INTEGER NOT NULL,
                    defense_points INTEGER NOT NULL,
                    CHECK(attacker_id != target_id)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS score_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_key TEXT NOT NULL,
                    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    player_id INTEGER NOT NULL, city TEXT NOT NULL,
                    category TEXT NOT NULL, points INTEGER NOT NULL,
                    source_key TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                    UNIQUE(season_key, source_key, category, player_id)
                )""")
                con.execute("CREATE INDEX IF NOT EXISTS idx_combat_pair_day ON "
                            "combat_events(season_key,day,attacker_id,target_id,hit)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_combat_target_window ON "
                            "combat_events(season_key,target_id,effective_at_utc)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_score_player_day ON "
                            "score_ledger(season_key,day,player_id)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_resources_active ON "
                            "player_resources(season_key,last_eligible_action_at)")
                # Corrections will use compensating INSERTs, never rewrite prior score rows.
                for table in ("combat_events", "score_ledger"):
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
                        BEFORE UPDATE ON {table} BEGIN
                        SELECT RAISE(ABORT, 'immutable combat history'); END""")
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
                        BEFORE DELETE ON {table} BEGIN
                        SELECT RAISE(ABORT, 'immutable combat history'); END""")
                con.execute("PRAGMA user_version=3")
            if version < 4:
                con.execute("""CREATE TABLE IF NOT EXISTS player_economy (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    guard_until TEXT, guard_last_started_at TEXT,
                    mittens_armed INTEGER NOT NULL DEFAULT 0 CHECK(mittens_armed IN (0,1)),
                    bomb_armed INTEGER NOT NULL DEFAULT 0 CHECK(bomb_armed IN (0,1)),
                    golden_awarded INTEGER NOT NULL DEFAULT 0 CHECK(golden_awarded BETWEEN 0 AND 1),
                    PRIMARY KEY(season_key,discord_user_id),
                    FOREIGN KEY(season_key,discord_user_id)
                        REFERENCES players(season_key,discord_user_id)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS player_inventory (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    item_key TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0
                        CHECK(quantity BETWEEN 0 AND 3),
                    PRIMARY KEY(season_key,discord_user_id,item_key),
                    FOREIGN KEY(season_key,discord_user_id)
                        REFERENCES players(season_key,discord_user_id)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS item_events (
                    interaction_id TEXT PRIMARY KEY, season_key TEXT NOT NULL,
                    discord_user_id INTEGER NOT NULL, day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    operation TEXT NOT NULL, item_key TEXT NOT NULL,
                    detail TEXT NOT NULL, happened_at_utc TEXT NOT NULL,
                    effective_at_utc TEXT NOT NULL
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS quest_claims (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    quest_key TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 20,
                    claimed_at_utc TEXT NOT NULL,
                    PRIMARY KEY(season_key,discord_user_id,day,quest_key)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS mystery_gifts (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    source TEXT NOT NULL CHECK(source IN ('daily','bonus')),
                    interaction_id TEXT NOT NULL UNIQUE,
                    reward TEXT NOT NULL, actual_reward TEXT NOT NULL,
                    roll REAL NOT NULL, amount INTEGER NOT NULL DEFAULT 0,
                    claimed_at_utc TEXT NOT NULL,
                    PRIMARY KEY(season_key,discord_user_id,day,source)
                )""")
                con.execute("CREATE INDEX IF NOT EXISTS idx_item_events_user_day ON "
                            "item_events(season_key,discord_user_id,day,operation,item_key)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_claims_user_day ON "
                            "quest_claims(season_key,discord_user_id,day)")
                for table in ("item_events", "quest_claims", "mystery_gifts"):
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
                        BEFORE UPDATE ON {table} BEGIN
                        SELECT RAISE(ABORT, 'immutable event history'); END""")
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
                        BEFORE DELETE ON {table} BEGIN
                        SELECT RAISE(ABORT, 'immutable event history'); END""")
                for column, definition in (
                    ("modifier_item", "TEXT"), ("guarded", "INTEGER NOT NULL DEFAULT 0"),
                    ("item_bonus_points", "INTEGER NOT NULL DEFAULT 0"),
                    ("city_credit", "INTEGER"),
                ):
                    cols = {r[1] for r in con.execute("PRAGMA table_info(combat_events)")}
                    if column not in cols:
                        con.execute(f"ALTER TABLE combat_events ADD COLUMN {column} {definition}")
                # Historical v3 combat rows intentionally retain NULL city_credit.
                # Do not UPDATE immutable combat history; future city aggregation
                # should use COALESCE(city_credit, points_awarded).
                con.execute("PRAGMA user_version=4")
            if version < 5:
                con.execute("""CREATE TABLE IF NOT EXISTS world_settings (
                    season_key TEXT PRIMARY KEY,
                    boss_enabled INTEGER NOT NULL DEFAULT 1 CHECK(boss_enabled IN (0,1)),
                    boss_hp_override INTEGER CHECK(boss_hp_override IS NULL OR boss_hp_override>=150)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS world_days (
                    season_key TEXT NOT NULL, day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    effective_start_utc TEXT NOT NULL, theme TEXT NOT NULL,
                    boss_initial_hp INTEGER NOT NULL CHECK(boss_initial_hp>=150),
                    boss_hp INTEGER NOT NULL CHECK(boss_hp>=0),
                    boss_defeated_at TEXT, created_at_utc TEXT NOT NULL,
                    PRIMARY KEY(season_key,day)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS world_sieges (
                    season_key TEXT NOT NULL, day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    city TEXT NOT NULL, initial_hp INTEGER NOT NULL CHECK(initial_hp>=72),
                    hp INTEGER NOT NULL CHECK(hp>=0), cleared_at_utc TEXT,
                    PRIMARY KEY(season_key,day,city)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS pve_events (
                    interaction_id TEXT PRIMARY KEY, season_key TEXT NOT NULL,
                    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    kind TEXT NOT NULL CHECK(kind IN ('boss','siege')),
                    attacker_id INTEGER NOT NULL, city TEXT NOT NULL,
                    happened_at_utc TEXT NOT NULL, effective_at_utc TEXT NOT NULL,
                    hit_roll REAL NOT NULL, damage_roll REAL,
                    hit INTEGER NOT NULL, damage INTEGER NOT NULL CHECK(damage>=0),
                    echo INTEGER NOT NULL, final_blow INTEGER NOT NULL,
                    points_awarded INTEGER NOT NULL CHECK(points_awarded>=0),
                    theme_points INTEGER NOT NULL DEFAULT 0 CHECK(theme_points>=0),
                    hp_after INTEGER NOT NULL CHECK(hp_after>=0), max_hp INTEGER NOT NULL
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS city_day_snapshots (
                    season_key TEXT NOT NULL, day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    city TEXT NOT NULL, score_x100 INTEGER NOT NULL,
                    active_players INTEGER NOT NULL, qualified INTEGER NOT NULL,
                    siege_cleared INTEGER NOT NULL, siege_damage INTEGER NOT NULL,
                    locked_at_utc TEXT NOT NULL,
                    PRIMARY KEY(season_key,day,city)
                )""")
                con.execute("CREATE INDEX IF NOT EXISTS idx_pve_player_day ON "
                            "pve_events(season_key,day,attacker_id,kind)")
                for table in ('pve_events','city_day_snapshots'):
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
                        BEFORE UPDATE ON {table} BEGIN
                        SELECT RAISE(ABORT,'immutable group history'); END""")
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
                        BEFORE DELETE ON {table} BEGIN
                        SELECT RAISE(ABORT,'immutable group history'); END""")
                con.execute("PRAGMA user_version=5")
            if version < 6:
                con.execute("""CREATE TABLE IF NOT EXISTS launch_approvals (
                    season_key TEXT PRIMARY KEY, host_id INTEGER NOT NULL,
                    approved_at_utc TEXT NOT NULL, planned_start_utc TEXT NOT NULL,
                    reason TEXT NOT NULL
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS prize_awards (
                    season_key TEXT NOT NULL, place INTEGER NOT NULL CHECK(place BETWEEN 1 AND 10),
                    discord_user_id INTEGER NOT NULL, mr_username TEXT NOT NULL,
                    city TEXT NOT NULL, points INTEGER NOT NULL CHECK(points>=0),
                    reward TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','paid')),
                    updated_at_utc TEXT,
                    PRIMARY KEY(season_key,place), UNIQUE(season_key,discord_user_id)
                )""")
                con.execute("""CREATE TRIGGER IF NOT EXISTS prize_awards_immutable_delete
                    BEFORE DELETE ON prize_awards BEGIN
                    SELECT RAISE(ABORT,'immutable prize history'); END""")
                con.execute("PRAGMA user_version=6")
            if version < 7:
                # Cosmetic selection only. Trophies themselves derive from the
                # immutable score/combat/PvE/gift ledgers, not editable counters.
                con.execute("""CREATE TABLE IF NOT EXISTS player_titles (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    title_key TEXT NOT NULL DEFAULT 'none', updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(season_key, discord_user_id),
                    FOREIGN KEY(season_key, discord_user_id)
                        REFERENCES players(season_key, discord_user_id)
                )""")
                con.execute("PRAGMA user_version=7")
            if version < 8:
                # v0.2.0 uses separate score-neutral season-scoped storage.
                con.execute("""CREATE TABLE IF NOT EXISTS cosmetic_unlocks (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    cosmetic_key TEXT NOT NULL, unlocked_at_utc TEXT NOT NULL,
                    PRIMARY KEY(season_key,discord_user_id,cosmetic_key),
                    FOREIGN KEY(season_key,discord_user_id)
                        REFERENCES players(season_key,discord_user_id)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS cosmetic_equipped (
                    season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
                    category TEXT NOT NULL, cosmetic_key TEXT NOT NULL,
                    PRIMARY KEY(season_key,discord_user_id,category),
                    FOREIGN KEY(season_key,discord_user_id)
                        REFERENCES players(season_key,discord_user_id)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS cosmetic_purchases (
                    interaction_id TEXT PRIMARY KEY, season_key TEXT NOT NULL,
                    discord_user_id INTEGER NOT NULL, day INTEGER NOT NULL,
                    cosmetic_key TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>=0),
                    detail TEXT NOT NULL, purchased_at_utc TEXT NOT NULL
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS encounter_events (
                    interaction_id TEXT PRIMARY KEY, season_key TEXT NOT NULL,
                    discord_user_id INTEGER NOT NULL, day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    souvenir TEXT NOT NULL, choice TEXT NOT NULL,
                    encountered_at_utc TEXT NOT NULL,
                    UNIQUE(season_key,discord_user_id,day)
                )""")
                con.execute("""CREATE TABLE IF NOT EXISTS arcade_events (
                    interaction_id TEXT PRIMARY KEY, season_key TEXT NOT NULL,
                    discord_user_id INTEGER NOT NULL, day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
                    mode TEXT NOT NULL, style TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK(score>=0),
                    equip TEXT, played_at_utc TEXT NOT NULL
                )""")
                con.execute("CREATE INDEX IF NOT EXISTS idx_arcade_mode_day ON "
                            "arcade_events(season_key,discord_user_id,day,mode)")
                for table in ("cosmetic_purchases", "encounter_events", "arcade_events", "cosmetic_unlocks"):
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
                        BEFORE UPDATE ON {table} BEGIN
                        SELECT RAISE(ABORT,'immutable winter event'); END""")
                    con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
                        BEFORE DELETE ON {table} BEGIN
                        SELECT RAISE(ABORT,'immutable winter event'); END""")
                con.execute("PRAGMA user_version=8")
        with self.connect() as con:
            result = con.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {result}")

    def schema_version(self) -> int:
        with self.connect() as con:
            return con.execute("PRAGMA user_version").fetchone()[0]

    @staticmethod
    def _make_season(row: sqlite3.Row) -> Season:
        return Season(row["season_key"], _parse(row["planned_start_utc"]),
                      _parse(row["started_at_utc"]), _parse(row["paused_at_utc"]),
                      row["paused_seconds"], _parse(row["finalized_at_utc"]))

    def ensure_season(self, key: str, planned_start: datetime) -> Season:
        if not key.strip():
            raise LifecycleError("Season key must not be empty")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT OR IGNORE INTO season_state(season_key,planned_start_utc) "
                        "VALUES(?,?)", (key, _timestamp(planned_start)))
            row = con.execute("SELECT * FROM season_state WHERE season_key=?", (key,)).fetchone()
            return self._make_season(row)

    def season(self, key: str) -> Season:
        with self.connect() as con:
            row = con.execute("SELECT * FROM season_state WHERE season_key=?", (key,)).fetchone()
        if row is None:
            raise LifecycleError("Season not set up; initialise it before using the bot")
        return self._make_season(row)

    @staticmethod
    def _audit(con, season, actor, subject, action, reason, when, before=None, after=None):
        con.execute("""INSERT INTO admin_audit
            (season_key,actor_id,subject_id,action,reason,created_at_utc,before_json,after_json)
            VALUES(?,?,?,?,?,?,?,?)""", (
            season, actor, subject, action, reason, _timestamp(when),
            json.dumps(before, sort_keys=True) if before is not None else None,
            json.dumps(after, sort_keys=True) if after is not None else None,
        ))

    def transition(self, key: str, actor_id: int, action: str, now: datetime,
                   reason: str, new_start: datetime | None = None) -> Season:
        now = as_utc(now)
        if not reason.strip():
            raise LifecycleError("A reason is required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            raw = con.execute("SELECT * FROM season_state WHERE season_key=?", (key,)).fetchone()
            if raw is None:
                raise LifecycleError("Season not configured")
            old = self._make_season(raw)
            state = old.phase(now)
            if action == "setup":
                if new_start is None or new_start <= now:
                    raise LifecycleError("Choose a future UTC start time")
                if state != "not_open" or as_utc(new_start) - timedelta(hours=168) <= now:
                    raise LifecycleError("Start time can only change before registration opens")
                con.execute("UPDATE season_state SET planned_start_utc=? WHERE season_key=?",
                            (_timestamp(new_start), key))
            elif action == "start":
                if state != "ready":
                    raise LifecycleError("Start is allowed only after the scheduled UTC kickoff")
                con.execute("UPDATE season_state SET started_at_utc=? WHERE season_key=?",
                            (_timestamp(now), key))
                # Pre-registered players begin regenerating from the actual start,
                # even if they first view their profile several hours later.
                con.execute("""INSERT OR IGNORE INTO player_resources
                    (season_key,discord_user_id,snowball_regen_at,warmth_regen_at)
                    SELECT season_key,discord_user_id,?,? FROM players
                    WHERE season_key=?""", (_timestamp(now), _timestamp(now), key))
            elif action == "pause":
                if state != "live":
                    raise LifecycleError("Only a live season can be paused")
                con.execute("UPDATE season_state SET paused_at_utc=? WHERE season_key=?",
                            (_timestamp(now), key))
            elif action == "resume":
                if state != "paused":
                    raise LifecycleError("Season is not paused")
                seconds = (now - old.paused_at).total_seconds()
                if seconds < 0:
                    raise LifecycleError("Resume time cannot precede pause time")
                # Seconds are stored as REAL in SQLite when fractional.
                con.execute("UPDATE season_state SET paused_at_utc=NULL, paused_seconds=? "
                            "WHERE season_key=?", (old.paused_seconds + seconds, key))
            elif action == "finalize":
                if state != "closed":
                    raise LifecycleError("Finalization requires all 168 effective hours to end")
                con.execute("UPDATE season_state SET finalized_at_utc=? WHERE season_key=?",
                            (_timestamp(now), key))
            else:
                raise LifecycleError("Unknown transition")
            updated = self._make_season(con.execute(
                "SELECT * FROM season_state WHERE season_key=?", (key,)).fetchone())
            self._audit(con, key, actor_id, 0, f"season:{action}", reason, now,
                        before={"phase": state, "planned_start": old.planned_start.isoformat()},
                        after={"phase": updated.phase(now),
                               "planned_start": updated.planned_start.isoformat()})
        return updated

    def register(self, season: str, user_id: int, mr_name: str, city: str, now: datetime) -> Player:
        if city not in CITIES:
            raise RegistrationError("Unknown city")
        if user_id <= 0:
            raise RegistrationError("Invalid Discord user")
        display, normalized = normalize_mr_username(mr_name)
        when = _timestamp(now)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing_season = con.execute("SELECT * FROM season_state WHERE season_key=?",
                                          (season,)).fetchone()
            if existing_season:
                state = self._make_season(existing_season).phase(now)
                if state not in ("registration", "ready", "live", "paused"):
                    raise RegistrationError("Registration is not open")
            previous = con.execute(
                "SELECT * FROM players WHERE season_key=? AND discord_user_id=?", (season, user_id)
            ).fetchone()
            if previous:
                if previous["mr_username_norm"] == normalized and previous["city"] == city:
                    return self._make_player(previous)
                raise RegistrationError("You already registered this season; contact staff for changes")
            try:
                con.execute("""INSERT INTO players(season_key,discord_user_id,mr_username,
                    mr_username_norm,city,joined_at_utc) VALUES(?,?,?,?,?,?)""",
                    (season, user_id, display, normalized, city, when))
            except sqlite3.IntegrityError as exc:
                raise RegistrationError("That MR username has already been claimed; contact staff if disputed") from exc
            if existing_season and state in ("live", "paused"):
                # Late joiners receive exactly the starter balance; no pre-join
                # regeneration. Paused registrations seed at frozen game time.
                effective_join = self._make_season(existing_season).effective_now(now)
                con.execute("""INSERT OR IGNORE INTO player_resources
                    (season_key,discord_user_id,snowball_regen_at,warmth_regen_at)
                    VALUES(?,?,?,?)""", (
                    season, user_id, _timestamp(effective_join), _timestamp(effective_join),
                ))
            return self._make_player(con.execute(
                "SELECT * FROM players WHERE season_key=? AND discord_user_id=?",
                (season, user_id)).fetchone())

    @staticmethod
    def _make_player(row: sqlite3.Row) -> Player:
        return Player(row["discord_user_id"], row["mr_username"], row["city"],
                      row["joined_at_utc"], row["review_state"])

    def get_player(self, season: str, user_id: int) -> Player | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM players WHERE season_key=? AND discord_user_id=?",
                              (season, user_id)).fetchone()
            return self._make_player(row) if row else None

    def registrations(self, season: str) -> list[Player]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM players WHERE season_key=? ORDER BY joined_at_utc,id",
                               (season,)).fetchall()
            return [self._make_player(r) for r in rows]

    def review(self, season: str, actor_id: int, subject_id: int, state: str,
               reason: str, now: datetime) -> None:
        if state not in ("flagged", "cleared", "disqualified"):
            raise ValueError("Unknown review state")
        if not reason.strip():
            raise ValueError("A reason is required for account review")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM players WHERE season_key=? AND discord_user_id=?",
                              (season, subject_id)).fetchone()
            if row is None:
                raise RegistrationError("Player is not registered")
            con.execute("UPDATE players SET review_state=? WHERE season_key=? AND discord_user_id=?",
                        (state, season, subject_id))
            self._audit(con, season, actor_id, subject_id, "identity_review:" + state,
                        reason.strip(), now, {"review_state": row["review_state"]},
                        {"review_state": state})

    def get_published(self, season: str, kind: str) -> tuple[int, int] | None:
        with self.connect() as con:
            row = con.execute("SELECT channel_id,message_id FROM published_messages "
                              "WHERE season_key=? AND message_kind=?", (season, kind)).fetchone()
            return (row["channel_id"], row["message_id"]) if row else None

    def record_published(self, season: str, actor: int, kind: str, channel: int,
                         message: int, now: datetime) -> None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            before = con.execute("SELECT channel_id,message_id FROM published_messages "
                                 "WHERE season_key=? AND message_kind=?", (season, kind)).fetchone()
            con.execute("""INSERT INTO published_messages(season_key,message_kind,channel_id,message_id)
                VALUES(?,?,?,?) ON CONFLICT(season_key,message_kind) DO UPDATE
                SET channel_id=excluded.channel_id,message_id=excluded.message_id""",
                (season, kind, channel, message))
            self._audit(con, season, actor, 0, "dashboard:publish", "Publish/update dashboard",
                        now, dict(before) if before else None,
                        {"channel_id": channel, "message_id": message})

    def audit_count(self, season: str) -> int:
        with self.connect() as con:
            return con.execute("SELECT COUNT(*) FROM admin_audit WHERE season_key=?",
                               (season,)).fetchone()[0]

    def audit_entries(self, season: str) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM admin_audit WHERE season_key=? ORDER BY id", (season,))]
