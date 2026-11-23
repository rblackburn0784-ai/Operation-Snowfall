"""v2.9.9a: server-authoritative, web-only Snowball Target Gallery.

The complete 45-second skill game uses deterministic server-issued target
trajectories, bounded ammunition, audited/idempotent shots, and time validation.
Scores are PRACTICE HONOURS, never event points, Discord arcade results or prizes.
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

DURATION_MS = 45_000
AMMO = 32
WIDTH = 640
HEIGHT = 360
SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
MIN_SHOT_MS = 145

# Independent from the classic Discord five-game tables and v2.9.9 drills.
GALLERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_arcade_gallery_sessions (
 session_id TEXT PRIMARY KEY,
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
 status TEXT NOT NULL CHECK(status IN ('active','paused','finished')),
 elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK(elapsed_ms BETWEEN 0 AND 45000),
 resumed_at_utc TEXT,
 schedule_json TEXT NOT NULL,
 claimed_json TEXT NOT NULL DEFAULT '[]',
 shots_used INTEGER NOT NULL DEFAULT 0 CHECK(shots_used BETWEEN 0 AND 32),
 hits INTEGER NOT NULL DEFAULT 0 CHECK(hits BETWEEN 0 AND 32),
 misses INTEGER NOT NULL DEFAULT 0 CHECK(misses BETWEEN 0 AND 32),
 decoys INTEGER NOT NULL DEFAULT 0 CHECK(decoys BETWEEN 0 AND 32),
 combo INTEGER NOT NULL DEFAULT 0 CHECK(combo BETWEEN 0 AND 32),
 best_combo INTEGER NOT NULL DEFAULT 0 CHECK(best_combo BETWEEN 0 AND 32),
 score INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
 last_shot_at_utc TEXT,
 last_feedback TEXT NOT NULL DEFAULT '',
 started_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 finished_at_utc TEXT,
 FOREIGN KEY(season_key,player_id) REFERENCES players(season_key,discord_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_gallery_active
 ON web_arcade_gallery_sessions(season_key,player_id,day)
 WHERE status IN ('active','paused');
CREATE INDEX IF NOT EXISTS idx_web_gallery_results
 ON web_arcade_gallery_sessions(season_key,player_id,status,score);
CREATE TABLE IF NOT EXISTS web_arcade_gallery_shots (
 interaction_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES web_arcade_gallery_sessions(session_id),
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 shot_index INTEGER NOT NULL CHECK(shot_index BETWEEN 0 AND 31),
 x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 640),
 y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 360),
 outcome TEXT NOT NULL CHECK(outcome IN ('hit','gold','decoy','miss')),
 target_id INTEGER,
 score_after INTEGER NOT NULL CHECK(score_after BETWEEN 0 AND 100),
 elapsed_ms INTEGER NOT NULL CHECK(elapsed_ms BETWEEN 0 AND 45000),
 feedback TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(session_id,shot_index)
);
"""


def install_gallery_schema(connection) -> None:
    """Explicit additive, idempotent QA migration; never on web app startup."""
    for query in GALLERY_SCHEMA.strip().split(";"):
        if query.strip():
            connection.execute(query.strip())


