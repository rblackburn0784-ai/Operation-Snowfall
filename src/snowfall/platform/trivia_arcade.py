"""v2.9.9e — Christmas Trivia: real timed, server-scored web arcade.

Five challenges per level across three festive levels: pick a present, spot
true/false, and arrange shuffled letters. The server owns the question bank,
solutions, expiry clock, scoring and replay ledger. All output is strictly
unranked QA practice; classic Discord arcade and rewards are untouched.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import random
import re
import secrets

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.social_arcade import SocialArcadeEngine

SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_QUESTIONS = 15
LEVEL_TITLES = ("Snowy Warmup", "Workshop Rush", "North Pole Finale")
QUESTION_MS = (16_000, 14_000, 12_000)
TOTAL_MS = 210_000
PATTERN = ("gift", "gift", "truefalse", "gift", "scramble")
ANSWER_LIMIT = 64

# Question bank is backend-only. No /static/ file contains solutions.
# Each entry: identifier, kind, question/clue, options (for gifts), answer,
# short explanation shown AFTER the player submits or times out.
BANK = (
    (
        ("e1", "gift", "Which animal traditionally pulls Santa's sleigh?",
         ("Reindeer", "Penguins", "Polar bears", "Horses"), "Reindeer",
         "Santa's team of reindeer pulls his sleigh in the familiar stories."),
        ("e2", "gift", "What colour are ripe holly berries?",
         ("Red", "Blue", "Purple", "Orange"), "Red",
         "The familiar evergreen holly has bright red berries."),
        ("e3", "gift", "What do people traditionally hang on a Christmas tree?",
         ("Decorations", "Umbrellas", "Sunglasses", "Sandcastles"), "Decorations",
         "Baubles, lights and ornaments are popular Christmas-tree decorations."),
        ("e4", "gift", "What is usually left out for Santa in a British Christmas tradition?",
         ("A mince pie", "A curry", "A bowl of noodles", "A pancake"), "A mince pie",
         "Many families leave a mince pie and a drink for Father Christmas."),
        ("e5", "gift", "Which month contains Christmas Day?",
         ("December", "November", "January", "October"), "December",
         "Christmas Day is celebrated on 25 December."),
        ("e6", "truefalse", "A traditional snowman is commonly built from snow.",
         (), "True", "Snow is the classic material used to build a snowman."),
        ("e7", "truefalse", "Christmas Day falls on 25 November.",
         (), "False", "Christmas Day falls on 25 December."),
        ("e8", "truefalse", "A Christmas cracker often contains a paper hat.",
         (), "True", "Traditional Christmas crackers often include paper hats."),
        ("e9", "scramble", "Unscramble this festive decoration.",
         (), "TINSEL", "Tinsel is a sparkling decoration used at Christmas."),
        ("e10", "scramble", "Unscramble this Christmas plant.",
         (), "HOLLY", "Holly is an evergreen plant associated with Christmas."),
        ("e11", "scramble", "Unscramble this festive song type.",
         (), "CAROL", "Carols are songs associated with Christmas."),
    ),
    (
        ("m1", "gift", "Who wrote the novella A Christmas Carol?",
         ("Charles Dickens", "Jane Austen", "Jules Verne", "Lewis Carroll"),
         "Charles Dickens", "Charles Dickens published A Christmas Carol in 1843."),
        ("m2", "gift", "Which ballet features the Sugar Plum Fairy?",
         ("The Nutcracker", "Swan Lake", "Giselle", "Coppélia"),
         "The Nutcracker", "The Sugar Plum Fairy appears in The Nutcracker."),
        ("m3", "gift", "Which plant is traditionally associated with a kiss at Christmas?",
         ("Mistletoe", "Ivy", "Lavender", "Heather"), "Mistletoe",
         "Mistletoe has a long tradition of Christmas kissing."),
        ("m4", "gift", "Which country is often credited with popularising decorated Christmas trees?",
         ("Germany", "Brazil", "Egypt", "Australia"), "Germany",
         "Decorated Christmas trees are widely associated with German traditions."),
        ("m5", "gift", "Which Charles Dickens character famously says 'Bah! Humbug!'?",
         ("Ebenezer Scrooge", "Oliver Twist", "Fagin", "Mr Pickwick"),
         "Ebenezer Scrooge", "Scrooge is the miser who changes in A Christmas Carol."),
        ("m6", "truefalse", "The Nutcracker was composed by Pyotr Ilyich Tchaikovsky.",
         (), "True", "Tchaikovsky wrote the music for The Nutcracker."),
        ("m7", "truefalse", "Boxing Day is observed on 26 December in the UK.",
         (), "True", "Boxing Day falls on 26 December."),
        ("m8", "truefalse", "The Ghost of Christmas Yet to Come appears first in A Christmas Carol.",
         (), "False", "The Ghost of Christmas Past appears before the other two spirits."),
        ("m9", "scramble", "Unscramble this Christmas transport.",
         (), "SLEIGH", "Santa is often depicted travelling by sleigh."),
        ("m10", "scramble", "Unscramble this evergreen decoration.",
         (), "WREATH", "Wreaths are commonly hung on doors over Christmas."),
        ("m11", "scramble", "Unscramble this gift-wrapping accessory.",
         (), "RIBBON", "Ribbon is often used to decorate wrapped presents."),
    ),
    (
        ("h1", "gift", "Which reindeer is traditionally said to have a glowing red nose?",
         ("Rudolph", "Dasher", "Dancer", "Vixen"), "Rudolph",
         "Rudolph's famous glowing red nose is central to the story."),
        ("h2", "gift", "How many ghosts of Christmas visit Scrooge after Marley warns him?",
         ("Three", "Two", "Four", "Five"), "Three",
         "The three spirits represent Christmas Past, Present and Yet to Come."),
        ("h3", "gift", "What is the name of the family in Home Alone?",
         ("McCallister", "Griswold", "Banks", "Parker"), "McCallister",
         "Kevin McCallister is the central character in Home Alone."),
        ("h4", "gift", "Which song begins with the words 'Dashing through the snow'?",
         ("Jingle Bells", "Silent Night", "Deck the Halls", "White Christmas"),
         "Jingle Bells", "Jingle Bells opens with 'Dashing through the snow'."),
        ("h5", "gift", "In The Twelve Days of Christmas, what appears on day five?",
         ("Five gold rings", "Five turtle doves", "Five drummers", "Five pears"),
         "Five gold rings", "The fifth day's gift is five gold rings."),
        ("h6", "truefalse", "The story A Christmas Carol was published in the 1800s.",
         (), "True", "It was published in 1843."),
        ("h7", "truefalse", "In the classic song, the partridge is in a cherry tree.",
         (), "False", "The partridge sits in a pear tree."),
        ("h8", "truefalse", "Rudolph was one of the original eight reindeer in the 1823 poem.",
         (), "False", "Rudolph was introduced much later, in 1939."),
        ("h9", "scramble", "Unscramble the hanging gift-holder by the fireplace.",
         (), "STOCKING", "Christmas stockings are often hung by fireplaces."),
        ("h10", "scramble", "Unscramble Santa's traditional entrance.",
         (), "CHIMNEY", "In many stories Santa enters through the chimney."),
        ("h11", "scramble", "Unscramble this snowy winter figure.",
         (), "SNOWMAN", "A snowman is made from packed snow."),
    ),
)

TRIVIA_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_arcade_trivia_sessions (
 session_id TEXT PRIMARY KEY,
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
 status TEXT NOT NULL CHECK(status IN ('paused','active','finished')),
 elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK(elapsed_ms BETWEEN 0 AND 210000),
 resumed_at_utc TEXT,
 deck_json TEXT NOT NULL,
 step INTEGER NOT NULL DEFAULT 0 CHECK(step BETWEEN 0 AND 15),
 question_started_ms INTEGER NOT NULL DEFAULT 0 CHECK(question_started_ms BETWEEN 0 AND 210000),
 history_json TEXT NOT NULL DEFAULT '[]',
 correct INTEGER NOT NULL DEFAULT 0 CHECK(correct BETWEEN 0 AND 15),
 wrong INTEGER NOT NULL DEFAULT 0 CHECK(wrong BETWEEN 0 AND 15),
 timeouts INTEGER NOT NULL DEFAULT 0 CHECK(timeouts BETWEEN 0 AND 15),
 streak INTEGER NOT NULL DEFAULT 0 CHECK(streak BETWEEN 0 AND 15),
 best_streak INTEGER NOT NULL DEFAULT 0 CHECK(best_streak BETWEEN 0 AND 15),
 score INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
 feedback TEXT NOT NULL DEFAULT '',
 started_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 finished_at_utc TEXT,
 FOREIGN KEY(season_key,player_id) REFERENCES players(season_key,discord_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_trivia_active
 ON web_arcade_trivia_sessions(season_key,player_id,day)
 WHERE status IN ('paused','active');
CREATE INDEX IF NOT EXISTS idx_web_trivia_records
 ON web_arcade_trivia_sessions(season_key,player_id,status,score);
CREATE TABLE IF NOT EXISTS web_arcade_trivia_answers (
 interaction_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES web_arcade_trivia_sessions(session_id),
 season_key TEXT NOT NULL,
 player_id BIGINT NOT NULL,
 step INTEGER NOT NULL CHECK(step BETWEEN 0 AND 14),
 answer TEXT NOT NULL,
 verdict TEXT NOT NULL CHECK(verdict IN ('correct','wrong')),
 points INTEGER NOT NULL CHECK(points BETWEEN 0 AND 10),
 created_at_utc TEXT NOT NULL,
 UNIQUE(session_id,step)
);
"""


