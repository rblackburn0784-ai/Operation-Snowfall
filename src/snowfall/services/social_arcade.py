"""v0.2.7 five-game Winter Arcade and honorary social records.

Each game is interactive, deterministic after a securely randomised start,
and backed by a serialised, replay-safe SQLite transaction. Results are
display-only: never insert score_ledger, rewards, inventory or prize rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import secrets
from typing import Any

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.winter_fun import WinterFunEngine


class SocialArcadeError(ValueError):
    """Rejected arcade action without scoring, balance or award changes."""


@dataclass(frozen=True)
class GameSpec:
    key: str
    title: str
    icon: str
    description: str
    rounds: int
    award_name: str


GAMES: dict[str, GameSpec] = {
    "gallery": GameSpec(
        "gallery", "Snowball Target Gallery", "🎯",
        "Spot the correct target in five quick-fire shooting-gallery rounds.", 5,
        "Sharpshooter Ribbon"),
    "safe": GameSpec(
        "safe", "Frozen Safecracker", "🔐",
        "Solve three icy lock-dial clues to open the speakeasy safe.", 3,
        "Ice Vault Key"),
    "snowman": GameSpec(
        "snowman", "Snowman Builder", "☃️",
        "Follow four festive blueprints to assemble the best snowman.", 4,
        "Master Snow Sculptor"),
    "catch": GameSpec(
        "catch", "Snowflake Catch", "❄️",
        "Read the wind and catch five drifting snowflakes.", 5,
        "Blizzard Catcher"),
    "trivia": GameSpec(
        "trivia", "Christmas Trivia", "🎄",
        "Five multiple-choice festive questions with explanations.", 5,
        "Yule Quizmaster"),
}
DAILY_GAME_CAP = 3
STAMPS = {
    **{f"played_{key}": f"{spec.icon} {spec.title} Ticket"
       for key, spec in GAMES.items()},
    **{f"master_{key}": f"🏅 {spec.award_name}"
       for key, spec in GAMES.items()},
    "all_five": "🌟 Winter Arcade Grand Tour",
}
LANES = ("Left", "Centre", "Right")

# All questions, clues and explanations are original, public-domain factual
# holiday trivia or original in-world winter fiction.
GALLERY = (
    ("the silver bell", ("Silver Bell", "Cocoa Tin", "Candy Cane"), "Silver Bell"),
    ("the candy-striped pole", ("Toy Train", "Candy Cane", "Snowman"), "Candy Cane"),
    ("the little tin locomotive", ("Toy Train", "Snow Globe", "Woollen Hat"), "Toy Train"),
    ("the frosted glass globe", ("Snow Globe", "Silver Bell", "Cocoa Tin"), "Snow Globe"),
    ("the red winter mitten", ("Woollen Mitten", "Toy Train", "Snow Globe"), "Woollen Mitten"),
    ("the golden Christmas star", ("Golden Star", "Candy Cane", "Snowman"), "Golden Star"),
    ("the steaming cocoa mug", ("Cocoa Tin", "Golden Star", "Toy Train"), "Cocoa Tin"),
    ("the carrot-nosed figure", ("Snowman", "Silver Bell", "Woollen Mitten"), "Snowman"),
    ("the wrapped green parcel", ("Green Parcel", "Golden Star", "Snow Globe"), "Green Parcel"),
    ("the striped festive stocking", ("Striped Stocking", "Cocoa Tin", "Toy Train"), "Striped Stocking"),
)
SAFE_CLUES = (
    ("I'm the number of sides on a snowflake's usual sixfold pattern.", "6", ("4", "6", "8")),
    ("Two bells ring twice each. How many rings altogether?", "4", ("3", "4", "6")),
    ("Three snowmen share nine buttons equally. Buttons per snowman?", "3", ("2", "3", "4")),
    ("A seven-day event begins on Day 1. How many days remain after Day 5?", "2", ("2", "3", "4")),
    ("What digit makes the sum 3 + 4?", "7", ("5", "6", "7")),
    ("A reindeer has four hooves. How many hooves does one reindeer have?", "4", ("4", "6", "8")),
    ("The icy key says: half of ten.", "5", ("4", "5", "6")),
    ("The clock chimes twelve, then six. What is 12 - 6?", "6", ("3", "6", "9")),
    ("A pair of mittens has how many individual mittens?", "2", ("1", "2", "3")),
    ("Four tiny stars plus four more stars make what number?", "8", ("6", "7", "8")),
)
SNOWMAN_PARTS = (
    ("HAT", "A classic detective snowman needs a tall black top hat.",
     ("Black Top Hat", "Red Beanie", "Golden Crown"), "Black Top Hat"),
    ("SCARF", "The blueprint shows a red-and-white candy-striped scarf.",
     ("Blue Scarf", "Candy Scarf", "Green Cravat"), "Candy Scarf"),
    ("NOSE", "Finish the snowman's face with the traditional orange vegetable.",
     ("Carrot Nose", "Icicle Nose", "Button Nose"), "Carrot Nose"),
    ("EYES", "The reference sketch calls for two dark coal eyes.",
     ("Coal Eyes", "Ruby Eyes", "Button Eyes"), "Coal Eyes"),
    ("COAT", "The figure wears a thick brown detective trench coat.",
     ("Brown Trench Coat", "Silver Jacket", "Red Cape"), "Brown Trench Coat"),
    ("ARMS", "The blueprint's arms are two bare winter twigs.",
     ("Toy Swords", "Twig Arms", "Candy Canes"), "Twig Arms"),
    ("BUTTONS", "The chest uses three shiny brass buttons.",
     ("Brass Buttons", "Blue Gems", "Wooden Discs"), "Brass Buttons"),
    ("BOOTS", "Snowy boots should be black and polished.",
     ("Brown Slippers", "Yellow Skates", "Black Boots"), "Black Boots"),
)
TRIVIA = (
    ("Which date is Christmas Day in the Gregorian calendar?",
     ("24 December", "25 December", "26 December"), "25 December",
     "Christmas Day falls on 25 December."),
    ("What festive plant has bright red bracts often mistaken for flowers?",
     ("Poinsettia", "Rosemary", "Ivy"), "Poinsettia",
     "Poinsettias are popular at Christmas for their colourful bracts."),
    ("Which of these is traditionally used to build a snowman's nose?",
     ("Carrot", "Pine cone", "Candy cane"), "Carrot",
     "A carrot is the familiar snowman nose."),
    ("Which of these is an evergreen tree?",
     ("Oak", "Spruce", "Beech"), "Spruce",
     "Spruce trees retain needles through winter."),
    ("Which festive decoration commonly hangs on a door?",
     ("Wreath", "Scarf", "Calendar"), "Wreath",
     "A wreath is a traditional seasonal door decoration."),
    ("What shape is a typical snowflake's crystal symmetry?",
     ("Fourfold", "Sixfold", "Eightfold"), "Sixfold",
     "Ice crystals commonly form sixfold structures."),
    ("What is the name for the shortest day of the year in the Northern Hemisphere?",
     ("Summer solstice", "Winter solstice", "Spring equinox"), "Winter solstice",
     "The winter solstice marks the shortest daylight period."),
    ("What are the small bells on a sleigh often called?",
     ("Jingle bells", "Ship bells", "Cow gongs"), "Jingle bells",
     "Jingle bells are associated with sleighs."),
    ("Which drink is made using cocoa beans?",
     ("Hot chocolate", "Apple juice", "Lemonade"), "Hot chocolate",
     "Cocoa is the defining ingredient in hot chocolate."),
    ("Which of these animals traditionally pulls Santa's sleigh?",
     ("Reindeer", "Penguins", "Horses"), "Reindeer",
     "Reindeer pull the sleigh in many Christmas stories."),
    ("Which month follows November?",
     ("January", "October", "December"), "December",
     "December is the twelfth calendar month."),
    ("Which seasonal treat is shaped like a hooked walking stick?",
     ("Candy cane", "Mince pie", "Shortbread"), "Candy cane",
     "Candy canes are curved striped sweets."),
    ("What do people traditionally put on top of some Christmas trees?",
     ("Star", "Teapot", "Book"), "Star",
     "Stars and angels are common tree toppers."),
    ("Which of these is a winter precipitation type?",
     ("Snow", "Sand", "Ash"), "Snow",
     "Snow forms when ice crystals fall from clouds."),
    ("In the UK, what date is Boxing Day?",
     ("24 December", "26 December", "31 December"), "26 December",
     "Boxing Day is on 26 December."),
    ("What is a bauble?",
     ("A tree ornament", "A snow shovel", "A winter coat"), "A tree ornament",
     "A bauble is a Christmas-tree decoration."),
    ("What sweet fruit is traditionally put in some Christmas puddings?",
     ("Dried raisins", "Fresh cucumber", "Raw onion"), "Dried raisins",
     "Dried fruit is a common ingredient in Christmas pudding."),
    ("What is a traditional colour of holly berries?",
     ("Red", "Turquoise", "Black"), "Red",
     "The familiar festive holly species has red berries."),
)


@dataclass(frozen=True)
class ArcadeRound:
    index: int
    total: int
    prompt: str
    choices: tuple[str, ...]
    category: str


@dataclass(frozen=True)
class ArcadeSession:
    session_id: str
    mode: str
    title: str
    day: int
    attempt: int
    step: int
    total_rounds: int
    score: int
    finished: bool
    feedback: str
    current: ArcadeRound | None
    played_choices: tuple[str, ...]


@dataclass(frozen=True)
class ArcadeRecord:
    mode: str
    name: str
    personal_best: int
    games_played: int
    attempts_today: int
    active_id: str | None


@dataclass(frozen=True)
class SocialEntry:
    name: str
    city: str
    best: int
    games: int
    user_id: int


@dataclass(frozen=True)
class CityEntry:
    city: str
    score: int
    players: int


@dataclass(frozen=True)
class ArcadeLobby:
    day: int | None
    phase: str
    records: tuple[ArcadeRecord, ...]
    stamps: tuple[str, ...]
    completed: int
    bests_total: int

    def record(self, mode: str) -> ArcadeRecord:
        return next(r for r in self.records if r.mode == mode)


@dataclass(frozen=True)
class ArcadeMove:
    session: ArcadeSession
    right: bool
    delta: int
    feedback: str
    repeated: bool
    new_stamps: tuple[str, ...]


def _render_row(row: dict[str, Any], idx: int, total: int) -> ArcadeRound:
    return ArcadeRound(idx + 1, total, row["prompt"], tuple(row["choices"]),
                       row.get("category", ""))


def _generate(mode: str, rng) -> list[dict[str, Any]]:
    """Generate one sealed randomised quiz, persisted before first display.

    Secrets are server-side: the UI sees questions and choices, not answers.
    """
    if mode not in GAMES:
        raise SocialArcadeError("Unknown arcade game.")
    spec = GAMES[mode]
    if mode == "gallery":
        pool = rng.sample(GALLERY, spec.rounds)
        result = [{"prompt": f"🎯 The announcer calls for {hint}. Which target do you hit?",
                   "choices": list(options), "answer": answer,
                   "explanation": f"Clean hit on {answer}!", "category": "Target Gallery"}
                  for hint, options, answer in pool]
    elif mode == "safe":
        pool = rng.sample(SAFE_CLUES, spec.rounds)
        result = [{"prompt": f"🔐 Dial {i + 1}/3 — {hint}",
                   "choices": list(options), "answer": answer,
                   "explanation": f"Correct dial digit: {answer}.", "category": "Safecracker"}
                  for i, (hint, answer, options) in enumerate(pool)]
    elif mode == "snowman":
        pool = rng.sample(SNOWMAN_PARTS, spec.rounds)
        result = [{"prompt": f"☃️ Blueprint: {hint}", "choices": list(options),
                   "answer": answer, "explanation": f"{part} fitted: {answer}.",
                   "category": part} for part, hint, options, answer in pool]
    elif mode == "catch":
        result = []
        for i in range(spec.rounds):
            start = rng.randrange(3)
            shift = rng.choice((-1, 0, 1))
            wind = {-1: "one lane LEFT", 0: "STILL", 1: "one lane RIGHT"}[shift]
            answer = LANES[(start+shift) % 3]
            result.append({
                "prompt": f"❄️ Flake {i + 1}: Starting lane {LANES[start]}. "
                          f"Wind: {wind}. Lanes wrap at the edges. Where will it land?",
                "choices": list(LANES), "answer": answer,
                "explanation": f"It drifted into the {answer} lane.",
                "category": "Snowflake Forecast",
            })
    else:
        pool = rng.sample(TRIVIA, spec.rounds)
        result = [{"prompt": question, "choices": list(options), "answer": answer,
                   "explanation": explanation, "category": "Christmas Trivia"}
                  for question, options, answer, explanation in pool]
    for row in result:
        rng.shuffle(row["choices"])
        if row["choices"].count(row["answer"]) != 1 or len(row["choices"]) != 3:
            raise SocialArcadeError("The generated game puzzle is invalid.")
    return result


def _session(con, row) -> ArcadeSession:
    puzzles = json.loads(row["puzzles_json"])
    step = int(row["step"])
    total = len(puzzles)
    current = _render_row(puzzles[step], step, total) if step < total else None
    chosen = tuple(r[0] for r in con.execute(
        "SELECT choice FROM social_arcade_turns WHERE session_id=? "
        "ORDER BY turn ASC", (row["session_id"],)))
    return ArcadeSession(
        row["session_id"], row["mode"], GAMES[row["mode"]].title,
        int(row["day"]), int(row["attempt"]), step, total,
        int(row["score"]), row["status"] == "finished",
        row["last_feedback"], current, chosen)


def _row_for(con, session_id, season, user):
    return con.execute(
        "SELECT * FROM social_arcade_runs WHERE session_id=? "
        "AND season_key=? AND discord_user_id=?", (session_id, season, user)).fetchone()


class SocialArcadeEngine:
    def __init__(self, store: Store, rng=None):
        self.store = store
        self.rng = rng or secrets.SystemRandom()

    @staticmethod
    def _eligible(con, season: str, user: int, now: datetime, *, active: bool):
        # Same authoritative player/review/host day gate as winter activities.
        try:
            from snowfall.services.combat import CombatEngine
            state = CombatEngine._season(con, season)
            day = WinterFunEngine._current(con, season, user, now, active=active)
            return state, day
        except ValueError as exc:
            raise SocialArcadeError(str(exc)) from exc

    def lobby(self, season: str, user: int, now: datetime) -> ArcadeLobby:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN")
            state, day = self._eligible(con, season, user, now, active=False)
            records = []
            for key, game in GAMES.items():
                best, played = con.execute(
                    "SELECT COALESCE(MAX(score),0),COUNT(*) FROM social_arcade_runs "
                    "WHERE season_key=? AND discord_user_id=? AND mode=? AND status='finished'",
                    (season, user, key)).fetchone()
                used = int(con.execute(
                    "SELECT COUNT(*) FROM social_arcade_runs WHERE season_key=? "
                    "AND discord_user_id=? AND day=? AND mode=?",
                    (season, user, day or 0, key)).fetchone()[0])
                active_row = con.execute(
                    "SELECT session_id FROM social_arcade_runs WHERE season_key=? "
                    "AND discord_user_id=? AND day=? AND mode=? AND status='active'",
                    (season, user, day or 0, key)).fetchone()
                records.append(ArcadeRecord(key, game.title, int(best), int(played),
                                            used, active_row[0] if active_row else None))
            stamps = tuple(r[0] for r in con.execute(
                "SELECT stamp_key FROM social_arcade_stamps WHERE season_key=? "
                "AND discord_user_id=? ORDER BY stamp_key", (season, user)))
            return ArcadeLobby(day, state.phase(now), tuple(records), stamps,
                               sum(r.games_played for r in records),
                               sum(r.personal_best for r in records))

    def begin(self, season: str, user: int, mode: str, now: datetime, *,
              expected_day: int | None = None, expected_used: int | None = None) -> ArcadeSession:
        """Resume active session or spend one of three daily *starts*."""
        if mode not in GAMES:
            raise SocialArcadeError("Unknown arcade game.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            _, day = self._eligible(con, season, user, now, active=True)
            if expected_day is not None and day != expected_day:
                raise SocialArcadeError("The event day changed. Refresh the arcade.")
            active = con.execute(
                "SELECT * FROM social_arcade_runs WHERE season_key=? "
                "AND discord_user_id=? AND day=? AND mode=? AND status='active'",
                (season, user, day, mode)).fetchone()
            used = int(con.execute(
                "SELECT COUNT(*) FROM social_arcade_runs WHERE season_key=? "
                "AND discord_user_id=? AND day=? AND mode=?",
                (season, user, day, mode)).fetchone()[0])
            # Web starts carry a snapshot of the attempt counter. In the
            # same write transaction, a retry returns its existing run even
            # if it was completed on Discord after the response was lost.
            if expected_used is not None and used != expected_used:
                if used == expected_used + 1:
                    previous = con.execute(
                        "SELECT * FROM social_arcade_runs WHERE season_key=? "
                        "AND discord_user_id=? AND day=? AND mode=? AND attempt=?",
                        (season, user, day, mode, used)).fetchone()
                    if previous:
                        return _session(con, previous)
                raise SocialArcadeError("Arcade attempts changed. Refresh the lobby.")
            if active:
                return _session(con, active)
            if used >= DAILY_GAME_CAP:
                raise SocialArcadeError(
                    "You've used all three daily runs of this game. "
                    "Try another arcade game or view the leaderboards.")
            puzzles = _generate(mode, self.rng)
            run_id = secrets.token_hex(16)
            con.execute(
                "INSERT INTO social_arcade_runs(session_id,season_key,discord_user_id,"
                "day,mode,attempt,puzzles_json,started_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (run_id, season, user, day, mode, used+1,
                 json.dumps(puzzles, ensure_ascii=True), _timestamp(now)))
            row = _row_for(con, run_id, season, user)
            return _session(con, row)

    def session(self, season: str, user: int, session_id: str, now: datetime):
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN")
            _, day = self._eligible(con, season, user, now, active=False)
            row = _row_for(con, session_id, season, user)
            if row is None:
                raise SocialArcadeError("This arcade session belongs to another player.")
            if day != row["day"]:
                raise SocialArcadeError("That arcade round belongs to a previous event day.")
            return _session(con, row)

    def move(self, season: str, user: int, session_id: str,
             expected_step: int, choice: str, interaction_id: str,
             now: datetime) -> ArcadeMove:
        """Server-authoritative, single atomic step with replay-safe updates."""
        if not isinstance(interaction_id, str) or not 1 <= len(interaction_id) <= 128:
            raise SocialArcadeError("A valid unique Discord interaction is required.")
        if not isinstance(choice, str) or len(choice) > 96:
            raise SocialArcadeError("Invalid arcade choice.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._eligible(con, season, user, now, active=True)
            previous = con.execute(
                "SELECT * FROM social_arcade_turns WHERE interaction_id=?",
                (interaction_id,)).fetchone()
            if previous:
                if ((previous["season_key"], previous["discord_user_id"],
                     previous["session_id"], previous["turn"], previous["choice"])
                    != (season, user, session_id, expected_step, choice)):
                    raise SocialArcadeError(
                        "This interaction already belongs to a different arcade choice.")
                row = _row_for(con, session_id, season, user)
                if row is None:
                    raise SocialArcadeError("Arcade session unavailable.")
                return ArcadeMove(_session(con, row), bool(previous["correct"]),
                                  int(previous["points"]), previous["feedback"],
                                  True, ())
            row = _row_for(con, session_id, season, user)
            if row is None:
                raise SocialArcadeError("This arcade session belongs to another player.")
            state_day = self._eligible(con, season, user, now, active=True)[1]
            if int(row["day"]) != state_day:
                raise SocialArcadeError("That game is from a previous event day.")
            if row["status"] != "active":
                raise SocialArcadeError("This arcade game is already completed.")
            if int(row["step"]) != expected_step:
                raise SocialArcadeError("That move is out of date. Reopen the game to refresh.")
            puzzles = json.loads(row["puzzles_json"])
            if not 0 <= expected_step < len(puzzles):
                raise SocialArcadeError("Invalid game round.")
            puzzle = puzzles[expected_step]
            if choice not in puzzle["choices"]:
                raise SocialArcadeError("That choice isn't one of the offered options.")
            correct = choice == puzzle["answer"]
            base = {"safe": 30, "snowman": 25}.get(row["mode"], 20)
            delta = base if correct else 0
            total = int(row["score"]) + delta
            next_step = expected_step+1
            finished = next_step == len(puzzles)
            if finished and row["mode"] == "safe" and total == 90:
                delta += 10
                total += 10
            message = (("✅ " if correct else "❄️ ")
                       + (puzzle["explanation"] if correct else
                          f"Not quite: {puzzle['answer']}. {puzzle['explanation']}")
                       + (" Perfect safe cracked!" if finished and total == 100
                          and row["mode"] == "safe" else ""))
            con.execute(
                "INSERT INTO social_arcade_turns(interaction_id,session_id,"
                "season_key,discord_user_id,day,turn,choice,correct,points,"
                "score_after,feedback,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (interaction_id, session_id, season, user, state_day, expected_step,
                 choice, int(correct), delta, total, message, _timestamp(now)))
            con.execute(
                "UPDATE social_arcade_runs SET step=?,score=?,status=?,"
                "last_feedback=?,finished_at_utc=? WHERE session_id=?",
                (next_step, total, "finished" if finished else "active",
                 message, _timestamp(now) if finished else None, session_id))
            new_stamps = []
            if finished:
                potential = [f"played_{row['mode']}"]
                if total == 100:
                    potential.append(f"master_{row['mode']}")
                completed_games = {r[0] for r in con.execute(
                    "SELECT DISTINCT mode FROM social_arcade_runs WHERE "
                    "season_key=? AND discord_user_id=? AND status='finished'",
                    (season, user))}
                if len(completed_games) == len(GAMES):
                    potential.append("all_five")
                for stamp in potential:
                    added = con.execute(
                        "INSERT OR IGNORE INTO social_arcade_stamps("
                        "season_key,discord_user_id,stamp_key,earned_at_utc)"
                        "VALUES(?,?,?,?)", (season, user, stamp, _timestamp(now)))
                    if added.rowcount:
                        new_stamps.append(stamp)
            updated = _row_for(con, session_id, season, user)
            return ArcadeMove(_session(con, updated), correct, delta,
                              message, False, tuple(new_stamps))

    def leaderboard(self, season: str, user: int, mode: str, now: datetime,
                    *, daily: bool = False, limit: int = 10) -> tuple[SocialEntry, ...]:
        if mode not in GAMES:
            raise SocialArcadeError("Unknown arcade game.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN")
            _, day = self._eligible(con, season, user, now, active=False)
            if daily and day is None:
                return ()
            clause = "AND r.day=?" if daily else ""
            params = (season, mode, day) if daily else (season, mode)
            rows = con.execute(f"""SELECT p.mr_username name,p.city city,
                    MAX(r.score) best,COUNT(*) games,p.discord_user_id user_id
                FROM social_arcade_runs r
                JOIN players p ON p.season_key=r.season_key
                  AND p.discord_user_id=r.discord_user_id
                WHERE r.season_key=? AND r.mode=? AND r.status='finished'
                  AND p.review_state NOT IN ('flagged','disqualified')
                  {clause}
                GROUP BY r.discord_user_id,p.id
                ORDER BY best DESC, games DESC, p.mr_username_norm ASC
                LIMIT ?""", (*params, min(25,max(1,limit)))).fetchall()
            return tuple(SocialEntry(row["name"], row["city"], int(row["best"]),
                                     int(row["games"]), int(row["user_id"]))
                         for row in rows)

    def city_table(self, season: str, user: int, now: datetime,
                   *, daily: bool = False) -> tuple[CityEntry, ...]:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN")
            _, day = self._eligible(con, season, user, now, active=False)
            if daily and day is None:
                return ()
            clause = "AND day=?" if daily else ""
            params = (season, day) if daily else (season,)
            rows = con.execute(f"""SELECT p.city city,SUM(b.best) total,
                     COUNT(DISTINCT b.discord_user_id) players
                FROM (SELECT season_key,discord_user_id,mode,MAX(score) best
                    FROM social_arcade_runs WHERE season_key=?
                    AND status='finished' {clause}
                    GROUP BY season_key,discord_user_id,mode) b
                JOIN players p ON p.season_key=b.season_key
                  AND p.discord_user_id=b.discord_user_id
                WHERE p.review_state NOT IN ('flagged','disqualified')
                GROUP BY p.city ORDER BY total DESC,p.city ASC""",params).fetchall()
            return tuple(CityEntry(r["city"],int(r["total"]),int(r["players"]))
                         for r in rows)
