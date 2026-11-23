"""v2.9.9b: isolated Frozen Safecracker with server-owned combinations.

The browser moves a tactile forty-notch dial. The server validates rotation,
direction, stage, dial position, play clock and shot-like action sequencing.
All scores remain QA-only: never Discord arcade, economy or prize records.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import secrets

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.social_arcade import SocialArcadeEngine

DURATION_MS = 90_000
NOTCHES = 40
DIRECTIONS = (1, -1, 1)  # clockwise, anticlockwise, clockwise
MIN_TRAVEL = (40, 40, 40)  # complete rotation before each tumbler seats
MAX_MOVES = 100
MAX_ACTIONS = 300
SESSION_RE = re.compile(r"^[0-9a-f]{32}$")

SAFE_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_arcade_safe_sessions (
 session_id TEXT PRIMARY KEY,
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
 status TEXT NOT NULL CHECK(status IN ('paused','active','finished')),
 elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK(elapsed_ms BETWEEN 0 AND 90000),
 resumed_at_utc TEXT,
 combination_json TEXT NOT NULL,
 dial INTEGER NOT NULL DEFAULT 0 CHECK(dial BETWEEN 0 AND 39),
 stage INTEGER NOT NULL DEFAULT 0 CHECK(stage BETWEEN 0 AND 3),
 travel INTEGER NOT NULL DEFAULT 0 CHECK(travel BETWEEN 0 AND 10000),
 total_ticks INTEGER NOT NULL DEFAULT 0 CHECK(total_ticks BETWEEN 0 AND 10000),
 mistakes INTEGER NOT NULL DEFAULT 0 CHECK(mistakes BETWEEN 0 AND 100),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 100),
 action_seq INTEGER NOT NULL DEFAULT 0 CHECK(action_seq BETWEEN 0 AND 300),
 score INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
 last_feedback TEXT NOT NULL DEFAULT '',
 started_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 finished_at_utc TEXT,
 FOREIGN KEY(season_key,player_id) REFERENCES players(season_key,discord_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_safe_active
 ON web_arcade_safe_sessions(season_key,player_id,day)
 WHERE status IN ('paused','active');
CREATE INDEX IF NOT EXISTS idx_web_safe_records
 ON web_arcade_safe_sessions(season_key,player_id,status,score);
CREATE TABLE IF NOT EXISTS web_arcade_safe_actions (
 interaction_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES web_arcade_safe_sessions(session_id),
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 action_seq INTEGER NOT NULL CHECK(action_seq BETWEEN 0 AND 299),
 action TEXT NOT NULL CHECK(action IN ('turn','set')),
 ticks INTEGER NOT NULL CHECK(ticks BETWEEN -80 AND 80),
 stage_after INTEGER NOT NULL CHECK(stage_after BETWEEN 0 AND 3),
 dial_after INTEGER NOT NULL CHECK(dial_after BETWEEN 0 AND 39),
 feedback TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(session_id,action_seq)
);
"""


def install_safe_schema(connection) -> None:
    """Explicit additive QA schema only, never called at server startup."""
    for statement in SAFE_SCHEMA.strip().split(";"):
        if statement.strip():
            connection.execute(statement.strip())


def _elapsed(row, now: datetime) -> int:
    elapsed = int(row["elapsed_ms"])
    if row["status"] == "active" and row["resumed_at_utc"]:
        resumed = datetime.fromisoformat(row["resumed_at_utc"]).astimezone(timezone.utc)
        elapsed += max(0, round((now - resumed).total_seconds() * 1000))
    return min(DURATION_MS, elapsed)


def proximity(dial: int, code: int) -> int:
    """Circular forty-notch distance; stop at the exact alignment."""
    d = abs(dial - code)
    return min(d, NOTCHES - d)


def _signal(row) -> str:
    stage = int(row["stage"])
    if stage >= 3:
        return "open"
    if int(row["travel"]) < MIN_TRAVEL[stage]:
        return "turn"
    code = json.loads(row["combination_json"])[stage]
    distance = proximity(int(row["dial"]), code)
    if distance == 0:
        return "click"
    if distance <= 3:
        return "near"
    if distance <= 7:
        return "faint"
    return "quiet"