def install_trivia_schema(con) -> None:
    """Explicit additive QA migration only; never run on live web startup."""
    for statement in TRIVIA_SCHEMA.strip().split(";"):
        if statement.strip():
            con.execute(statement.strip())


def _make_deck(rng=None) -> list[dict]:
    rng = rng or secrets.SystemRandom()
    deck: list[dict] = []
    for tier, entries in enumerate(BANK):
        selected: dict[str, list] = {}
        for kind in ("gift", "truefalse", "scramble"):
            pool = [entry for entry in entries if entry[1] == kind]
            wanted = {"gift": 3, "truefalse": 1, "scramble": 1}[kind]
            selected[kind] = rng.sample(pool, wanted)
        for kind in PATTERN:
            identifier, _, prompt, variants, correct, explanation = selected[kind].pop()
            options = list(variants) if kind == "gift" else (
                ["True", "False"] if kind == "truefalse" else []
            )
            if kind == "gift":
                rng.shuffle(options)
            tiles = list(correct) if kind == "scramble" else []
            if tiles:
                for _ in range(8):
                    rng.shuffle(tiles)
                    if "".join(tiles) != correct:
                        break
                if "".join(tiles) == correct:
                    tiles = tiles[1:] + tiles[:1]
            deck.append({
                "id": identifier, "kind": kind, "prompt": prompt,
                "options": options, "tiles": tiles, "correct": correct,
                "explanation": explanation, "level": tier + 1,
                "limit_ms": QUESTION_MS[tier],
            })
    assert len(deck) == MAX_QUESTIONS
    return deck


