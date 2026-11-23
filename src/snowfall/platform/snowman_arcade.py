"""v2.9.9c Snowman Builder — isolated, server-validated drag-and-drop arcade.

The server issues three escalating blueprints and validates each placement,
part ownership, target position, order, elapsed play and unique interaction.
All results are unranked QA practice: no shared Discord or prize writes.
"""
from __future__ import annotations

import json
import math
import re
import secrets
from datetime import datetime, timezone

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.social_arcade import SocialArcadeEngine

DURATION_MS = 150_000
ROUNDS = (
    ("First Snowfall", ("base", "torso", "head", "hat"), ()),
    ("Frosty Friend", ("base", "torso", "head", "scarf", "nose",
                      "arm_left", "arm_right"), ("sunhat",)),
    ("Blizzard Master", ("base", "torso", "head", "hat", "scarf", "nose",
                         "arm_left", "arm_right", "buttons"), ("beachball", "sunhat")),
)
# Twenty correctly assembled parts, with progressively tougher item trays.
TOTAL_PARTS = sum(len(parts) for _, parts, _ in ROUNDS)
BONUSES = (4, 6, 10)
SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
PIECE_RE = re.compile(r"^[a-z_]{3,24}$")
GEOMETRY = {
    "base": (249, 270, 38),
    "torso": (249, 206, 32),
    "head": (249, 142, 26),
    "hat": (249, 93, 24),
    "scarf": (249, 172, 21),
    "nose": (275, 143, 17),
    "arm_left": (188, 207, 23),
    "arm_right": (309, 207, 23),
    "buttons": (249, 227, 22),
}
LABELS = {
    "base": "Big snowball", "torso": "Middle snowball", "head": "Small snowball",
    "hat": "Top hat", "scarf": "Winter scarf", "nose": "Carrot",
    "arm_left": "Left twig", "arm_right": "Right twig",
    "buttons": "Coal buttons", "sunhat": "Summer hat", "beachball": "Beach ball",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS web_arcade_snowman_sessions (
 session_id TEXT PRIMARY KEY,
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
 status TEXT NOT NULL CHECK(status IN ('active','paused','finished')),
 started_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 resumed_at_utc TEXT,
 finished_at_utc TEXT,
 elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK(elapsed_ms BETWEEN 0 AND 150000),
 blueprint_json TEXT NOT NULL,
 stage INTEGER NOT NULL DEFAULT 0 CHECK(stage BETWEEN 0 AND 3),
 placed_json TEXT NOT NULL DEFAULT '[]',
 placed_total INTEGER NOT NULL DEFAULT 0 CHECK(placed_total BETWEEN 0 AND 20),
 mistakes INTEGER NOT NULL DEFAULT 0 CHECK(mistakes BETWEEN 0 AND 100),
 actions INTEGER NOT NULL DEFAULT 0 CHECK(actions BETWEEN 0 AND 120),
 score INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
 last_action_at_utc TEXT,
 last_feedback TEXT NOT NULL DEFAULT '',
 FOREIGN KEY(season_key,player_id) REFERENCES players(season_key,discord_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_snowman_active
 ON web_arcade_snowman_sessions(season_key,player_id,day)
 WHERE status IN ('active','paused');
CREATE INDEX IF NOT EXISTS idx_web_snowman_records
 ON web_arcade_snowman_sessions(season_key,player_id,status,score);
CREATE TABLE IF NOT EXISTS web_arcade_snowman_actions (
 interaction_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES web_arcade_snowman_sessions(session_id),
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 action_seq INTEGER NOT NULL CHECK(action_seq BETWEEN 0 AND 119),
 stage INTEGER NOT NULL CHECK(stage BETWEEN 0 AND 2),
 piece_id TEXT NOT NULL,
 x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 640),
 y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 360),
 outcome TEXT NOT NULL CHECK(outcome IN ('placed','wrong_spot','decoy')),
 score_after INTEGER NOT NULL CHECK(score_after BETWEEN 0 AND 100),
 feedback TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(session_id,action_seq)
);
"""


def install_snowman_schema(con) -> None:
    """Explicit additive schema install; never called on normal app startup."""
    for statement in SCHEMA.strip().split(";"):
        if statement.strip():
            con.execute(statement.strip())


def make_blueprints(rng=None) -> list[dict]:
    rng = rng or secrets.SystemRandom()
    result = []
    for i, (title, types, decoys) in enumerate(ROUNDS):
        shift_x = rng.randrange(-12, 13)
        shift_y = rng.randrange(-5, 6)
        slots = [{
            "id": type_name,
            "x": GEOMETRY[type_name][0] + shift_x,
            "y": GEOMETRY[type_name][1] + shift_y,
            "radius": GEOMETRY[type_name][2],
        } for type_name in types]
        parts = [
            {"id": key, "label": LABELS[key], "decoy": key in decoys}
            for key in (*types, *decoys)
        ]
        rng.shuffle(parts)
        result.append({
            "round": i + 1, "name": title,
            "slots": slots, "parts": parts, "required": len(types),
            "bonus": BONUSES[i],
        })
    return result


def _elapsed(row, now: datetime) -> int:
    elapsed = int(row["elapsed_ms"])
    if row["status"] == "active" and row["resumed_at_utc"]:
        then = datetime.fromisoformat(row["resumed_at_utc"]).astimezone(timezone.utc)
        elapsed += max(0, round((now - then).total_seconds() * 1000))
    return min(DURATION_MS, elapsed)


def _score(placed: int, mistakes: int, stage: int, elapsed: int = 0,
           completed: bool = False) -> int:
    earned = placed * 4 + sum(BONUSES[:stage]) - mistakes * 3
    if completed:
        earned -= elapsed // 30_000  # small time-efficiency tie-breaker
    return max(0, min(100, earned))


class SnowmanBuilderEngine:
    """Three blueprints, server-confirmed piece drops and practice-only scores."""

    def __init__(self, store: Store, season: str, rng=None):
        self.store, self.season = store, season
        self.rng = rng or secrets.SystemRandom()

    def _eligible(self, con, user: int, now: datetime, active=False):
        return SocialArcadeEngine._eligible(
            con, self.season, user, now, active=active)[1]

    def _row(self, con, user: int, sid: str):
        return con.execute(
            "SELECT * FROM web_arcade_snowman_sessions "
            "WHERE session_id=? AND season_key=? AND player_id=?",
            (sid, self.season, user)).fetchone()

    @staticmethod
    def _sync(con, row, now: datetime):
        if row["status"] == "active" and _elapsed(row, now) >= DURATION_MS:
            stamp = _timestamp(now)
            con.execute(
                "UPDATE web_arcade_snowman_sessions SET status='finished',"
                "elapsed_ms=?,resumed_at_utc=NULL,updated_at_utc=?,"
                "finished_at_utc=?,last_feedback=? WHERE session_id=?",
                (DURATION_MS, stamp, stamp,
                 "Snowstorm! Your workshop time has expired.", row["session_id"]))
            row = con.execute(
                "SELECT * FROM web_arcade_snowman_sessions WHERE session_id=?",
                (row["session_id"],)).fetchone()
        return row

    @staticmethod
    def _snapshot(row, now: datetime, *, repeated=False, last_action=None):
        blueprints = json.loads(row["blueprint_json"])
        stage = int(row["stage"])
        finished = row["status"] == "finished"
        return {
            "session_id": row["session_id"], "mode": "snowman",
            "title": "Snowman Builder", "day": int(row["day"]),
            "practice": True, "competitive": False,
            "status": row["status"], "stage": stage,
            "round": min(stage + 1, 3), "total_rounds": 3,
            "duration_ms": DURATION_MS, "elapsed_ms": _elapsed(row, now),
            "blueprint": blueprints[stage] if stage < 3 else blueprints[-1],
            "placed": json.loads(row["placed_json"]),
            "placed_total": int(row["placed_total"]),
            "total_parts": TOTAL_PARTS,
            "mistakes": int(row["mistakes"]), "action_seq": int(row["actions"]),
            "score": int(row["score"]), "feedback": row["last_feedback"],
            "repeated": repeated, "last_action": last_action,
            "complete": stage == 3,
            "result": ("FROSTY MASTERPIECE! All three snowmen built."
                       if stage == 3 else "Workshop closed. Try another build!")
                      if finished else None,
            "note": "Unranked practice; does not consume competitive starts or award prizes.",
        }

    def start(self, user: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            existing = con.execute(
                "SELECT * FROM web_arcade_snowman_sessions WHERE season_key=? "
                "AND player_id=? AND day=? AND status IN ('paused','active')",
                (self.season, user, day)).fetchone()
            if existing:
                existing = self._sync(con, existing, now)
                if existing["status"] != "finished":
                    return self._snapshot(existing, now)
            stamp = _timestamp(now)
            sid = secrets.token_hex(16)
            con.execute(
                "INSERT INTO web_arcade_snowman_sessions "
                "(session_id,season_key,player_id,day,status,started_at_utc,"
                "updated_at_utc,blueprint_json) VALUES(?,?,?,?,?,?,?,?)",
                (sid, self.season, user, day, "paused", stamp, stamp,
                 json.dumps(make_blueprints(self.rng), separators=(",", ":"))))
            return self._snapshot(self._row(con, user, sid), now)

    def session(self, user: int, sid: str, *, now: datetime | None = None) -> dict:
        if not SESSION_RE.fullmatch(sid):
            raise ValueError("Invalid Snowman Builder session.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, user, now, active=False)
            row = self._row(con, user, sid)
            if not row:
                raise ValueError("Snowman Builder session unavailable for this player.")
            return self._snapshot(self._sync(con, row, now), now)

    def control(self, user: int, sid: str, action: str,
                *, now: datetime | None = None) -> dict:
        if not SESSION_RE.fullmatch(sid) or action not in ("pause", "resume", "finish"):
            raise ValueError("Invalid Snowman Builder control.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=action == "resume")
            row = self._row(con, user, sid)
            if not row:
                raise ValueError("Snowman Builder session unavailable for this player.")
            row = self._sync(con, row, now)
            if row["status"] == "finished":
                return self._snapshot(row, now)
            if row["day"] != day:
                raise ValueError("Builder session belongs to a previous day.")
            status = ("finished" if action == "finish" else
                      "active" if action == "resume" else "paused")
            if row["status"] != status:
                stamp = _timestamp(now)
                elapsed = _elapsed(row, now)
                con.execute(
                    "UPDATE web_arcade_snowman_sessions SET status=?,elapsed_ms=?,"
                    "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=?,"
                    "last_feedback=? WHERE session_id=?",
                    (status, elapsed, stamp if status == "active" else None,
                     stamp if status == "finished" else None, stamp,
                     {"pause": "Workshop paused and safely saved.",
                      "resume": "Choose a part and build your snowman!",
                      "finish": "You left the workshop early."}[action], sid))
                row = self._row(con, user, sid)
            return self._snapshot(row, now)

    def place(self, user: int, sid: str, action_seq: int, piece_id: str, x: int,
              y: int, interaction_id: str, *, now: datetime | None = None) -> dict:
        if (not SESSION_RE.fullmatch(sid) or type(action_seq) is not int
                or not 0 <= action_seq < 120 or not isinstance(piece_id, str)
                or not PIECE_RE.fullmatch(piece_id)
                or type(x) is not int or type(y) is not int
                or not 0 <= x <= 640 or not 0 <= y <= 360
                or not isinstance(interaction_id, str)
                or not 1 <= len(interaction_id) <= 128):
            raise ValueError("Invalid Snowman Builder placement.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            replay = con.execute(
                "SELECT * FROM web_arcade_snowman_actions WHERE interaction_id=?",
                (interaction_id,)).fetchone()
            if replay:
                if (replay["session_id"] != sid or replay["season_key"] != self.season
                        or replay["player_id"] != user
                        or replay["action_seq"] != action_seq
                        or replay["piece_id"] != piece_id or replay["x"] != x
                        or replay["y"] != y):
                    raise ValueError("Snowman placement key belongs to another action.")
                row = self._row(con, user, sid)
                return self._snapshot(row, now, repeated=True, last_action={
                    "outcome": replay["outcome"], "piece_id": piece_id,
                    "feedback": replay["feedback"], "stage": replay["stage"]})
            row = self._row(con, user, sid)
            if not row:
                raise ValueError("Snowman Builder session unavailable for this player.")
            row = self._sync(con, row, now)
            if row["status"] != "active" or row["day"] != day:
                raise ValueError("Snowman Builder is paused, finished or from an earlier day.")
            if action_seq != int(row["actions"]):
                raise ValueError("Out-of-order Snowman Builder placement. Refresh the game.")
            if row["last_action_at_utc"]:
                last = datetime.fromisoformat(row["last_action_at_utc"]).astimezone(timezone.utc)
                if (now-last).total_seconds()*1000 < 170:
                    raise ValueError("Wait before placing another snowman part.")
            plans = json.loads(row["blueprint_json"])
            stage = int(row["stage"])
            plan = plans[stage]
            parts = {p["id"]: p for p in plan["parts"]}
            if piece_id not in parts:
                raise ValueError("Part does not belong to this blueprint.")
            placed = set(json.loads(row["placed_json"]))
            if piece_id in placed:
                raise ValueError("Snowman part has already been placed.")
            target = next((slot for slot in plan["slots"]
                           if slot["id"] == piece_id), None)
            correct = target is not None and math.hypot(
                x-target["x"], y-target["y"]) <= target["radius"]
            outcome = ("placed" if correct else
                       "decoy" if target is None else "wrong_spot")
            if correct:
                placed.add(piece_id)
                feedback = "Perfect fit! "+LABELS[piece_id]+" placed."
            elif target is None:
                feedback = "That's a decoy! Find real snowman parts."
            else:
                feedback = "That piece belongs elsewhere. Match the outline."
            mistakes = int(row["mistakes"]) + (not correct)
            total = int(row["placed_total"]) + correct
            if len(placed) == plan["required"]:
                stage += 1
                placed = set()
                if stage == 3:
                    feedback = "MASTER BUILDER! All three snowmen are complete."
                else:
                    feedback = "Blueprint complete! On to "+plans[stage]["name"]+"."
            elapsed = _elapsed(row, now)
            finished = stage == 3 or action_seq == 119
            score = _score(total, mistakes, stage, elapsed, completed=stage == 3)
            stamp = _timestamp(now)
            con.execute(
                "UPDATE web_arcade_snowman_sessions SET stage=?,placed_json=?,"
                "placed_total=?,mistakes=?,actions=actions+1,score=?,"
                "last_action_at_utc=?,last_feedback=?,status=?,elapsed_ms=?,"
                "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=? "
                "WHERE session_id=?",
                (stage, json.dumps(sorted(placed)), total, mistakes, score,
                 stamp, feedback, "finished" if finished else "active",
                 elapsed if finished else int(row["elapsed_ms"]),
                 None if finished else row["resumed_at_utc"],
                 stamp if finished else None, stamp, sid))
            con.execute(
                "INSERT INTO web_arcade_snowman_actions "
                "(interaction_id,session_id,season_key,player_id,action_seq,"
                "stage,piece_id,x,y,outcome,score_after,feedback,created_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (interaction_id, sid, self.season, user, action_seq, int(row["stage"]),
                 piece_id, x, y, outcome, score, feedback, stamp))
            return self._snapshot(self._row(con, user, sid), now, last_action={
                "outcome": outcome, "piece_id": piece_id,
                "feedback": feedback, "stage": int(row["stage"]),
            })

    def record(self, user: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            self._eligible(con, user, now, active=False)
            record = con.execute(
                "SELECT COALESCE(MAX(score),0),COUNT(*),"
                "COALESCE(SUM(CASE WHEN stage=3 THEN 1 ELSE 0 END),0) "
                "FROM web_arcade_snowman_sessions WHERE season_key=? AND player_id=? "
                "AND status='finished'", (self.season, user)).fetchone()
            return {"personal_best": int(record[0]), "finished_runs": int(record[1]),
                    "completed_builds": int(record[2]), "practice": True,
                    "competitive": False}