def schedule_targets(rng=None) -> list[dict]:
    """Full visual schedule; award decisions always recalculated server-side."""
    rng = rng or secrets.SystemRandom()
    targets = []
    for i in range(43):
        starts = 450 + i * 1020
        wave = min(3, starts // 15000 + 1)
        kind = ("decoy" if i > 3 and i % 8 == 5
                else "gold" if i > 1 and i % 7 == 3 else "normal")
        length = (2100, 1730, 1450)[wave - 1]
        if kind == "gold":
            length -= 230
        targets.append({
            "id": i, "kind": kind, "wave": wave, "start": starts,
            "life": length, "x0": rng.randrange(155, 491),
            "y": rng.choice((126, 181, 243, 285)),
            "amp": rng.randrange(38, 110),
            "rate": round(rng.uniform(1.65 + wave * .35, 2.45 + wave * .55), 5),
            "phase": round(rng.uniform(0, math.tau), 5),
            "radius": 28 if kind == "normal" else 25 if kind == "gold" else 30,
        })
    return targets


def target_position(target: dict, elapsed_ms: int) -> tuple[float, float]:
    dt = (elapsed_ms - target["start"]) / 1000
    return (target["x0"] + target["amp"] * math.sin(target["phase"] + dt * target["rate"]),
            target["y"])


def find_target(schedule: list[dict], claimed: set[int], elapsed_ms: int,
                x: int, y: int) -> dict | None:
    """Closest currently visible, unclaimed target at authoritative shot time."""
    candidates = []
    # 120ms lookback absorbs latency; no client-reported shot timestamp accepted.
    for t in schedule:
        if t["id"] in claimed:
            continue
        for lag in (0, 60, 120):
            moment = elapsed_ms - lag
            if not (t["start"] <= moment < t["start"] + t["life"]):
                continue
            tx, ty = target_position(t, moment)
            distance = math.hypot(x - tx, y - ty)
            if distance <= t["radius"] + 6:
                candidates.append((distance / t["radius"], t["id"], t))
    return min(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def _elapsed(row, now: datetime) -> int:
    base = int(row["elapsed_ms"])
    if row["status"] == "active" and row["resumed_at_utc"]:
        origin = datetime.fromisoformat(row["resumed_at_utc"]).astimezone(timezone.utc)
        base += max(0, round((now - origin).total_seconds() * 1000))
    return min(DURATION_MS, base)


class GalleryEngine:
    """Transactional preview gallery. Never calls the Discord game write engine."""

    def __init__(self, store: Store, season: str):
        self.store, self.season = store, season

    def _eligible(self, con, user: int, now: datetime, *, active: bool):
        return SocialArcadeEngine._eligible(con, self.season, user, now, active=active)[1]

    def _row(self, con, user: int, session_id: str):
        return con.execute(
            "SELECT * FROM web_arcade_gallery_sessions "
            "WHERE session_id=? AND season_key=? AND player_id=?",
            (session_id, self.season, user)).fetchone()

    @staticmethod
    def _sync(con, row, now: datetime):
        if row["status"] == "active" and _elapsed(row, now) >= DURATION_MS:
            con.execute(
                "UPDATE web_arcade_gallery_sessions "
                "SET status='finished',elapsed_ms=?,resumed_at_utc=NULL,"
                "finished_at_utc=?,updated_at_utc=?,last_feedback=? WHERE session_id=?",
                (DURATION_MS, _timestamp(now), _timestamp(now),
                 "Time! The gallery is closed.", row["session_id"]))
            return con.execute(
                "SELECT * FROM web_arcade_gallery_sessions WHERE session_id=?",
                (row["session_id"],)).fetchone()
        return row

    @staticmethod
    def _snapshot(row, now: datetime, *, last_event: dict | None = None,
                  repeated: bool = False):
        score = int(row["score"])
        used = int(row["shots_used"])
        hits = int(row["hits"])
        return {
            "session_id": row["session_id"], "mode": "gallery",
            "title": "Snowball Target Gallery", "day": int(row["day"]),
            "status": row["status"], "practice": True, "competitive": False,
            "duration_ms": DURATION_MS, "elapsed_ms": _elapsed(row, now),
            "server_epoch_ms": round(now.timestamp() * 1000),
            "schedule": json.loads(row["schedule_json"]),
            "claimed": json.loads(row["claimed_json"]),
            "ammo": AMMO - used, "shots_used": used, "hits": hits,
            "misses": int(row["misses"]), "decoys": int(row["decoys"]),
            "combo": int(row["combo"]), "best_combo": int(row["best_combo"]),
            "accuracy": round(100 * hits / used) if used else 0,
            "score": score, "feedback": row["last_feedback"],
            "last_event": last_event, "repeated": repeated,
            "result": ("Sharpshooter!" if score >= 85 else
                       "Excellent aim!" if score >= 60 else
                       "Good practice!" if score >= 35 else "Keep training!")
                      if row["status"] == "finished" else None,
            "note": "Unranked QA practice. No Discord starts, event points or prizes.",
        }

    def start(self, user: int, *, now: datetime | None = None):
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            row = con.execute(
                "SELECT * FROM web_arcade_gallery_sessions WHERE season_key=? AND "
                "player_id=? AND day=? AND status IN ('active','paused')",
                (self.season, user, day)).fetchone()
            if row:
                row = self._sync(con, row, now)
                if row["status"] != "finished":
                    return self._snapshot(row, now)
            sid = secrets.token_hex(16)
            stamp = _timestamp(now)
            con.execute(
                "INSERT INTO web_arcade_gallery_sessions "
                "(session_id,season_key,player_id,day,status,elapsed_ms,resumed_at_utc,"
                "schedule_json,started_at_utc,updated_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (sid, self.season, user, day, "paused", 0, None,
                 json.dumps(schedule_targets(), separators=(",", ":")), stamp, stamp))
            return self._snapshot(self._row(con, user, sid), now)

    def session(self, user: int, session_id: str, *, now: datetime | None = None):
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("Invalid gallery session.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, user, now, active=False)
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Gallery session unavailable for this player.")
            return self._snapshot(self._sync(con, row, now), now)

    def control(self, user: int, session_id: str, action: str, *,
                now: datetime | None = None):
        if not SESSION_RE.fullmatch(session_id) or action not in ("pause", "resume", "finish"):
            raise ValueError("Invalid gallery control.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=action == "resume")
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Gallery session unavailable for this player.")
            row = self._sync(con, row, now)
            if row["status"] == "finished":
                return self._snapshot(row, now)
            if day != row["day"]:
                raise ValueError("This gallery belongs to an earlier event day.")
            elapsed = _elapsed(row, now)
            status = ("finished" if action == "finish" else
                      "active" if action == "resume" else "paused")
            if row["status"] != status:
                stamp = _timestamp(now)
                con.execute(
                    "UPDATE web_arcade_gallery_sessions SET status=?,elapsed_ms=?,"
                    "resumed_at_utc=?,updated_at_utc=?,finished_at_utc=?,last_feedback=? "
                    "WHERE session_id=?",
                    (status, elapsed, stamp if status == "active" else None, stamp,
                     stamp if status == "finished" else None,
                     {"finish": "Practice finished.",
                      "pause": "Paused and safely saved.",
                      "resume": "Next wave incoming!"}[action], session_id))
                row = self._row(con, user, session_id)
            return self._snapshot(row, now)

    def shoot(self, user: int, session_id: str, shot_index: int, x: int, y: int,
              interaction_id: str, *, now: datetime | None = None):
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("Invalid gallery session.")
        if (type(shot_index) is not int or not 0 <= shot_index < AMMO or
                type(x) is not int or not 0 <= x <= WIDTH or
                type(y) is not int or not 0 <= y <= HEIGHT or
                not 1 <= len(interaction_id) <= 128):
            raise ValueError("Invalid gallery shot.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            old = con.execute(
                "SELECT * FROM web_arcade_gallery_shots WHERE interaction_id=?",
                (interaction_id,)).fetchone()
            if old:
                if (old["session_id"] != session_id or old["season_key"] != self.season
                        or old["player_id"] != user or old["shot_index"] != shot_index
                        or old["x"] != x or old["y"] != y):
                    raise ValueError("Gallery shot idempotency key belongs to another action.")
                row = self._row(con, user, session_id)
                return self._snapshot(row, now, repeated=True, last_event={
                    "outcome": old["outcome"], "target_id": old["target_id"],
                    "feedback": old["feedback"], "score_after": old["score_after"],
                    "shot_index": shot_index})
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Gallery session unavailable for this player.")
            row = self._sync(con, row, now)
            if day != row["day"] or row["status"] != "active":
                raise ValueError("Gallery is paused, finished, or from a previous event day.")
            if int(row["shots_used"]) != shot_index:
                raise ValueError("Out-of-order gallery shot. Refresh the game.")
            if row["last_shot_at_utc"]:
                previous = datetime.fromisoformat(row["last_shot_at_utc"]).astimezone(timezone.utc)
                if (now - previous).total_seconds() * 1000 < MIN_SHOT_MS:
                    raise ValueError("Slow down between snowball throws.")
            elapsed = _elapsed(row, now)
            claimed = set(json.loads(row["claimed_json"]))
            target = find_target(json.loads(row["schedule_json"]), claimed, elapsed, x, y)
            kind = target["kind"] if target else "miss"
            outcome = "hit" if kind == "normal" else kind
            hits = int(row["hits"]) + (kind in ("normal", "gold"))
            misses = int(row["misses"]) + (kind == "miss")
            decoys = int(row["decoys"]) + (kind == "decoy")
            combo = int(row["combo"]) + 1 if kind in ("normal", "gold") else 0
            best = max(int(row["best_combo"]), combo)
            bonus = (min(5, combo // 3) if kind in ("normal", "gold") else 0)
            earned = {"normal": 7, "gold": 15, "decoy": -9, "miss": -2}[kind] + bonus
            score = max(0, min(100, int(row["score"]) + earned))
            feedback = {
                "normal": f"Clean hit! +{earned} · {combo} streak",
                "gold": f"GOLDEN TARGET! +{earned} · {combo} streak",
                "decoy": "Careful! That was a decoy. −9",
                "miss": "Snowball missed. −2",
            }[kind]
            if target:
                claimed.add(target["id"])
            used = shot_index + 1
            status = "finished" if used >= AMMO else "active"
            stamp = _timestamp(now)
            con.execute(
                "UPDATE web_arcade_gallery_sessions SET shots_used=?,hits=?,misses=?,"
                "decoys=?,combo=?,best_combo=?,score=?,claimed_json=?,"
                "last_shot_at_utc=?,last_feedback=?,status=?,elapsed_ms=?,"
                "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=? WHERE session_id=?",
                (used, hits, misses, decoys, combo, best, score,
                 json.dumps(sorted(claimed)), stamp, feedback, status,
                 elapsed if status == "finished" else int(row["elapsed_ms"]),
                 None if status == "finished" else row["resumed_at_utc"],
                 stamp if status == "finished" else None, stamp, session_id))
            con.execute(
                "INSERT INTO web_arcade_gallery_shots "
                "(interaction_id,session_id,season_key,player_id,shot_index,"
                "x,y,outcome,target_id,score_after,elapsed_ms,feedback,created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (interaction_id, session_id, self.season, user, shot_index,
                 x, y, outcome, target["id"] if target else None, score,
                 elapsed, feedback, stamp))
            updated = self._row(con, user, session_id)
            return self._snapshot(updated, now, last_event={
                "outcome": outcome, "target_id": target["id"] if target else None,
                "feedback": feedback, "score_after": score, "shot_index": shot_index})

    def record(self, user: int, *, now: datetime | None = None):
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            self._eligible(con, user, now, active=False)
            row = con.execute(
                "SELECT COALESCE(MAX(score),0),COUNT(*),COALESCE(MAX(best_combo),0) "
                "FROM web_arcade_gallery_sessions WHERE season_key=? AND player_id=? "
                "AND status='finished'", (self.season, user)).fetchone()
            return {"personal_best": int(row[0]), "finished_runs": int(row[1]),
                    "best_combo": int(row[2]), "practice": True,
                    "competitive": False}