class SafecrackerEngine:
    """One resumable, server-timed QA safe round per player/event day."""

    def __init__(self, store: Store, season: str, rng=None):
        self.store = store
        self.season = season
        self.rng = rng or secrets.SystemRandom()

    def _eligible(self, con, player_id: int, now: datetime, active: bool):
        return SocialArcadeEngine._eligible(
            con, self.season, player_id, now, active=active)[1]

    def _row(self, con, player_id: int, session_id: str):
        return con.execute(
            "SELECT * FROM web_arcade_safe_sessions WHERE session_id=? "
            "AND season_key=? AND player_id=?",
            (session_id, self.season, player_id)).fetchone()

    @staticmethod
    def _sync(con, row, now: datetime):
        if row["status"] == "active" and _elapsed(row, now) >= DURATION_MS:
            stamp = _timestamp(now)
            con.execute(
                "UPDATE web_arcade_safe_sessions SET status='finished',elapsed_ms=?,"
                "resumed_at_utc=NULL,updated_at_utc=?,finished_at_utc=?,"
                "last_feedback=? WHERE session_id=?",
                (DURATION_MS, stamp, stamp,
                 "Time is up! The combination lock is frozen shut.", row["session_id"]))
            return con.execute(
                "SELECT * FROM web_arcade_safe_sessions WHERE session_id=?",
                (row["session_id"],)).fetchone()
        return row

    @staticmethod
    def _snapshot(row, now: datetime, *, repeated=False, last_action=None):
        stage = int(row["stage"])
        elapsed = _elapsed(row, now)
        finished = row["status"] == "finished"
        complete = stage == 3
        answer = json.loads(row["combination_json"]) if finished else None
        return {
            "session_id": row["session_id"], "mode": "safe",
            "title": "Frozen Safecracker", "day": int(row["day"]),
            "status": row["status"], "practice": True, "competitive": False,
            "duration_ms": DURATION_MS, "elapsed_ms": elapsed,
            "server_epoch_ms": round(now.timestamp() * 1000),
            "dial": int(row["dial"]), "stage": stage,
            "direction": DIRECTIONS[stage] if stage < 3 else 0,
            "turn_required": MIN_TRAVEL[stage] if stage < 3 else 0,
            "travel": int(row["travel"]),
            "signal": _signal(row), "mistakes": int(row["mistakes"]),
            "attempts": int(row["attempts"]), "action_seq": int(row["action_seq"]),
            "score": int(row["score"]), "feedback": row["last_feedback"],
            "unlocked": complete, "combination": answer, "repeated": repeated,
            "last_action": last_action,
            "result": ("VAULT OPEN! Brilliant safecracking." if complete else
                       "Time's up. Try again with a fresh safe.") if finished else None,
            "note": "QA practice only — no Discord starts, resources, rankings or prizes.",
        }

    def start(self, player_id: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, player_id, now, active=True)
            row = con.execute(
                "SELECT * FROM web_arcade_safe_sessions WHERE season_key=? "
                "AND player_id=? AND day=? AND status IN ('active','paused')",
                (self.season, player_id, day)).fetchone()
            if row:
                row = self._sync(con, row, now)
                if row["status"] != "finished":
                    return self._snapshot(row, now)
            sid = secrets.token_hex(16)
            # Stable secret per session, never returned until the safe is finished.
            combination = [self.rng.randrange(NOTCHES) for _ in range(3)]
            stamp = _timestamp(now)
            con.execute(
                "INSERT INTO web_arcade_safe_sessions "
                "(session_id,season_key,player_id,day,status,"
                "combination_json,started_at_utc,updated_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (sid, self.season, player_id, day, "paused",
                 json.dumps(combination), stamp, stamp))
            return self._snapshot(self._row(con, player_id, sid), now)

    def session(self, player_id: int, session_id: str, *,
                now: datetime | None = None) -> dict:
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("Invalid safecracker session.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, player_id, now, active=False)
            row = self._row(con, player_id, session_id)
            if row is None:
                raise ValueError("Safecracker session unavailable for this player.")
            return self._snapshot(self._sync(con, row, now), now)

    def control(self, player_id: int, session_id: str, action: str, *,
                now: datetime | None = None) -> dict:
        if not SESSION_RE.fullmatch(session_id) or action not in (
                "pause", "resume", "finish"):
            raise ValueError("Invalid safecracker control.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, player_id, now, active=action == "resume")
            row = self._row(con, player_id, session_id)
            if row is None:
                raise ValueError("Safecracker session unavailable for this player.")
            row = self._sync(con, row, now)
            if row["status"] == "finished":
                return self._snapshot(row, now)
            if day != row["day"]:
                raise ValueError("Safecracker belongs to a previous event day.")
            status = ("finished" if action == "finish" else
                      "active" if action == "resume" else "paused")
            if row["status"] != status:
                elapsed = _elapsed(row, now)
                stamp = _timestamp(now)
                con.execute(
                    "UPDATE web_arcade_safe_sessions SET status=?,elapsed_ms=?,"
                    "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=?,last_feedback=? "
                    "WHERE session_id=?",
                    (status, elapsed, stamp if status == "active" else None,
                     stamp if status == "finished" else None, stamp,
                     {"pause": "Dial frozen. Your progress is saved.",
                      "resume": "Listen for the tumblers. Turn the dial!",
                      "finish": "The safe was left unopened."}[action],
                     session_id))
                row = self._row(con, player_id, session_id)
            return self._snapshot(row, now)

    def move(self, player_id: int, session_id: str, action_seq: int,
             action: str, ticks: int, interaction_id: str, *,
             now: datetime | None = None) -> dict:
        """One atomic turn gesture or tumbler seating, never client scores."""
        if not SESSION_RE.fullmatch(session_id) or (
                type(action_seq) is not int or not 0 <= action_seq < MAX_ACTIONS
                or action not in ("turn", "set") or type(ticks) is not int
                or (action == "set" and ticks != 0)
                or (action == "turn" and not 1 <= abs(ticks) <= 80)
                or not isinstance(interaction_id, str)
                or not 1 <= len(interaction_id) <= 128):
            raise ValueError("Invalid safecracker action.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, player_id, now, active=True)
            replay = con.execute(
                "SELECT * FROM web_arcade_safe_actions WHERE interaction_id=?",
                (interaction_id,)).fetchone()
            if replay:
                if (replay["session_id"] != session_id or replay["season_key"] != self.season
                        or replay["player_id"] != player_id
                        or replay["action_seq"] != action_seq
                        or replay["action"] != action or replay["ticks"] != ticks):
                    raise ValueError("Safecracker action key belongs to another request.")
                row = self._row(con, player_id, session_id)
                return self._snapshot(row, now, repeated=True, last_action={
                    "action": replay["action"], "stage": int(replay["stage_after"]),
                    "feedback": replay["feedback"], "seq": action_seq})
            row = self._row(con, player_id, session_id)
            if row is None:
                raise ValueError("Safecracker session unavailable for this player.")
            row = self._sync(con, row, now)
            if row["status"] != "active" or day != row["day"]:
                raise ValueError("Safecracker is paused, finished, or from an earlier day.")
            if action_seq != int(row["action_seq"]):
                raise ValueError("Out-of-order safecracker action. Refresh the game.")
            elapsed = _elapsed(row, now)
            dial = int(row["dial"])
            travel = int(row["travel"])
            total_ticks = int(row["total_ticks"])
            mistakes = int(row["mistakes"])
            attempts = int(row["attempts"])
            stage = int(row["stage"])
            combo = json.loads(row["combination_json"])
            finished = False
            score = int(row["score"])
            if action == "turn":
                # Allows a whole gesture from desktop/touch, but blocks obvious
                # teleportation or impossible accumulated rotation speeds.
                total_ticks += abs(ticks)
                if total_ticks > elapsed // 18 + 12:
                    raise ValueError("Dial is turning too fast for the elapsed time.")
                dial = (dial + ticks) % NOTCHES
                if ticks * DIRECTIONS[stage] > 0:
                    travel = min(10000, travel + abs(ticks))
                    feedback = "Dial turning. Listen for a click near the next number."
                else:
                    travel = 0
                    mistakes = min(100, mistakes + 1)
                    feedback = "Wrong direction! Tumbler slipped — start this turn again."
            else:
                attempts = min(100, attempts + 1)
                valid = (travel >= MIN_TRAVEL[stage] and
                         proximity(dial, combo[stage]) == 0)
                if valid:
                    stage += 1
                    travel = 0
                    feedback = ("TUMBLER " + str(stage) + " SET! " +
                                ("The safe is OPEN!" if stage == 3
                                 else "Reverse direction and find the next click."))
                    if stage == 3:
                        finished = True
                        score = max(15, min(100, 100 - mistakes * 8 -
                                          (attempts - 3) * 6 - elapsed // 3500))
                else:
                    travel = 0
                    mistakes = min(100, mistakes + 1)
                    feedback = ("Not aligned! Complete a full turn in the required "
                                "direction and listen for the clear click.")
            stamp = _timestamp(now)
            status = "finished" if finished else "active"
            if action_seq + 1 >= MAX_ACTIONS and not finished:
                status = "finished"
                feedback = "Too many dial operations. Start a new practice safe."
            con.execute(
                "UPDATE web_arcade_safe_sessions SET dial=?,stage=?,travel=?,"
                "total_ticks=?,mistakes=?,attempts=?,action_seq=action_seq+1,"
                "score=?,status=?,elapsed_ms=?,resumed_at_utc=?,finished_at_utc=?,"
                "updated_at_utc=?,last_feedback=? WHERE session_id=?",
                (dial, stage, travel, total_ticks, mistakes, attempts, score,
                 status, elapsed if status == "finished" else int(row["elapsed_ms"]),
                 None if status == "finished" else row["resumed_at_utc"],
                 stamp if status == "finished" else None, stamp, feedback, session_id))
            con.execute(
                "INSERT INTO web_arcade_safe_actions "
                "(interaction_id,session_id,season_key,player_id,action_seq,"
                "action,ticks,stage_after,dial_after,feedback,created_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (interaction_id, session_id, self.season, player_id, action_seq,
                 action, ticks, stage, dial, feedback, stamp))
            return self._snapshot(self._row(con, player_id, session_id), now,
                                  last_action={"action": action, "stage": stage,
                                               "feedback": feedback, "seq": action_seq})

    def record(self, player_id: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            self._eligible(con, player_id, now, active=False)
            row = con.execute(
                "SELECT COALESCE(MAX(score),0),COUNT(*),"
                "COALESCE(SUM(CASE WHEN stage=3 THEN 1 ELSE 0 END),0) "
                "FROM web_arcade_safe_sessions WHERE season_key=? AND player_id=? "
                "AND status='finished'", (self.season, player_id)).fetchone()
            return {"personal_best": int(row[0]), "finished_runs": int(row[1]),
                    "vaults_opened": int(row[2]), "practice": True,
                    "competitive": False}
