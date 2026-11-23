"""v2.9.9d: server-authoritative, independently audited Snowflake Catch arcade.

The server owns the falling-object schedule, collision time and x-coordinate,
basket speed, item resolution, scores and the timer. Browser position reports
never include claims of a catch or a result. QA-only/unranked and separate from
all Discord scores, resources and prizes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
import secrets

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.social_arcade import SocialArcadeEngine

DURATION_MS = 60_000
WIDTH = 640
HEIGHT = 360
CATCH_Y = 300
BASKET_START = 320
BASKET_MIN = 66
BASKET_MAX = 574
BASKET_TOLERANCE = 48
MAX_SPEED_PX_MS = 0.95
MAX_ACTIONS = 360
SESSION_RE = re.compile(r"^[a-f0-9]{32}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_arcade_catch_sessions (
 session_id TEXT PRIMARY KEY,
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
 status TEXT NOT NULL CHECK(status IN ('active','paused','finished')),
 elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK(elapsed_ms BETWEEN 0 AND 60000),
 resumed_at_utc TEXT,
 schedule_json TEXT NOT NULL,
 settled_json TEXT NOT NULL DEFAULT '[]',
 basket_x INTEGER NOT NULL DEFAULT 320 CHECK(basket_x BETWEEN 66 AND 574),
 last_position_elapsed INTEGER NOT NULL DEFAULT 0,
 actions INTEGER NOT NULL DEFAULT 0 CHECK(actions BETWEEN 0 AND 360),
 caught INTEGER NOT NULL DEFAULT 0,
 missed INTEGER NOT NULL DEFAULT 0,
 hazards INTEGER NOT NULL DEFAULT 0,
 bonus INTEGER NOT NULL DEFAULT 0,
 combo INTEGER NOT NULL DEFAULT 0,
 best_combo INTEGER NOT NULL DEFAULT 0,
 score INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
 last_feedback TEXT NOT NULL DEFAULT '',
 started_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 finished_at_utc TEXT,
 FOREIGN KEY(season_key,player_id) REFERENCES players(season_key,discord_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_catch_active
 ON web_arcade_catch_sessions(season_key,player_id,day)
 WHERE status IN ('active','paused');
CREATE INDEX IF NOT EXISTS idx_web_catch_record
 ON web_arcade_catch_sessions(season_key,player_id,status,score);
CREATE TABLE IF NOT EXISTS web_arcade_catch_actions (
 interaction_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES web_arcade_catch_sessions(session_id),
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 action_seq INTEGER NOT NULL CHECK(action_seq BETWEEN 0 AND 359),
 x INTEGER NOT NULL CHECK(x BETWEEN 66 AND 574),
 settled_events_json TEXT NOT NULL,
 score_after INTEGER NOT NULL CHECK(score_after BETWEEN 0 AND 100),
 created_at_utc TEXT NOT NULL,
 UNIQUE(session_id,action_seq)
);
"""


def install_catch_schema(con) -> None:
    """Additive, idempotent; call exclusively via the guarded QA installer."""
    for statement in SCHEMA.strip().split(";"):
        if statement.strip():
            con.execute(statement.strip())


