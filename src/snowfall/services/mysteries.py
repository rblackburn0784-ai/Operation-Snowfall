"""v0.2.6 Christmas mysteries and secret encounters: cosmetic-only case histories.

A seven-chapter detective story with immutable, season/player/day scoped records.
No method touches scores, official prizes, wallet balances, PvP/PvE events or gear.
All writes are serialized and replay-safe, including concurrent double-clicks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.winter_fun import WinterFunEngine


class MysteryError(ValueError):
    """An invalid or unavailable investigation; nothing else changes."""


@dataclass(frozen=True)
class MysteryCase:
    day: int
    title: str
    scene: str
    leads: tuple[tuple[str, str, str], ...]
    suspects: tuple[tuple[str, str], ...]
    culprit: str
    conclusion: str
    secret_title: str
    secret_scene: str


CASES = (
    MysteryCase(
        1, "The Vanishing Christmas Ledger",
        "The Gutter Saints' charity ledger disappeared from the back of a Chicago "
        "speakeasy during the first snowfall. Nobody saw the door open.",
        (("window", "The Frosted Window", "The window is sealed shut from the inside; the "
          "snow outside the sill is undisturbed."),
         ("counter", "The Cash Counter", "The counter clock stopped at 10:17. A bellhop "
          "collected the room keys at 10:15."),
         ("door", "The Back Door", "Only the bellhop has the spare key. A trail of "
          "hotel-lobby carpet fibres leads behind the bar.")),
        (("courier", "Midnight Courier"), ("musician", "Club Bandleader"),
         ("bellhop", "Hotel Bellhop")), "bellhop",
        "The bellhop took the charity ledger through the locked back door. "
        "The courier and bandleader never held the spare key.",
        "The Alleyway Carol", "A masked singer is waiting beside the old hotel loading bay.",
    ),
    MysteryCase(
        2, "The Ghost Train at Midnight",
        "A toy train full of Christmas parcels rolled across the station tracks "
        "after the stationmaster locked the depot.",
        (("tracks", "Fresh Rail Marks", "The snow beside the rails is untouched. "
          "Nobody walked beside the runaway train."),
         ("engine", "The Engine Panel", "A recently installed timer has a mechanic's "
          "toolmark and was set to midnight."),
         ("platform", "Platform Tickets", "The conductor left before 11; "
          "the mechanic signed out the only service hatch key.")),
        (("conductor", "Night Conductor"), ("mechanic", "Depot Mechanic"),
         ("porter", "Platform Porter")), "mechanic",
        "The mechanic fitted a midnight timer behind the engine panel to move the parcels.",
        "The Lantern in Carriage Seven",
        "A lantern flickers inside an empty carriage no timetable mentions.",
    ),
    MysteryCase(
        3, "The Ice Vault Job",
        "A locked ice-house vault was found open. Its missing festive star had "
        "never left the building, according to the night watch.",
        (("lock", "The Vault Lock", "The lock was opened cleanly with a narrow "
          "specialist pick; there are no marks from forced entry."),
         ("floor", "The Snowy Floor", "A locksmith's wax imprint was left "
          "beneath the vault hinge."),
         ("receipt", "The Service Receipt", "The locksmith was called to repair "
          "this exact lock after closing. No other visitor signed in.")),
        (("bartender", "Ice Bar Bartender"), ("florist", "Midnight Florist"),
         ("locksmith", "Vault Locksmith")), "locksmith",
        "The locksmith copied the lock while posing as a repairman.",
        "The Secret Cellar",
        "Behind the ice vault, a hidden cellar door has appeared in the brickwork.",
    ),
    MysteryCase(
        4, "The Missing Sleigh Bell",
        "One priceless silver bell vanished from the town sleigh during the "
        "Christmas supply parade.",
        (("sleigh", "The Sleigh Harness", "The knot was undone neatly, "
          "not cut or broken."),
         ("schedule", "The Parade Schedule", "The clerk rescheduled the "
          "sleigh's stop to a deserted side street."),
         ("envelope", "The Sealed Envelope", "A parcel receipt for a silver "
          "bell bears the parade clerk's distinctive green ink.")),
        (("caroler", "Lead Caroler"), ("driver", "Sleigh Driver"),
         ("clerk", "Parade Clerk")), "clerk",
        "The clerk diverted the sleigh and used a parcel run to hide the bell.",
        "A Parcel Without a Name",
        "A parcel wrapped in silver paper is sitting outside the post office.",
    ),
    MysteryCase(
        5, "Who Stole the Snow Don's Hat?",
        "The Snow Don's battered fedora vanished while his bodyguards "
        "watched the frozen alley. Someone has embarrassed the whole mob.",
        (("tripod", "The Camera Tripod", "A camera tripod had been placed "
          "directly in front of the hat stand."),
         ("negative", "An Old Negative", "A developed photo shows the "
          "fedora placed inside a photographer's equipment case."),
         ("ticket", "The Coat Check", "The lookout's coat and tailor's "
          "measuring case are still sealed; the photographer left early.")),
        (("tailor", "Snowy Tailor"), ("lookout", "The Alley Lookout"),
         ("photographer", "Press Photographer")), "photographer",
        "The photographer slipped the hat into a camera case during his staged portrait.",
        "The Hatbox Informant",
        "An anonymous informant has left a hatbox under a Christmas tree.",
    ),
    MysteryCase(
        6, "The Blizzard Telegram",
        "A coded telegram diverted the city's winter relief trucks to a "
        "closed warehouse. The sender vanished into the whiteout.",
        (("paper", "The Telegram Paper", "The message uses the exact violet "
          "carbon paper stocked behind the telegraph office counter."),
         ("morse", "The Morse Tape", "The tape includes a correction made "
          "at the operator's desk before the outgoing signal."),
         ("shift", "The Shift Roster", "The operator worked alone that "
          "night; neither the banker nor driver entered the office.")),
        (("driver", "Relief Truck Driver"), ("banker", "Bank Manager"),
         ("operator", "Telegraph Operator")), "operator",
        "The operator rewrote the relief route and sent the false dispatch.",
        "The Signal Under the Snow",
        "A faint second message is tapping through the abandoned telegraph wire.",
    ),
    MysteryCase(
        7, "The Last Gift of Snowfall",
        "The Christmas Eve gift intended for every city went missing from "
        "the festive vault. The lock was never forced.",
        (("keyring", "The Key Cabinet", "The caretaker signed out the "
          "vault master key before dusk and failed to return it."),
         ("footprints", "The Courtyard Footprints", "A trail of boots "
          "matches the caretaker's unique square heel pattern."),
         ("receipt", "The Gift Register", "The mayor and janitor signed "
          "the register but neither had the master key.")),
        (("mayor", "Winter Mayor"), ("janitor", "Night Janitor"),
         ("caretaker", "Vault Caretaker")), "caretaker",
        "The caretaker moved the gift to a safe hiding place, hoping "
        "to keep it out of the Snow Don's hands.",
        "The Midnight Star",
        "A warm golden light glimmers where the final present should have been.",
    ),
)

LEAD_KEYS = frozenset(key for case in CASES for key, _, _ in case.leads)
SECRET_CHOICES = {
    "follow": ("Follow the whisper", "Silver Footprint"),
    "assist": ("Help the stranger", "Frosted Lantern"),
    "listen": ("Listen from the shadows", "Midnight Note"),
}
# Different stories are picked reproducibly per season / player / event day,
# not via the RNG used by combat or prize allocation.
SECRET_VARIANTS = (
    ("An old musician turns a corner, carrying a letter sealed in blue wax.",
     "The letter reveals a tiny map of snow-covered Christmas rooftops."),
    ("A masked courier slips out of a doorway without leaving any footprints.",
     "You discover a card signed 'From the Winter Underworld'."),
    ("A little light dances around a closed shop window in the blizzard.",
     "It illuminates a secret festive message written in frost."),
)
MAX_GUESSES = 2


@dataclass(frozen=True)
class ClueRecord:
    key: str
    label: str
    text: str
    found: bool


@dataclass(frozen=True)
class SecretRecord:
    title: str
    scene: str
    choice: str
    souvenir: str
    repeated: bool = False


@dataclass(frozen=True)
class GuessResult:
    day: int
    correct: bool
    solved: bool
    attempts_used: int
    message: str
    repeated: bool = False


@dataclass(frozen=True)
class CasebookEntry:
    day: int
    title: str
    clues: int
    solved: bool
    attempts: int
    secret: str | None


@dataclass(frozen=True)
class MysterySnapshot:
    day: int | None
    phase: str
    case: MysteryCase | None
    clues: tuple[ClueRecord, ...]
    guesses: int
    solved: bool
    locked: bool
    secret_ready: bool
    secret: SecretRecord | None
    activity: bool
    history: tuple[CasebookEntry, ...]

    @property
    def solved_count(self) -> int:
        return sum(entry.solved for entry in self.history)

    @property
    def souvenirs_count(self) -> int:
        return sum(entry.secret is not None for entry in self.history)


class MysteryEngine:
    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _check_id(interaction: str):
        if not isinstance(interaction, str) or not 1 <= len(interaction) <= 128:
            raise MysteryError("A valid unique Discord interaction ID is required.")

    @staticmethod
    def _current(con, season, user, now, *, active: bool):
        try:
            return WinterFunEngine._current(con, season, user, now, active=active)
        except ValueError as exc:
            raise MysteryError(str(exc)) from exc

    @staticmethod
    def _clues(con, season, user, day) -> set[str]:
        return {r[0] for r in con.execute(
            "SELECT lead_key FROM mystery_clues WHERE season_key=? "
            "AND discord_user_id=? AND day=?", (season, user, day))}

    @staticmethod
    def _guesses(con, season, user, day):
        return con.execute(
            "SELECT suspect_key,correct FROM mystery_guesses "
            "WHERE season_key=? AND discord_user_id=? AND day=? "
            "ORDER BY created_at_utc, interaction_id", (season, user, day)).fetchall()

    @staticmethod
    def _secret(con, season, user, day):
        return con.execute(
            "SELECT choice,souvenir,variant FROM mystery_secrets "
            "WHERE season_key=? AND discord_user_id=? AND day=?",
            (season, user, day)).fetchone()

    @staticmethod
    def _activity(con, season, user, day) -> bool:
        scored = con.execute(
            "SELECT 1 FROM score_ledger WHERE season_key=? AND player_id=? "
            "AND day=? AND points>0 LIMIT 1", (season, user, day)).fetchone()
        encountered = con.execute(
            "SELECT 1 FROM encounter_events WHERE season_key=? AND discord_user_id=? "
            "AND day=? LIMIT 1", (season, user, day)).fetchone()
        return bool(scored or encountered)

    @staticmethod
    def _variant(season, user, day):
        seed = f"{season}:{user}:{day}".encode("utf-8")
        return int.from_bytes(hashlib.blake2b(seed, digest_size=4).digest(), "big") % len(SECRET_VARIANTS)

    @staticmethod
    def _secret_record(case, row, repeated=False):
        variant = int(row["variant"])
        scene, discovery = SECRET_VARIANTS[variant]
        return SecretRecord(case.secret_title, f"{case.secret_scene} {scene} {discovery}",
                            row["choice"], row["souvenir"], repeated)

    def snapshot(self, season: str, user: int, now: datetime) -> MysterySnapshot:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN")  # Consistent read; no event action or reward.
            day = self._current(con, season, user, now, active=False)
            # Reuse the canonical clock, including effective day while paused.
            from snowfall.services.combat import CombatEngine
            phase = CombatEngine._season(con, season).phase(now)
            found = {}
            for row in con.execute(
                "SELECT day,lead_key FROM mystery_clues WHERE season_key=? AND "
                "discord_user_id=?", (season, user)):
                found.setdefault(int(row["day"]), set()).add(row["lead_key"])
            guesses = {}
            for row in con.execute(
                "SELECT day,correct FROM mystery_guesses WHERE season_key=? "
                "AND discord_user_id=?", (season, user)):
                guesses.setdefault(int(row["day"]), []).append(bool(row["correct"]))
            secrets = {}
            for row in con.execute(
                "SELECT day,choice,souvenir,variant FROM mystery_secrets "
                "WHERE season_key=? AND discord_user_id=?", (season, user)):
                secrets[int(row["day"])] = row
            history = tuple(CasebookEntry(
                case.day, case.title, len(found.get(case.day, ())),
                any(guesses.get(case.day, ())), len(guesses.get(case.day, ())),
                secrets[case.day]["souvenir"] if case.day in secrets else None,
            ) for case in CASES)
            if day is None:
                return MysterySnapshot(None, phase, None, (), 0, False, False,
                                       False, None, False, history)
            case = CASES[day - 1]
            clue_keys = found.get(day, set())
            clues = tuple(ClueRecord(key, title, note, key in clue_keys)
                          for key, title, note in case.leads)
            attempted = guesses.get(day, ())
            secret = self._secret_record(case, secrets[day]) if day in secrets else None
            activity = self._activity(con, season, user, day)
            return MysterySnapshot(
                day, phase, case, clues, len(attempted), any(attempted),
                len(attempted) >= MAX_GUESSES and not any(attempted),
                bool(len(clue_keys) >= 2 and activity and secret is None),
                secret, activity, history,
            )

    def investigate(self, season: str, user: int, lead: str, interaction: str,
                    now: datetime) -> tuple[ClueRecord, bool]:
        self._check_id(interaction)
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._current(con, season, user, now, active=True)
            case = CASES[day - 1]
            valid = {key: (title, detail) for key, title, detail in case.leads}
            if lead not in valid:
                raise MysteryError("That lead is not in today's case file.")
            used = con.execute("SELECT season_key,discord_user_id,day,lead_key FROM "
                               "mystery_clues WHERE interaction_id=?", (interaction,)).fetchone()
            if used and tuple(used) != (season, user, day, lead):
                raise MysteryError("That interaction ID belongs to another investigation.")
            old = con.execute("SELECT 1 FROM mystery_clues WHERE season_key=? "
                              "AND discord_user_id=? AND day=? AND lead_key=?",
                              (season, user, day, lead)).fetchone()
            repeated = bool(old)
            if not old:
                con.execute(
                    "INSERT INTO mystery_clues(interaction_id,season_key,discord_user_id,"
                    "day,lead_key,found_at_utc) VALUES (?,?,?,?,?,?)",
                    (interaction, season, user, day, lead, _timestamp(now)))
            return ClueRecord(lead, *valid[lead], True), repeated

    def accuse(self, season: str, user: int, suspect: str, interaction: str,
               now: datetime) -> GuessResult:
        self._check_id(interaction)
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._current(con, season, user, now, active=True)
            case = CASES[day - 1]
            labels = dict(case.suspects)
            if suspect not in labels:
                raise MysteryError("Choose one of today's three suspects.")
            earlier = con.execute(
                "SELECT season_key,discord_user_id,day,suspect_key,correct FROM "
                "mystery_guesses WHERE interaction_id=?", (interaction,)).fetchone()
            if earlier and tuple(earlier)[:4] != (season, user, day, suspect):
                raise MysteryError("That interaction ID belongs to another accusation.")
            rows = self._guesses(con, season, user, day)
            if len(self._clues(con, season, user, day)) < 2 and earlier is None:
                raise MysteryError("Collect at least two clues before accusing anyone.")
            if earlier is not None:
                correct = bool(earlier["correct"])
                return GuessResult(day, correct, correct or any(r["correct"] for r in rows),
                                   len(rows), case.conclusion if correct else
                                   "That accusation was already investigated.", True)
            if any(r["correct"] for r in rows):
                raise MysteryError("You've solved today's mystery already.")
            if len(rows) >= MAX_GUESSES:
                raise MysteryError("No accusations remain today. The next case opens tomorrow.")
            # Retrying the same wrong suspect does not spend another attempt.
            if any(r["suspect_key"] == suspect for r in rows):
                return GuessResult(day, False, False, len(rows),
                                   "Already ruled out. Pick a different suspect.", True)
            correct = suspect == case.culprit
            con.execute(
                "INSERT INTO mystery_guesses(interaction_id,season_key,discord_user_id,"
                "day,suspect_key,correct,created_at_utc) VALUES (?,?,?,?,?,?,?)",
                (interaction, season, user, day, suspect, int(correct), _timestamp(now)))
            attempts = len(rows) + 1
            message = (f"CASE CLOSED! {case.conclusion}" if correct
                       else "That story doesn't fit the evidence. "
                       + ("One accusation remains." if attempts < MAX_GUESSES
                          else "The case is unsolved for today."))
            return GuessResult(day, correct, correct, attempts, message)

    def secret(self, season: str, user: int, choice: str, interaction: str,
               now: datetime) -> SecretRecord:
        self._check_id(interaction)
        if choice not in SECRET_CHOICES:
            raise MysteryError("That is not a secret encounter choice.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._current(con, season, user, now, active=True)
            case = CASES[day - 1]
            prior_id = con.execute(
                "SELECT season_key,discord_user_id,day,choice FROM mystery_secrets "
                "WHERE interaction_id=?", (interaction,)).fetchone()
            if prior_id and tuple(prior_id) != (season, user, day, choice):
                raise MysteryError("That interaction ID belongs to another encounter.")
            existing = self._secret(con, season, user, day)
            if existing:
                return self._secret_record(case, existing, True)
            if len(self._clues(con, season, user, day)) < 2 or not self._activity(
                    con, season, user, day):
                raise MysteryError(
                    "Secret still locked. Find two clues and either earn real daily "
                    "points or finish today's ordinary surprise encounter.")
            variant = self._variant(season, user, day)
            souvenir = f"{case.secret_title} — {SECRET_CHOICES[choice][1]}"
            con.execute(
                "INSERT INTO mystery_secrets(interaction_id,season_key,discord_user_id,"
                "day,variant,choice,souvenir,found_at_utc) VALUES (?,?,?,?,?,?,?,?)",
                (interaction, season, user, day, variant, choice, souvenir, _timestamp(now)))
            row = self._secret(con, season, user, day)
            return self._secret_record(case, row)
