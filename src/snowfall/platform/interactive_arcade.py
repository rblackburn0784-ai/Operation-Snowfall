"""Web-only v2.9.9 interactive-arcade practice sessions.

This separate, explicitly provisioned table never writes to Discord's social
arcade runs, stamps, leaderboards, player resources, or prize/score ledgers.
Practice scores are illustrative and NOT verified competitive results.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.social_arcade import GAMES, SocialArcadeEngine

PRACTICE_DURATIONS = {
    "gallery": 60000, "safe": 90000, "snowman": 90000,
    "catch": 60000, "trivia": 90000,
}
SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
# Explicit web-only migration; do not modify the canonical game schema version.
WEB_ARCADE_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_arcade_practice_sessions (
 session_id TEXT PRIMARY KEY,
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('gallery','safe','snowman','catch','trivia')),
 state_json TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','finished')),
 started_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 FOREIGN KEY(season_key,player_id) REFERENCES players(season_key,discord_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_arcade_practice_active
 ON web_arcade_practice_sessions(season_key,player_id,mode)
 WHERE status='active';
"""
EMPTY_STATE = {"elapsed_ms": 0, "hits": 0, "misses": 0, "progress": 0,
               "position": 0.5, "angle": 0}


def install_practice_schema(connection) -> None:
    """Explicitly called by the QA schema installer or a disposable test DB."""
    for statement in WEB_ARCADE_SCHEMA.strip().split(";"):
        if statement.strip():
            connection.execute(statement.strip())


def _clean_state(data: dict[str, Any], duration: int) -> dict:
    if not isinstance(data, dict) or set(data) != set(EMPTY_STATE):
        raise ValueError("Invalid practice checkpoint fields.")
    result = {}
    for name in ("elapsed_ms", "hits", "misses", "progress", "angle"):
        value = data[name]
        if type(value) is not int:
            raise ValueError("Practice checkpoint contains invalid numbers.")
        result[name] = value
    position = data["position"]
    if type(position) not in (float, int) or not 0 <= position <= 1:
        raise ValueError("Invalid practice position.")
    result["position"] = float(position)
    if not 0 <= result["elapsed_ms"] <= duration:
        raise ValueError("Invalid practice elapsed time.")
    if not 0 <= result["hits"] <= 300 or not 0 <= result["misses"] <= 300:
        raise ValueError("Invalid practice interaction count.")
    if result["hits"] + result["misses"] > result["elapsed_ms"] // 150 + 2:
        raise ValueError("Practice events exceed the elapsed-time limit.")
    if not 0 <= result["progress"] <= 30 or not -720 <= result["angle"] <= 720:
        raise ValueError("Invalid practice checkpoint.")
    return result


class InteractiveArcadePractice:
    """One resumable server-owned practice session per player and mini-game.

    Browser checkpoints are explicitly untrusted and have no scoring authority
    outside this isolated practice table. Competitive validation will be added
    per game in v2.9.9a onward.
    """

    def __init__(self, store: Store, season: str):
        self.store, self.season = store, season

    def _eligible(self, con, user: int, now: datetime) -> None:
        SocialArcadeEngine._eligible(con, self.season, user, now, active=False)

    def _row(self, con, user: int, session_id: str):
        return con.execute(
            "SELECT * FROM web_arcade_practice_sessions "
            "WHERE session_id=? AND season_key=? AND player_id=?",
            (session_id, self.season, user)).fetchone()

    @staticmethod
    def _display(row) -> dict:
        state = json.loads(row["state_json"])
        return {
            "session_id": row["session_id"], "mode": row["mode"],
            "title": GAMES[row["mode"]].title,
            "practice": True, "competitive": False,
            "revision": int(row["revision"]), "status": row["status"],
            "duration_ms": PRACTICE_DURATIONS[row["mode"]],
            "state": state,
            "practice_score": max(0, min(100, state["hits"] * 10 - state["misses"] * 2)),
            "feedback": "Training only — no official scores, starts or rewards.",
        }

    def start(self, user: int, mode: str, *, now: datetime | None = None) -> dict:
        if mode not in PRACTICE_DURATIONS:
            raise ValueError("Unknown interactive practice game.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, user, now)
            row = con.execute(
                "SELECT * FROM web_arcade_practice_sessions "
                "WHERE season_key=? AND player_id=? AND mode=? AND status='active'",
                (self.season, user, mode)).fetchone()
            if row:
                return self._display(row)
            session_id = secrets.token_hex(16)
            timestamp = _timestamp(now)
            con.execute(
                "INSERT INTO web_arcade_practice_sessions "
                "(session_id,season_key,player_id,mode,state_json,started_at_utc,updated_at_utc)"
                " VALUES(?,?,?,?,?,?,?)",
                (session_id, self.season, user, mode,
                 json.dumps(EMPTY_STATE, separators=(",", ":")), timestamp, timestamp))
            return self._display(self._row(con, user, session_id))

    def session(self, user: int, session_id: str, *, now: datetime | None = None) -> dict:
        if not SESSION_ID.fullmatch(session_id):
            raise ValueError("Invalid practice session ID.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN")
            self._eligible(con, user, now)
            row = self._row(con, user, session_id)
            if not row:
                raise ValueError("Practice session unavailable for this player.")
            return self._display(row)

    def save(self, user: int, session_id: str, revision: int, state: dict,
             *, finish: bool = False, now: datetime | None = None) -> dict:
        if not SESSION_ID.fullmatch(session_id) or not 0 <= revision <= 10000:
            raise ValueError("Invalid practice checkpoint.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, user, now)
            row = self._row(con, user, session_id)
            if not row:
                raise ValueError("Practice session unavailable for this player.")
            duration = PRACTICE_DURATIONS[row["mode"]]
            next_state = _clean_state(state, duration)
            old = json.loads(row["state_json"])
            if revision == int(row["revision"]) - 1 and next_state == old and (
                    not finish or row["status"] == "finished"):
                return self._display(row)  # successful duplicate delivery
            if row["status"] != "active":
                raise ValueError("Practice session already finished.")
            if revision != int(row["revision"]):
                raise ValueError("Practice checkpoint is out of date. Resume the saved game.")
            for key in ("elapsed_ms", "hits", "misses", "progress"):
                if next_state[key] < old[key]:
                    raise ValueError("Practice progress cannot move backwards.")
            wall_ms = max(0, int((now - datetime.fromisoformat(
                row["started_at_utc"]).astimezone(timezone.utc)).total_seconds() * 1000))
            if next_state["elapsed_ms"] > wall_ms + 5000:
                raise ValueError("Practice timer cannot advance faster than real time.")
            status = "finished" if finish or next_state["elapsed_ms"] == duration else "active"
            con.execute(
                "UPDATE web_arcade_practice_sessions SET state_json=?,revision=revision+1,"
                "status=?,updated_at_utc=? WHERE session_id=? AND status='active'",
                (json.dumps(next_state, separators=(",", ":")), status,
                 _timestamp(now), session_id))
            return self._display(self._row(con, user, session_id))