def generate_schedule(rng=None) -> list[dict]:
    rng = rng or secrets.SystemRandom()
    schedule = []
    for i in range(45):
        start = 650 + i * 1280
        wave = min(3, start // 20_000 + 1)
        kind = ("hazard" if i > 3 and i % 9 == 6 else
                "gold" if i % 8 == 5 else
                "crystal" if i % 7 == 3 else "snowflake")
        flight = (2550, 2220, 1880)[wave - 1]
        drift = rng.choice((-1, 1)) * rng.randrange(30 + wave * 9, 65 + wave * 14)
        x0 = rng.randrange(125, 516)
        schedule.append({
            "id": i, "kind": kind, "wave": wave,
            "start": start, "flight": flight, "impact": start + flight,
            "x0": x0, "wind": drift,
            "sway": rng.randrange(8, 22),
            "phase": round(rng.uniform(0, math.tau), 5),
        })
    return schedule


def flake_position(flake: dict, elapsed_ms: int) -> tuple[float, float]:
    """Pure server/browser shared physics. Only the server awards a catch."""
    p = max(0.0, min(1.0, (elapsed_ms - flake["start"]) / flake["flight"]))
    x = (flake["x0"] + flake["wind"] * p +
         flake["sway"] * (math.sin(flake["phase"] + p * math.pi * 2) -
                         math.sin(flake["phase"])))
    return x, 38 + (CATCH_Y - 38) * p


def _elapsed(row, now: datetime) -> int:
    elapsed = int(row["elapsed_ms"])
    if row["status"] == "active" and row["resumed_at_utc"]:
        then = datetime.fromisoformat(row["resumed_at_utc"]).astimezone(timezone.utc)
        elapsed += max(0, round((now - then).total_seconds() * 1000))
    return min(DURATION_MS, elapsed)


def _resolve(row, elapsed_ms: int, new_x: int):
    """Evaluate *every* falling item crossing the basket line, not claims sent
    by the client. Interpolate valid basket movement between position reports.
    Hazards therefore cannot be omitted to avoid their penalty.
    """
    settled = set(json.loads(row["settled_json"]))
    start_ms = int(row["last_position_elapsed"])
    old_x = int(row["basket_x"])
    duration = max(1, elapsed_ms - start_ms)
    caught = int(row["caught"])
    missed = int(row["missed"])
    hazards = int(row["hazards"])
    bonus = int(row["bonus"])
    combo = int(row["combo"])
    best_combo = int(row["best_combo"])
    score = int(row["score"])
    events = []
    for item in json.loads(row["schedule_json"]):
        if item["id"] in settled or item["impact"] > elapsed_ms:
            continue
        # For late/stale updates after a pause, the old basket position is
        # used for historical events, preventing rewrites of settled catches.
        fraction = max(0.0, min(1.0, (item["impact"] - start_ms) / duration))
        basket = old_x + (new_x - old_x) * fraction
        fx, _ = flake_position(item, item["impact"])
        hit = abs(basket - fx) <= BASKET_TOLERANCE
        kind = item["kind"]
        if hit and kind == "hazard":
            hazards += 1
            combo = 0
            score = max(0, score - 12)
            outcome = "hazard"
            feedback = "Ouch! An icy shard hit your basket. −12"
        elif hit:
            caught += 1
            combo += 1
            best_combo = max(combo, best_combo)
            bonus += kind in ("gold", "crystal")
            points = {"snowflake": 3, "crystal": 6, "gold": 10}[kind]
            points += min(3, combo // 4)
            score = min(100, score + points)
            outcome = "caught"
            feedback = ("Golden flake!" if kind == "gold" else
                        "Crystal bonus!" if kind == "crystal" else
                        "Nice catch!") + f" +{points}"
        else:
            if kind != "hazard":
                missed += 1
                combo = 0
            outcome = "avoided" if kind == "hazard" else "missed"
            feedback = "Hazard avoided!" if kind == "hazard" else "Snowflake missed."
        settled.add(item["id"])
        events.append({"id": item["id"], "kind": kind,
                       "outcome": outcome, "feedback": feedback,
                       "score_after": score})
    return {
        "settled": sorted(settled), "caught": caught, "missed": missed,
        "hazards": hazards, "bonus": bonus, "combo": combo,
        "best_combo": best_combo, "score": score, "events": events,
    }


class SnowflakeCatchEngine:
    """Transactional, timed catch resolution with independent QA records."""

    def __init__(self, store: Store, season: str, rng=None):
        self.store, self.season = store, season
        self.rng = rng or secrets.SystemRandom()

    def _eligible(self, con, user: int, now: datetime, active=False):
        return SocialArcadeEngine._eligible(
            con, self.season, user, now, active=active)[1]

    def _row(self, con, user: int, session_id: str):
        return con.execute(
            "SELECT * FROM web_arcade_catch_sessions "
            "WHERE session_id=? AND season_key=? AND player_id=?",
            (session_id, self.season, user)).fetchone()

    @staticmethod
    def _snapshot(row, now, *, events=None, repeated=False):
        ms = _elapsed(row, now)
        score = int(row["score"])
        finished = row["status"] == "finished"
        return {
            "session_id": row["session_id"], "mode": "catch",
            "title": "Snowflake Catch", "status": row["status"],
            "day": int(row["day"]), "practice": True,
            "competitive": False, "duration_ms": DURATION_MS,
            "elapsed_ms": ms, "schedule": json.loads(row["schedule_json"]),
            "settled": json.loads(row["settled_json"]),
            "basket_x": int(row["basket_x"]),
            "action_seq": int(row["actions"]),
            "caught": int(row["caught"]), "missed": int(row["missed"]),
            "hazards": int(row["hazards"]), "bonus": int(row["bonus"]),
            "combo": int(row["combo"]), "best_combo": int(row["best_combo"]),
            "score": score, "events": events or [],
            "repeated": repeated, "feedback": row["last_feedback"],
            "result": ("BLIZZARD CHAMPION!" if score >= 85 else
                       "Frosty reflexes!" if score >= 55 else
                       "Keep catching!") if finished else None,
            "note": "Unranked QA only; no Discord starts, event resources or prizes.",
        }

    @staticmethod
    def _settle(con, row, now, elapsed_ms: int, x: int):
        result = _resolve(row, elapsed_ms, x)
        ended = row["status"] == "active" and elapsed_ms >= DURATION_MS
        stamp = _timestamp(now)
        feedback = result["events"][-1]["feedback"] if result["events"] else row["last_feedback"]
        if ended:
            feedback = "Time! Your snowflake basket is full of memories."
        con.execute(
            "UPDATE web_arcade_catch_sessions SET settled_json=?,basket_x=?,"
            "last_position_elapsed=?,caught=?,missed=?,hazards=?,bonus=?,"
            "combo=?,best_combo=?,score=?,last_feedback=?,"
            "updated_at_utc=?,status=?,elapsed_ms=?,resumed_at_utc=?,"
            "finished_at_utc=? WHERE session_id=?",
            (json.dumps(result["settled"]), x, elapsed_ms,
             result["caught"], result["missed"], result["hazards"],
             result["bonus"], result["combo"], result["best_combo"],
             result["score"], feedback, stamp,
             "finished" if ended else row["status"],
             elapsed_ms if ended else int(row["elapsed_ms"]),
             None if ended else row["resumed_at_utc"],
             stamp if ended else row["finished_at_utc"], row["session_id"]))
        updated = con.execute(
            "SELECT * FROM web_arcade_catch_sessions WHERE session_id=?",
            (row["session_id"],)).fetchone()
        return updated, result["events"]

    def start(self, user: int, *, now: datetime | None = None):
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            row = con.execute(
                "SELECT * FROM web_arcade_catch_sessions WHERE season_key=? "
                "AND player_id=? AND day=? AND status IN ('active','paused')",
                (self.season, user, day)).fetchone()
            if row is not None:
                if row["status"] == "active":
                    row, events = self._settle(
                        con, row, now, _elapsed(row, now), int(row["basket_x"]))
                    if row["status"] != "finished":
                        return self._snapshot(row, now, events=events)
                else:
                    return self._snapshot(row, now)
            sid, stamp = secrets.token_hex(16), _timestamp(now)
            con.execute(
                "INSERT INTO web_arcade_catch_sessions "
                "(session_id,season_key,player_id,day,status,schedule_json,"
                "started_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                (sid, self.season, user, day, "paused",
                 json.dumps(generate_schedule(self.rng), separators=(",", ":")),
                 stamp, stamp))
            return self._snapshot(self._row(con, user, sid), now)

    def session(self, user: int, session_id: str, *, now: datetime | None = None):
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("Invalid Snowflake Catch session.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, user, now, active=False)
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Snowflake Catch unavailable for this player.")
            if row["status"] == "active":
                row, events = self._settle(
                    con, row, now, _elapsed(row, now), int(row["basket_x"]))
                return self._snapshot(row, now, events=events)
            return self._snapshot(row, now)

    def control(self, user: int, session_id: str, action: str,
                *, now: datetime | None = None):
        if not SESSION_RE.fullmatch(session_id) or action not in (
                "pause", "resume", "finish"):
            raise ValueError("Invalid Snowflake Catch control.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=action == "resume")
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Snowflake Catch unavailable for this player.")
            events = []
            if row["status"] == "active":
                row, events = self._settle(
                    con, row, now, _elapsed(row, now), int(row["basket_x"]))
            if row["status"] == "finished":
                return self._snapshot(row, now, events=events)
            if row["day"] != day:
                raise ValueError("This game belongs to a previous event day.")
            status = ("finished" if action == "finish" else
                      "active" if action == "resume" else "paused")
            if status != row["status"]:
                ms, stamp = _elapsed(row, now), _timestamp(now)
                con.execute(
                    "UPDATE web_arcade_catch_sessions SET status=?,elapsed_ms=?,"
                    "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=?,"
                    "last_feedback=? WHERE session_id=?",
                    (status, ms, stamp if status == "active" else None,
                     stamp if status == "finished" else None, stamp,
                     {"pause": "Your basket is saved.",
                      "resume": "Snow is falling! Move the basket.",
                      "finish": "You left the snowflake storm early."}[action],
                     session_id))
                row = self._row(con, user, session_id)
            return self._snapshot(row, now, events=events)

    def update(self, user: int, session_id: str, action_seq: int, x: int,
               interaction_id: str, *, now: datetime | None = None):
        if (not SESSION_RE.fullmatch(session_id) or type(action_seq) is not int
                or not 0 <= action_seq < MAX_ACTIONS
                or type(x) is not int or not BASKET_MIN <= x <= BASKET_MAX
                or not isinstance(interaction_id, str)
                or not 1 <= len(interaction_id) <= 128):
            raise ValueError("Invalid Snowflake Catch basket update.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            replay = con.execute(
                "SELECT * FROM web_arcade_catch_actions WHERE interaction_id=?",
                (interaction_id,)).fetchone()
            if replay:
                if (replay["session_id"] != session_id or
                        replay["season_key"] != self.season or
                        replay["player_id"] != user or
                        replay["action_seq"] != action_seq or replay["x"] != x):
                    raise ValueError("Catch action key belongs to another request.")
                row = self._row(con, user, session_id)
                return self._snapshot(row, now,
                                      events=json.loads(replay["settled_events_json"]),
                                      repeated=True)
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Snowflake Catch unavailable for this player.")
            if row["status"] != "active" or row["day"] != day:
                raise ValueError("Snowflake Catch is paused, finished or from an earlier day.")
            if action_seq != row["actions"]:
                raise ValueError("Out-of-order Snowflake Catch update. Refresh game.")
            elapsed = _elapsed(row, now)
            old_x = int(row["basket_x"])
            interval = elapsed - int(row["last_position_elapsed"])
            if (abs(x - old_x) > max(8, interval * MAX_SPEED_PX_MS + 8)):
                raise ValueError("Basket cannot move that far in the available time.")
            if interval < 85 and action_seq > 0:
                raise ValueError("Basket input is too frequent; wait for next frame.")
            row, events = self._settle(con, row, now, elapsed, x)
            stamp = _timestamp(now)
            con.execute(
                "UPDATE web_arcade_catch_sessions SET actions=actions+1 "
                "WHERE session_id=?", (session_id,))
            con.execute(
                "INSERT INTO web_arcade_catch_actions "
                "(interaction_id,session_id,season_key,player_id,action_seq,"
                "x,settled_events_json,score_after,created_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (interaction_id, session_id, self.season, user, action_seq,
                 x, json.dumps(events, separators=(",", ":")), row["score"], stamp))
            row = self._row(con, user, session_id)
            return self._snapshot(row, now, events=events)

    def record(self, user: int, *, now: datetime | None = None):
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            self._eligible(con, user, now, active=False)
            r = con.execute(
                "SELECT COALESCE(MAX(score),0),COUNT(*),"
                "COALESCE(MAX(best_combo),0) FROM web_arcade_catch_sessions "
                "WHERE season_key=? AND player_id=? AND status='finished'",
                (self.season, user)).fetchone()
            return {"personal_best": int(r[0]), "finished_runs": int(r[1]),
                    "best_combo": int(r[2]), "practice": True,
                    "competitive": False}
