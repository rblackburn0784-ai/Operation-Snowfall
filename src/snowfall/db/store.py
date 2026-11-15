"""SQLite starter for registration, dispute review and admin audit.

This layer is intentionally small. Later combat must use BEGIN IMMEDIATE
transactions and interaction IDs in the ledger, not scattered UPDATEs.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import unicodedata


CITIES = ("Chicago", "New York", "Detroit", "Philadelphia", "Las Vegas", "Los Angeles")

class RegistrationError(ValueError):
    pass

@dataclass(frozen=True)
class Player:
    discord_user_id: int
    mr_username: str
    city: str
    joined_at_utc: str
    review_state: str


def normalize_mr_username(raw: str) -> tuple[str, str]:
    """Preserves display spelling, de-duplicates Unicode-equivalent spellings."""
    display = unicodedata.normalize("NFKC", raw).strip()
    if not (2 <= len(display) <= 32):
        raise RegistrationError("MR username must be between 2 and 32 characters")
    if any(unicodedata.category(c).startswith("C") for c in display):
        raise RegistrationError("MR username contains unsupported control characters")
    if "@" in display or "<" in display or ">" in display or chr(92) in display:
        raise RegistrationError("MR username contains unsafe Discord formatting")
    if display[0].isspace() or display[-1].isspace():
        raise RegistrationError("MR username cannot start or end with whitespace")
    return display, display.casefold()


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript('''
              CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_key TEXT NOT NULL,
                discord_user_id INTEGER NOT NULL,
                mr_username TEXT NOT NULL,
                mr_username_norm TEXT NOT NULL,
                city TEXT NOT NULL,
                joined_at_utc TEXT NOT NULL,
                review_state TEXT NOT NULL DEFAULT 'self_declared',
                UNIQUE (season_key, discord_user_id),
                UNIQUE (season_key, mr_username_norm)
              );
              CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_key TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
              );
            ''')

    def register(self, season: str, user_id: int, mr_name: str, city: str, now: datetime) -> Player:
        if city not in CITIES:
            raise RegistrationError("Unknown city")
        display, normalized = normalize_mr_username(mr_name)
        when = now.astimezone(timezone.utc).isoformat()
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute(
                "SELECT * FROM players WHERE season_key = ? AND discord_user_id = ?",
                (season, user_id),
            ).fetchone()
            if previous:
                if previous["mr_username_norm"] == normalized and previous["city"] == city:
                    return self._make_player(previous)
                raise RegistrationError("You already registered this season; contact staff for changes")
            try:
                con.execute(
                    "INSERT INTO players(season_key,discord_user_id,mr_username,mr_username_norm,city,joined_at_utc)"
                    " VALUES(?,?,?,?,?,?)",
                    (season, user_id, display, normalized, city, when),
                )
            except sqlite3.IntegrityError as exc:
                raise RegistrationError("That MR username has already been claimed; contact staff if disputed") from exc
            player = con.execute(
                "SELECT * FROM players WHERE season_key = ? AND discord_user_id = ?",
                (season, user_id),
            ).fetchone()
            return self._make_player(player)

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
            rows = con.execute("SELECT * FROM players WHERE season_key=? ORDER BY joined_at_utc, id",
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
            result = con.execute(
                "UPDATE players SET review_state=? WHERE season_key=? AND discord_user_id=?",
                (state, season, subject_id),
            )
            if result.rowcount != 1:
                raise RegistrationError("Player is not registered")
            con.execute(
                "INSERT INTO admin_audit(season_key,actor_id,subject_id,action,reason,created_at_utc)"
                " VALUES(?,?,?,?,?,?)",
                (season, actor_id, subject_id, "identity_review:" + state,
                 reason.strip(), now.astimezone(timezone.utc).isoformat()),
            )

    def audit_count(self, season: str) -> int:
        with self.connect() as con:
            return con.execute("SELECT COUNT(*) FROM admin_audit WHERE season_key=?",
                               (season,)).fetchone()[0]
