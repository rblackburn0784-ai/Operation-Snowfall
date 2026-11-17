"""Scoring-neutral v0.2.0 cosmetics, equipment, encounters and winter arcade modes.

No methods insert score_ledger, mutate combat/PvE ledgers, create paid awards,
or alter official combat rules. All data is season-scoped and isolated in the
existing disposable practice database when invoked from a test-day channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import secrets
from typing import Protocol

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.combat import CombatEngine


class WinterFunError(ValueError):
    """Rejected cosmetic/arcade action with no wallet or record changes."""


@dataclass(frozen=True)
class Cosmetic:
    key: str
    name: str
    category: str
    cost: int
    detail: str
    # Arcade gear advantages never apply to PvP, siege or boss fights.
    arcade_bonus: float = 0.0


COSMETICS: dict[str, Cosmetic] = {x.key: x for x in (
    Cosmetic("ice_frame", "Icy Noir Frame", "frame", 8, "Frosted portrait edging"),
    Cosmetic("gold_frame", "Golden Gutter Frame", "frame", 15, "Shimmering golden edging"),
    Cosmetic("snow_trail", "Snowstorm Trail", "trail", 6, "Blue sparkling snowball trail"),
    Cosmetic("candy_trail", "Candy Cane Trail", "trail", 10, "Red-and-white snowball trail"),
    Cosmetic("goggles", "Glacier Goggles", "gear", 10, "Improved aim in Target Practice only", .10),
    Cosmetic("boots", "Froststep Boots", "gear", 10, "Better evasion in Blizzard Dodge only", .10),
    Cosmetic("scarf", "Snow Don Scarf", "gear", 12, "Extra damage in Boss Drill only", .10),
    Cosmetic("midnight_banner", "Midnight Mob Banner", "banner", 8, "1930s noir profile header"),
)}
SLOTS = ("frame", "trail", "gear", "banner")
MODES = {
    "target": ("Target Practice", "Five practice throws at ice cans; the goggles improve accuracy"),
    "dodge": ("Blizzard Dodge", "Dodge five flying snowdrifts; Froststep Boots help"),
    "boss": ("Boss Drill", "Four training hits against a cardboard Snow Don; scarf helps"),
}
ENCOUNTER_CHOICES = {
    "help": ("Offer a hand", "Kindness"),
    "investigate": ("Investigate clues", "Detective"),
    "prank": ("Pull a harmless prank", "Mischief"),
}
ARCADE_STYLES = {
    "steady": ("Steady Shot", "Higher accuracy, lower arcade score per hit"),
    "risky": ("All-or-Nothing", "Lower accuracy, double arcade score per hit"),
}
DAILY_MODE_CAP = 3
ENCOUNTERS = (
    ("The Stray Reindeer", "You found a reindeer outside a Chicago speakeasy!", "Reindeer Postcard"),
    ("The Missing Mittens", "A street vendor has lost his Christmas gloves.", "Lost Mittens Pin"),
    ("Frozen Getaway Car", "A mobster's getaway car is buried in snow.", "Snowbound Keyring"),
    ("Carolers at the Club", "A chorus is singing right outside the hideout.", "Silver Jingle Bell"),
    ("The Midnight Courier", "A courier left a parcel wrapped in brown paper.", "Courier Ribbon"),
    ("The Blizzard Warning", "The city radio predicts a rough night of snowfall.", "Storm Warning Card"),
    ("The Last Snowflake", "One silver snowflake settles on your coat.", "Final Night Memento"),
)


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class ArcadeResult:
    mode: str
    points: int
    personal_best: int
    attempts_used: int
    equip: str | None
    repeated: bool = False
    style: str = "steady"


@dataclass(frozen=True)
class EncounterResult:
    day: int
    title: str
    story: str
    souvenir: str
    repeated: bool = False
    choice: str = "help"


@dataclass(frozen=True)
class ShopView:
    balance: int
    unlocked: frozenset[str]
    equipped: dict[str, str]
    day: int | None
    arcade_used: dict[str, int]
    arcade_best: dict[str, int]
    encounter: EncounterResult | None


class WinterFunEngine:
    def __init__(self, store: Store, rng: RandomSource | None = None):
        self.store = store
        self.rng = rng or secrets.SystemRandom()

    @staticmethod
    def _unique_id(interaction: str) -> None:
        if not isinstance(interaction, str) or not 1 <= len(interaction) <= 128:
            raise WinterFunError("A unique interaction ID is required.")

    @staticmethod
    def _current(con, season: str, user: int, now: datetime, *, active: bool):
        state = CombatEngine._season(con, season)
        person = con.execute("SELECT city FROM players WHERE season_key=? AND discord_user_id=? "
                             "AND review_state NOT IN ('flagged','disqualified')", (season, user)).fetchone()
        if not person:
            raise WinterFunError("Register and pass identity review before opening winter activities.")
        if active and state.phase(now) != "live":
            raise WinterFunError("Winter activities run only while the event day is live.")
        day = state.day(now)
        if active and day is None:
            raise WinterFunError("The host has not started an event day yet.")
        return day

    def shop(self, season: str, user: int, now: datetime) -> ShopView:
        now = as_utc(now)
        with self.store.connect() as con:
            day = self._current(con, season, user, now, active=False)
            resource = con.execute("SELECT snowflakes FROM player_resources WHERE "
                                   "season_key=? AND discord_user_id=?", (season, user)).fetchone()
            balance = int(resource[0]) if resource else 0
            unlocks = frozenset(r[0] for r in con.execute(
                "SELECT cosmetic_key FROM cosmetic_unlocks WHERE season_key=? AND discord_user_id=?",
                (season, user)))
            equipped = {r[0]: r[1] for r in con.execute(
                "SELECT category,cosmetic_key FROM cosmetic_equipped WHERE season_key=? AND discord_user_id=?",
                (season, user))}
            used, best = {}, {}
            for key in MODES:
                used[key] = int(con.execute(
                    "SELECT COUNT(*) FROM arcade_events WHERE season_key=? AND discord_user_id=? "
                    "AND day=? AND mode=?", (season, user, day or 0, key)).fetchone()[0])
                best[key] = int(con.execute(
                    "SELECT COALESCE(MAX(score),0) FROM arcade_events WHERE season_key=? "
                    "AND discord_user_id=? AND mode=?", (season, user, key)).fetchone()[0])
            encounter_row = con.execute("SELECT day,souvenir,choice FROM encounter_events WHERE "
                                        "season_key=? AND discord_user_id=? AND day=?",
                                        (season, user, day or 0)).fetchone()
            encounter = None
            if encounter_row:
                story = ENCOUNTERS[day - 1]
                encounter = EncounterResult(day, story[0], story[1], encounter_row[1], True, encounter_row[2])
            return ShopView(balance, unlocks, equipped, day, used, best, encounter)

    def buy(self, season: str, user: int, key: str, interaction: str, now: datetime) -> str:
        """Single IMMEDIATE transaction; retrying an interaction never spends twice."""
        self._unique_id(interaction)
        if key not in COSMETICS:
            raise WinterFunError("Unknown cosmetic or equipment.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._current(con, season, user, now, active=True)
            replay = con.execute("SELECT season_key,discord_user_id,cosmetic_key,detail FROM cosmetic_purchases "
                                 "WHERE interaction_id=?", (interaction,)).fetchone()
            if replay:
                if replay[0] != season or replay[1] != user or replay[2] != key:
                    raise WinterFunError("Interaction ID has already been used for another purchase.")
                return replay[3]
            item = COSMETICS[key]
            already = con.execute("SELECT 1 FROM cosmetic_unlocks WHERE season_key=? "
                                  "AND discord_user_id=? AND cosmetic_key=?", (season, user, key)).fetchone()
            if already:
                raise WinterFunError("Already owned. Open Wardrobe to equip it.")
            row = con.execute("SELECT snowflakes FROM player_resources WHERE "
                              "season_key=? AND discord_user_id=?", (season, user)).fetchone()
            if not row or int(row[0]) < item.cost:
                raise WinterFunError(f"You need {item.cost} Snowflakes to buy {item.name}.")
            con.execute("UPDATE player_resources SET snowflakes=snowflakes-? WHERE "
                        "season_key=? AND discord_user_id=? AND snowflakes>=?",
                        (item.cost, season, user, item.cost))
            con.execute("INSERT INTO cosmetic_unlocks(season_key,discord_user_id,cosmetic_key," 
                        "unlocked_at_utc) VALUES (?,?,?,?)", (season, user, key, _timestamp(now)))
            detail = f"🛍️ {item.name} unlocked for {item.cost} Snowflakes. Cosmetic/arcade only."
            con.execute("INSERT INTO cosmetic_purchases(interaction_id,season_key,discord_user_id," 
                        "day,cosmetic_key,cost,detail,purchased_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                        (interaction, season, user, day, key, item.cost, detail, _timestamp(now)))
            return detail

    def equip(self, season: str, user: int, key: str, now: datetime) -> str:
        now = as_utc(now)
        if key not in COSMETICS:
            raise WinterFunError("Unknown cosmetic or equipment.")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._current(con, season, user, now, active=False)
            unlocked = con.execute("SELECT 1 FROM cosmetic_unlocks WHERE season_key=? "
                                   "AND discord_user_id=? AND cosmetic_key=?",
                                   (season, user, key)).fetchone()
            if not unlocked:
                raise WinterFunError("You must unlock this item before equipping it.")
            item = COSMETICS[key]
            con.execute("INSERT INTO cosmetic_equipped(season_key,discord_user_id,category,"
                        "cosmetic_key) VALUES (?,?,?,?) ON CONFLICT(season_key,discord_user_id,"
                        "category) DO UPDATE SET cosmetic_key=excluded.cosmetic_key",
                        (season, user, item.category, key))
            return f"🎩 Equipped {item.name} in your {item.category} slot."

    def encounter(self, season: str, user: int, interaction: str, now: datetime,
                  choice: str = "help") -> EncounterResult:
        self._unique_id(interaction)
        if choice not in ENCOUNTER_CHOICES:
            raise WinterFunError("Unknown encounter response.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._current(con, season, user, now, active=True)
            previous_id = con.execute("SELECT season_key,discord_user_id,day FROM encounter_events "
                                      "WHERE interaction_id=?", (interaction,)).fetchone()
            if previous_id and tuple(previous_id) != (season, user, day):
                raise WinterFunError("This interaction was used in another encounter.")
            old = con.execute("SELECT souvenir,choice FROM encounter_events WHERE season_key=? "
                              "AND discord_user_id=? AND day=?", (season, user, day)).fetchone()
            title, story, souvenir = ENCOUNTERS[day - 1]
            if old:
                return EncounterResult(day, title, story, old[0], True, old[1])
            souvenir = f"{souvenir} — {ENCOUNTER_CHOICES[choice][1]}"
            con.execute("INSERT INTO encounter_events(interaction_id,season_key,discord_user_id,"
                        "day,souvenir,choice,encountered_at_utc) VALUES (?,?,?,?,?,?,?)",
                        (interaction, season, user, day, souvenir, choice, _timestamp(now)))
            return EncounterResult(day, title, story, souvenir, False, choice)

    def play(self, season: str, user: int, mode: str, interaction: str, now: datetime,
             style: str = "steady") -> ArcadeResult:
        self._unique_id(interaction)
        if style not in ARCADE_STYLES:
            raise WinterFunError("Unknown arcade strategy.")
        if mode not in MODES:
            raise WinterFunError("Unknown winter mini-game.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            day = self._current(con, season, user, now, active=True)
            seen = con.execute("SELECT season_key,discord_user_id,mode,score,day,equip,style FROM "
                               "arcade_events WHERE interaction_id=?", (interaction,)).fetchone()
            if seen:
                if seen[0] != season or seen[1] != user or seen[2] != mode or seen[6] != style:
                    raise WinterFunError("Interaction ID already belongs to a different mini-game.")
                prior = con.execute("SELECT MAX(score) FROM arcade_events WHERE season_key=? "
                                    "AND discord_user_id=? AND mode=?", (season, user, mode)).fetchone()
                used = con.execute("SELECT COUNT(*) FROM arcade_events WHERE season_key=? AND "
                                   "discord_user_id=? AND day=? AND mode=?", (season, user, seen[4], mode)).fetchone()
                return ArcadeResult(mode, seen[3], prior[0], used[0], seen[5], True, seen[6])
            used = int(con.execute("SELECT COUNT(*) FROM arcade_events WHERE season_key=? "
                                   "AND discord_user_id=? AND day=? AND mode=?",
                                   (season, user, day, mode)).fetchone()[0])
            if used >= DAILY_MODE_CAP:
                raise WinterFunError("You've used all three attempts in this mini-game today.")
            gear = con.execute("SELECT cosmetic_key FROM cosmetic_equipped WHERE season_key=? "
                               "AND discord_user_id=? AND category='gear'", (season, user)).fetchone()
            equip = gear[0] if gear else None
            advantage = COSMETICS[equip].arcade_bonus if equip in COSMETICS and (
                (mode == "target" and equip == "goggles") or
                (mode == "dodge" and equip == "boots") or
                (mode == "boss" and equip == "scarf")) else 0
            total = 0
            base_chance = (.65 if mode != "dodge" else .55) - (.20 if style == "risky" else 0)
            reward = 20 if style == "risky" else 10
            for _ in range(4 if mode == "boss" else 5):
                roll = self.rng.random()
                if not 0 <= roll < 1:
                    raise WinterFunError("Invalid game random roll; no attempt used.")
                if roll < base_chance + advantage:
                    total += reward + (2 if mode == "boss" and advantage else 0)
            con.execute("INSERT INTO arcade_events(interaction_id,season_key,discord_user_id,day,"
                        "mode,style,score,equip,played_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                        (interaction, season, user, day, mode, style, total, equip, _timestamp(now)))
            best = int(con.execute("SELECT MAX(score) FROM arcade_events WHERE season_key=? "
                                   "AND discord_user_id=? AND mode=?", (season, user, mode)).fetchone()[0])
            return ArcadeResult(mode, total, best, used + 1, equip, False, style)
