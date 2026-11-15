"""Transactional SQLite persistence for v0.1.1 foundation.

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
DB_VERSION = 2


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