def _elapsed(row, now: datetime) -> int:
    ms = int(row["elapsed_ms"])
    if row["status"] == "active" and row["resumed_at_utc"]:
        previous = datetime.fromisoformat(row["resumed_at_utc"]).astimezone(timezone.utc)
        ms += max(0, round((now - previous).total_seconds() * 1000))
    return min(TOTAL_MS, ms)


def _public_question(raw: dict) -> dict:
    """Keep all correct answers/explanations strictly server-side until resolved."""
    return {
        "id": raw["id"], "kind": raw["kind"], "prompt": raw["prompt"],
        "options": raw["options"], "tiles": raw["tiles"],
        "level": raw["level"], "limit_ms": raw["limit_ms"],
        "level_name": LEVEL_TITLES[raw["level"] - 1],
    }


class ChristmasTriviaEngine:
    def __init__(self, store: Store, season: str, rng=None):
        self.store, self.season = store, season
        self.rng = rng or secrets.SystemRandom()

    def _eligible(self, con, user: int, now: datetime, *, active=False):
        return SocialArcadeEngine._eligible(
            con, self.season, user, now, active=active)[1]

    def _row(self, con, user: int, session_id: str):
        return con.execute(
            "SELECT * FROM web_arcade_trivia_sessions "
            "WHERE session_id=? AND season_key=? AND player_id=?",
            (session_id, self.season, user)).fetchone()

    @staticmethod
    def _snapshot(row, now: datetime, *, repeated=False, last_answer=None) -> dict:
        deck = json.loads(row["deck_json"])
        step = int(row["step"])
        history = json.loads(row["history_json"])
        elapsed = _elapsed(row, now)
        current = deck[step] if step < MAX_QUESTIONS else None
        remaining = (
            max(0, int(row["question_started_ms"]) + current["limit_ms"] - elapsed)
            if current else 0
        )
        return {
            "session_id": row["session_id"], "mode": "trivia",
            "title": "Christmas Trivia", "day": int(row["day"]),
            "status": row["status"], "practice": True, "competitive": False,
            "step": step, "total_questions": MAX_QUESTIONS,
            "round": min(3, step // 5 + 1), "total_rounds": 3,
            "duration_ms": TOTAL_MS, "elapsed_ms": elapsed,
            "question": _public_question(current) if current else None,
            "question_remaining_ms": remaining,
            "correct": int(row["correct"]), "wrong": int(row["wrong"]),
            "timeouts": int(row["timeouts"]), "streak": int(row["streak"]),
            "best_streak": int(row["best_streak"]), "score": int(row["score"]),
            "feedback": row["feedback"], "last_answer": last_answer or (
                history[-1] if history else None),
            "history": history if row["status"] == "finished" else [],
            "repeated": repeated,
            "result": (
                "NORTH POLE QUIZ CHAMPION!" if row["score"] >= 85 else
                "FESTIVE MASTER!" if row["score"] >= 55 else
                "KEEP THE CHRISTMAS SPIRIT!"
            ) if row["status"] == "finished" else None,
            "note": "Unranked QA practice only — no official arcade starts or prizes.",
        }

    @staticmethod
    def _advance(con, row, now: datetime):
        """Resolve every question whose deadline passed; no client 'skip' authority."""
        if row["status"] != "active":
            return row
        elapsed = _elapsed(row, now)
        deck = json.loads(row["deck_json"])
        history = json.loads(row["history_json"])
        step = int(row["step"])
        start = int(row["question_started_ms"])
        timeout_count = int(row["timeouts"])
        feedback = row["feedback"]
        updated = False
        while step < MAX_QUESTIONS and elapsed >= start + deck[step]["limit_ms"]:
            question = deck[step]
            history.append({
                "step": step, "kind": question["kind"], "prompt": question["prompt"],
                "selected": None, "answer": question["correct"],
                "verdict": "timeout", "points": 0,
                "explanation": question["explanation"],
            })
            timeout_count += 1
            feedback = "Time's up! "+question["correct"]+" was the answer."
            start += question["limit_ms"]
            step += 1
            updated = True
        if not updated:
            return row
        status = "finished" if step == MAX_QUESTIONS else "active"
        stamp = _timestamp(now)
        con.execute(
            "UPDATE web_arcade_trivia_sessions SET step=?,question_started_ms=?,"
            "history_json=?,timeouts=?,streak=0,feedback=?,status=?,"
            "elapsed_ms=?,resumed_at_utc=?,finished_at_utc=?,updated_at_utc=? "
            "WHERE session_id=?",
            (step, start, json.dumps(history, separators=(",", ":")),
             timeout_count, feedback, status,
             elapsed if status == "finished" else int(row["elapsed_ms"]),
             None if status == "finished" else row["resumed_at_utc"],
             stamp if status == "finished" else None, stamp, row["session_id"]))
        return con.execute(
            "SELECT * FROM web_arcade_trivia_sessions WHERE session_id=?",
            (row["session_id"],)).fetchone()

    def start(self, user: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            row = con.execute(
                "SELECT * FROM web_arcade_trivia_sessions WHERE season_key=? "
                "AND player_id=? AND day=? AND status IN ('paused','active')",
                (self.season, user, day)).fetchone()
            if row is not None:
                row = self._advance(con, row, now)
                if row["status"] != "finished":
                    return self._snapshot(row, now)
            sid, stamp = secrets.token_hex(16), _timestamp(now)
            con.execute(
                "INSERT INTO web_arcade_trivia_sessions "
                "(session_id,season_key,player_id,day,status,deck_json,"
                "started_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                (sid, self.season, user, day, "paused",
                 json.dumps(_make_deck(self.rng), separators=(",", ":")),
                 stamp, stamp))
            return self._snapshot(self._row(con, user, sid), now)

    def session(self, user: int, session_id: str, *,
                now: datetime | None = None) -> dict:
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("Invalid Christmas Trivia session.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, user, now, active=False)
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Christmas Trivia session unavailable for this player.")
            return self._snapshot(self._advance(con, row, now), now)

    def control(self, user: int, session_id: str, action: str,
                *, now: datetime | None = None) -> dict:
        if not SESSION_RE.fullmatch(session_id) or action not in (
                "pause", "resume", "finish"):
            raise ValueError("Invalid Christmas Trivia control.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=action == "resume")
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Christmas Trivia session unavailable for this player.")
            row = self._advance(con, row, now)
            if row["status"] == "finished":
                return self._snapshot(row, now)
            if row["day"] != day:
                raise ValueError("Trivia belongs to a previous event day.")
            status = ("finished" if action == "finish" else
                      "active" if action == "resume" else "paused")
            if row["status"] != status:
                stamp = _timestamp(now)
                elapsed = _elapsed(row, now)
                con.execute(
                    "UPDATE web_arcade_trivia_sessions SET status=?,elapsed_ms=?,"
                    "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=?,"
                    "feedback=? WHERE session_id=?",
                    (status, elapsed, stamp if status == "active" else None,
                     stamp if status == "finished" else None, stamp,
                     {"pause": "Trivia paused; your questions are saved.",
                      "resume": "Time to unwrap the next Christmas challenge!",
                      "finish": "Quiz ended early. Try again for a festive high score."}[action],
                     session_id))
                row = self._row(con, user, session_id)
            return self._snapshot(row, now)

    def answer(self, user: int, session_id: str, step: int, answer: str,
               interaction_id: str, *, now: datetime | None = None) -> dict:
        if (not SESSION_RE.fullmatch(session_id)
                or type(step) is not int or not 0 <= step < MAX_QUESTIONS
                or not isinstance(answer, str) or not 1 <= len(answer) <= ANSWER_LIMIT
                or not isinstance(interaction_id, str)
                or not 1 <= len(interaction_id) <= 128):
            raise ValueError("Invalid Christmas Trivia answer.")
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._eligible(con, user, now, active=True)
            replay = con.execute(
                "SELECT * FROM web_arcade_trivia_answers WHERE interaction_id=?",
                (interaction_id,)).fetchone()
            if replay:
                if (replay["session_id"] != session_id or
                        replay["season_key"] != self.season or
                        replay["player_id"] != user or
                        replay["step"] != step or replay["answer"] != answer):
                    raise ValueError("Trivia idempotency key belongs to another answer.")
                row = self._row(con, user, session_id)
                return self._snapshot(row, now, repeated=True)
            row = self._row(con, user, session_id)
            if row is None:
                raise ValueError("Christmas Trivia session unavailable for this player.")
            row = self._advance(con, row, now)
            if row["status"] != "active" or row["day"] != day:
                raise ValueError("Trivia is paused, finished, or from an earlier event day.")
            if step != row["step"]:
                raise ValueError("Trivia answer is out of order; refresh the question.")
            deck = json.loads(row["deck_json"])
            current = deck[step]
            value = answer.upper() if current["kind"] == "scramble" else answer
            if current["kind"] == "scramble":
                if (not value.isascii() or not value.isalpha()
                        or Counter(value) != Counter(current["tiles"])):
                    raise ValueError("Answer must use each available letter exactly once.")
            elif value not in current["options"]:
                raise ValueError("Select one of the offered answer cards.")
            elapsed = _elapsed(row, now)
            remaining = max(0, current["limit_ms"] - (
                elapsed - int(row["question_started_ms"])))
            is_correct = value == current["correct"]
            streak = int(row["streak"]) + 1 if is_correct else 0
            speed = (2 if remaining >= current["limit_ms"] * 2 // 3 else
                     1 if remaining >= current["limit_ms"] // 3 else 0)
            bonus = min(3, streak // 3) if is_correct else 0
            points = (5 + speed + bonus) if is_correct else 0
            score = min(100, int(row["score"]) + points)
            feedback = (
                f"Correct! +{points} points. " if is_correct else
                f"Not quite. It was {current['correct']}. "
            ) + current["explanation"]
            history = json.loads(row["history_json"])
            history.append({
                "step": step, "kind": current["kind"], "prompt": current["prompt"],
                "selected": value, "answer": current["correct"],
                "verdict": "correct" if is_correct else "wrong",
                "points": points, "explanation": current["explanation"],
            })
            next_step = step + 1
            done = next_step == MAX_QUESTIONS
            stamp = _timestamp(now)
            con.execute(
                "UPDATE web_arcade_trivia_sessions SET step=?,"
                "question_started_ms=?,history_json=?,correct=?,wrong=?,"
                "streak=?,best_streak=?,score=?,feedback=?,status=?,elapsed_ms=?,"
                "resumed_at_utc=?,finished_at_utc=?,updated_at_utc=? "
                "WHERE session_id=?",
                (next_step, elapsed, json.dumps(history, separators=(",", ":")),
                 int(row["correct"]) + is_correct, int(row["wrong"]) + (not is_correct),
                 streak, max(streak, int(row["best_streak"])), score,
                 feedback, "finished" if done else "active",
                 elapsed if done else int(row["elapsed_ms"]),
                 None if done else row["resumed_at_utc"],
                 stamp if done else None, stamp, session_id))
            con.execute(
                "INSERT INTO web_arcade_trivia_answers "
                "(interaction_id,session_id,season_key,player_id,step,answer,"
                "verdict,points,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (interaction_id, session_id, self.season, user, step,
                 answer, "correct" if is_correct else "wrong", points, stamp))
            row = self._row(con, user, session_id)
            return self._snapshot(row, now, last_answer=history[-1])

    def record(self, user: int, *, now: datetime | None = None) -> dict:
        now = as_utc(now or datetime.now(timezone.utc))
        with self.store.connect() as con:
            self._eligible(con, user, now, active=False)
            row = con.execute(
                "SELECT COALESCE(MAX(score),0),COUNT(*),"
                "COALESCE(MAX(best_streak),0),COALESCE(MAX(correct),0) "
                "FROM web_arcade_trivia_sessions WHERE season_key=? AND player_id=? "
                "AND status='finished'", (self.season, user)).fetchone()
            return {
                "personal_best": int(row[0]), "finished_runs": int(row[1]),
                "best_streak": int(row[2]), "best_correct": int(row[3]),
                "practice": True, "competitive": False,
            }
