"""v0.1.3 transactional items, daily quests, guarding and mystery gifts.

No Discord dependency. All mutations use SQLite BEGIN IMMEDIATE and a unique
interaction ID; effective event timestamps freeze while the season is paused.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import secrets
import sqlite3
from typing import Protocol

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _parse, _timestamp
from snowfall.services.combat import CombatEngine, CombatError, _game_now, SNOWFLAKE_CAP

ITEM_CAPS = {"cocoa": 3, "fort": 2, "mittens": 2, "bomb": 2, "golden": 1}
ITEM_COSTS = {"cocoa": 8, "fort": 10, "mittens": 6, "bomb": 15}
ITEM_NAMES = {"cocoa": "Hot Chocolate", "fort": "Fort Kit", "mittens": "Precision Mittens",
              "bomb": "Blizzard Bomb", "golden": "Golden Snowball"}
DAILY_USE_CAPS = {"cocoa": 2, "fort": 2, "mittens": 2, "bomb": 1, "golden": 1}
QUEST_TARGETS = {"throws": 5, "rivals": 2, "community": 1}
QUEST_NAMES = {"throws": "Get your gloves on", "rivals": "Spread the misery",
               "community": "Winter preparation"}


class EconomyError(CombatError):
    """A rejected economy action; no items or points were spent."""


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class InventoryView:
    day: int | None
    quantities: dict[str, int]
    snowflakes: int
    warmth: int
    armour_hp: int
    guard_until: datetime | None
    mittens_armed: bool
    bomb_armed: bool
    uses_today: dict[str, int]
    next_guard_at: datetime | None
    guard_active: bool


@dataclass(frozen=True)
class QuestView:
    key: str
    name: str
    progress: int
    target: int
    claimed: bool


@dataclass(frozen=True)
class ActionResult:
    text: str
    repeated: bool = False


@dataclass(frozen=True)
class GiftResult:
    reward: str
    actual_reward: str
    source: str
    repeated: bool = False
    amount: int = 0


class EconomyEngine:
    @staticmethod
    def _validate_interaction(interaction: str) -> None:
        if not isinstance(interaction, str) or not 1 <= len(interaction) <= 128:
            raise EconomyError("A unique Discord interaction ID is required.")

    def __init__(self, store: Store, rng: RandomSource | None = None):
        self.store = store
        self.rng = rng if rng is not None else secrets.SystemRandom()

    @staticmethod
    def _initialize(con: sqlite3.Connection, season: str, user_id: int) -> sqlite3.Row:
        """Seed starter cocoa exactly once, including for migrated players."""
        inserted = con.execute(
            "INSERT OR IGNORE INTO player_economy(season_key,discord_user_id) VALUES (?,?)",
            (season, user_id),
        ).rowcount
        if inserted:
            con.execute("""INSERT INTO player_inventory
                (season_key,discord_user_id,item_key,quantity) VALUES (?,?,?,1)""",
                (season, user_id, "cocoa"))
        return con.execute("SELECT * FROM player_economy "
                           "WHERE season_key=? AND discord_user_id=?",
                           (season, user_id)).fetchone()

    @staticmethod
    def _quantity(con: sqlite3.Connection, season: str, user: int, item: str) -> int:
        row = con.execute("SELECT quantity FROM player_inventory WHERE season_key=? "
                          "AND discord_user_id=? AND item_key=?", (season, user, item)).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _set_quantity(con: sqlite3.Connection, season: str, user: int,
                      item: str, value: int) -> None:
        if not 0 <= value <= ITEM_CAPS[item]:
            raise EconomyError("Item storage cap would be exceeded.")
        con.execute("""INSERT INTO player_inventory
            (season_key,discord_user_id,item_key,quantity) VALUES (?,?,?,?)
            ON CONFLICT(season_key,discord_user_id,item_key)
            DO UPDATE SET quantity=excluded.quantity""", (season, user, item, value))

    @staticmethod
    def _need_live(con, season: str, user: int, now: datetime):
        state = CombatEngine._season(con, season)
        if state.phase(now) != "live":
            raise EconomyError("Economy actions are available only while the event is LIVE.")
        try:
            player = CombatEngine._player(con, season, user)
        except CombatError as exc:
            raise EconomyError(str(exc)) from exc
        return state, player, _game_now(state, now), state.day(now)

    @staticmethod
    def _record(con, interaction: str, season: str, user: int, day: int,
                operation: str, item: str, text: str, now: datetime, game_now: datetime):
        con.execute("""INSERT INTO item_events(interaction_id,season_key,discord_user_id,
            day,operation,item_key,detail,happened_at_utc,effective_at_utc)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (interaction, season, user, day, operation, item,
             json.dumps({"text": text}), _timestamp(now), _timestamp(game_now)))

    @staticmethod
    def _repeated(con, interaction: str, season: str, user: int,
                  operation: str, item: str) -> ActionResult | None:
        existing = con.execute("SELECT * FROM item_events WHERE interaction_id=?",
                               (interaction,)).fetchone()
        if existing is None:
            return None
        if (existing["season_key"], existing["discord_user_id"],
            existing["operation"], existing["item_key"]) != (season, user, operation, item):
            raise EconomyError("This interaction ID was already used for another action.")
        return ActionResult(json.loads(existing["detail"])["text"], repeated=True)

    def inventory(self, season: str, user: int, now: datetime) -> InventoryView:
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            season_state = CombatEngine._season(con, season)
            try:
                CombatEngine._player(con, season, user)
            except CombatError as exc:
                raise EconomyError(str(exc)) from exc
            game_now = _game_now(season_state, now) if season_state.started_at else now
            econ = self._initialize(con, season, user)
            if season_state.started_at:
                resource = CombatEngine(self.store)._resources(con, season, user, game_now)
                snowflakes, warmth, armour = (resource["snowflakes"], resource["warmth"],
                                              resource["armour_hp"])
            else:
                snowflakes, warmth, armour = 0, 100, 0
            day = season_state.day(now)
            quantities = {k: self._quantity(con, season, user, k) for k in ITEM_CAPS}
            counts = {k: int(con.execute("SELECT COUNT(*) FROM item_events WHERE "
                         "season_key=? AND discord_user_id=? AND day=? AND operation='use' "
                         "AND item_key=?", (season, user, day, k)).fetchone()[0])
                      if day is not None else 0 for k in DAILY_USE_CAPS}
            last = _parse(econ["guard_last_started_at"])
            return InventoryView(day, quantities, snowflakes, warmth, armour,
                                 _parse(econ["guard_until"]), bool(econ["mittens_armed"]),
                                 bool(econ["bomb_armed"]), counts,
                                 last + timedelta(hours=2) if last else None,
                                 (_parse(econ["guard_until"]) or game_now) > game_now)

    def craft(self, season: str, user: int, item: str, interaction: str,
              now: datetime) -> ActionResult:
        if item not in ITEM_COSTS:
            raise EconomyError("Only Hot Chocolate, Fort Kits, Mittens and Bombs can be crafted.")
        self._validate_interaction(interaction)
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if result := self._repeated(con, interaction, season, user, "craft", item):
                return result
            _, _, game_now, day = self._need_live(con, season, user, now)
            self._initialize(con, season, user)
            r = CombatEngine(self.store)._resources(con, season, user, game_now)
            price = ITEM_COSTS[item] - (2 if item == "fort" and day == 2 else 0)
            if self._quantity(con, season, user, item) >= ITEM_CAPS[item]:
                raise EconomyError("You already hold the maximum of that item.")
            if r["snowflakes"] < price:
                raise EconomyError(f"You need {price} Snowflakes to craft {ITEM_NAMES[item]}.")
            self._set_quantity(con, season, user, item,
                               self._quantity(con, season, user, item) + 1)
            con.execute("UPDATE player_resources SET snowflakes=snowflakes-? WHERE "
                        "season_key=? AND discord_user_id=?", (price, season, user))
            text = f"Crafted {ITEM_NAMES[item]} for {price} Snowflakes."
            self._record(con, interaction, season, user, day, "craft", item, text, now, game_now)
            return ActionResult(text)

    def use(self, season: str, user: int, item: str, interaction: str,
            now: datetime) -> ActionResult:
        if item not in ("cocoa", "fort", "mittens", "bomb"):
            raise EconomyError("Golden Snowballs are used through the Throw menu, not /snow use.")
        self._validate_interaction(interaction)
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if result := self._repeated(con, interaction, season, user, "use", item):
                return result
            _, _, game_now, day = self._need_live(con, season, user, now)
            econ = self._initialize(con, season, user)
            r = CombatEngine(self.store)._resources(con, season, user, game_now)
            used = con.execute("SELECT COUNT(*) FROM item_events WHERE season_key=? "
                               "AND discord_user_id=? AND day=? AND operation='use' "
                               "AND item_key=?", (season, user, day, item)).fetchone()[0]
            if used >= DAILY_USE_CAPS[item]:
                raise EconomyError(f"Daily use limit reached for {ITEM_NAMES[item]}.")
            if self._quantity(con, season, user, item) == 0:
                raise EconomyError(f"You have no {ITEM_NAMES[item]} left.")
            if r["knockout_until"] is not None:
                raise EconomyError("Items cannot be activated during knockout recovery.")
            if item == "cocoa":
                if r["warmth"] >= 100:
                    raise EconomyError("You're already at maximum warmth.")
                gained = min(30, 100 - r["warmth"])
                con.execute("UPDATE player_resources SET warmth=warmth+?, warmth_regen_at=? "
                            "WHERE season_key=? AND discord_user_id=?",
                            (gained, _timestamp(game_now) if r["warmth"]+gained == 100
                             else r["warmth_regen_at"], season, user))
                text = f"Hot Chocolate restored {gained} warmth. ☕"
            elif item == "fort":
                if r["armour_hp"] > 0:
                    raise EconomyError("Your current snow fort must expire or be destroyed first.")
                con.execute("UPDATE player_resources SET armour_hp=25, armour_expires_at=? "
                            "WHERE season_key=? AND discord_user_id=?",
                            (_timestamp(game_now + timedelta(hours=6)), season, user))
                text = "Fort deployed: 25 armour for up to 6 active hours. 🏰"
            elif item == "mittens":
                if econ["mittens_armed"]:
                    raise EconomyError("Mittens are already armed for your next legal throw.")
                con.execute("UPDATE player_economy SET mittens_armed=1 WHERE "
                            "season_key=? AND discord_user_id=?", (season, user))
                text = "Mittens armed: +10 percentage points accuracy on the next legal throw. 🧤"
            else:
                if econ["bomb_armed"]:
                    raise EconomyError("Blizzard Bomb is already armed.")
                con.execute("UPDATE player_economy SET bomb_armed=1 WHERE "
                            "season_key=? AND discord_user_id=?", (season, user))
                text = "Blizzard Bomb armed: next legal Power Shot gets +7 damage and +5 hit points. 💣"
            self._set_quantity(con, season, user, item,
                               self._quantity(con, season, user, item) - 1)
            self._record(con, interaction, season, user, day, "use", item, text, now, game_now)
            return ActionResult(text)

    def guard(self, season: str, user: int, mode: str, interaction: str,
              now: datetime) -> ActionResult:
        if mode not in ("on", "off"):
            raise EconomyError("Choose guard on or guard off.")
        self._validate_interaction(interaction)
        now = as_utc(now)
        operation = "guard_" + mode
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if result := self._repeated(con, interaction, season, user, operation, "guard"):
                return result
            _, _, game_now, day = self._need_live(con, season, user, now)
            econ = self._initialize(con, season, user)
            r = CombatEngine(self.store)._resources(con, season, user, game_now)
            guarded = (_parse(econ["guard_until"]) or game_now) > game_now
            if mode == "on":
                if r["knockout_until"] is not None:
                    raise EconomyError("Cannot guard while knocked out.")
                if guarded:
                    raise EconomyError("Guard is already active.")
                last = _parse(econ["guard_last_started_at"])
                if last and game_now - last < timedelta(hours=2):
                    raise EconomyError("Guard has a 2-hour activation cooldown.")
                con.execute("UPDATE player_economy SET guard_until=?,guard_last_started_at=? "
                            "WHERE season_key=? AND discord_user_id=?",
                            (_timestamp(game_now + timedelta(minutes=30)),
                             _timestamp(game_now), season, user))
                text = "Guard activated for 30 active minutes. You cannot throw while guarding. 🛡️"
            else:
                if not guarded:
                    raise EconomyError("Guard is not active.")
                con.execute("UPDATE player_economy SET guard_until=NULL "
                            "WHERE season_key=? AND discord_user_id=?", (season, user))
                text = "Guard lowered. Your 2-hour activation cooldown continues."
            self._record(con, interaction, season, user, day, operation, "guard", text, now, game_now)
            return ActionResult(text)

    @staticmethod
    def _quest_progress(con: sqlite3.Connection, season: str, user: int, day: int):
        attempts = int(con.execute("SELECT COUNT(*) FROM combat_events WHERE season_key=? "
                   "AND attacker_id=? AND day=?", (season, user, day)).fetchone()[0])
        rivals = int(con.execute("SELECT COUNT(DISTINCT target_id) FROM combat_events "
                   "WHERE season_key=? AND attacker_id=? AND day=? AND hit=1 "
                   "AND points_awarded>0", (season, user, day)).fetchone()[0])
        community = int(con.execute("SELECT COUNT(*) FROM item_events WHERE season_key=? "
                       "AND discord_user_id=? AND day=? "
                       "AND operation IN ('craft','use','guard_on')",
                       (season, user, day)).fetchone()[0])
        return {"throws": attempts, "rivals": rivals, "community": community}

    def quests(self, season: str, user: int, now: datetime) -> list[QuestView]:
        now = as_utc(now)
        with self.store.connect() as con:
            state = CombatEngine._season(con, season)
            try:
                CombatEngine._player(con, season, user)
            except CombatError as exc:
                raise EconomyError(str(exc)) from exc
            day = state.day(now)
            if day is None:
                return [QuestView(k, QUEST_NAMES[k], 0, t, False)
                        for k, t in QUEST_TARGETS.items()]
            progress = self._quest_progress(con, season, user, day)
            claimed = {r[0] for r in con.execute("SELECT quest_key FROM quest_claims "
                           "WHERE season_key=? AND discord_user_id=? AND day=?",
                           (season, user, day)).fetchall()}
            return [QuestView(k, QUEST_NAMES[k], min(progress[k], t), t, k in claimed)
                    for k, t in QUEST_TARGETS.items()]

    def claim_quest(self, season: str, user: int, quest: str, now: datetime) -> ActionResult:
        if quest not in QUEST_TARGETS:
            raise EconomyError("Unknown daily objective.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            _, player, game_now, day = self._need_live(con, season, user, now)
            self._initialize(con, season, user)
            if con.execute("SELECT 1 FROM quest_claims WHERE season_key=? "
                           "AND discord_user_id=? AND day=? AND quest_key=?",
                           (season, user, day, quest)).fetchone():
                return ActionResult(f"{QUEST_NAMES[quest]} was already claimed today.", repeated=True)
            progress = self._quest_progress(con, season, user, day)[quest]
            if progress < QUEST_TARGETS[quest]:
                raise EconomyError(f"Objective not complete: {progress}/{QUEST_TARGETS[quest]}.")
            resource = CombatEngine(self.store)._resources(con, season, user, game_now)
            flakes_granted = min(2, SNOWFLAKE_CAP - resource["snowflakes"])
            con.execute("INSERT INTO quest_claims(season_key,discord_user_id,day,quest_key,"
                        "points,claimed_at_utc) VALUES (?,?,?,?,20,?)",
                        (season, user, day, quest, _timestamp(now)))
            con.execute("""INSERT INTO score_ledger
                (season_key,day,player_id,city,category,points,source_key,created_at_utc)
                VALUES(?,?,?,?,'quest',20,?,?)""",
                (season, day, user, player["city"], f"quest:{day}:{quest}", _timestamp(now)))
            con.execute("UPDATE player_resources SET snowflakes=MIN(?,snowflakes+2), "
                        "last_scored_action_at=?, last_eligible_action_at=? "
                        "WHERE season_key=? AND discord_user_id=?",
                        (SNOWFLAKE_CAP, _timestamp(game_now), _timestamp(game_now), season, user))
            return ActionResult(f"✅ {QUEST_NAMES[quest]} complete! +20 points and "
                                f"+{flakes_granted} Snowflakes.")

    @staticmethod
    def _gift_reward(roll: float) -> str:
        if not 0 <= roll < 1:
            raise EconomyError("Gift RNG returned an invalid value.")
        if roll < .40:
            return "snowballs"
        if roll < .65:
            return "cocoa"
        if roll < .85:
            return "mittens"
        if roll < .95:
            return "fort"
        if roll < .99:
            return "bomb"
        return "golden"

    def present(self, season: str, user: int, interaction: str,
                now: datetime, source: str = "daily") -> GiftResult:
        if source not in ("daily", "bonus"):
            raise EconomyError("Unknown present type.")
        self._validate_interaction(interaction)
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # Interaction reuse must not cross gift operation or account.
            collision = con.execute("SELECT * FROM mystery_gifts WHERE interaction_id=?",
                                    (interaction,)).fetchone()
            if collision and (collision["season_key"], collision["discord_user_id"],
                              collision["source"]) != (season, user, source):
                raise EconomyError("Interaction ID was used for another present.")
            if collision:
                return GiftResult(collision["reward"], collision["actual_reward"], source, True,
                                  collision["amount"])
            _, _, game_now, day = self._need_live(con, season, user, now)
            self._initialize(con, season, user)
            prior = con.execute("SELECT * FROM mystery_gifts WHERE season_key=? "
                                "AND discord_user_id=? AND day=? AND source=?",
                                (season, user, day, source)).fetchone()
            if prior:
                return GiftResult(prior["reward"], prior["actual_reward"], source, True,
                                  prior["amount"])
            claimed = con.execute("SELECT COUNT(*) FROM quest_claims WHERE season_key=? "
                                  "AND discord_user_id=? AND day=?",
                                  (season, user, day)).fetchone()[0]
            if (source == "daily" and claimed < 1) or (source == "bonus" and
                                                      (day != 4 or claimed < 3)):
                raise EconomyError("Claim a daily quest before opening your present "
                                   "(all three for Day 4's extra present).")
            r = CombatEngine(self.store)._resources(con, season, user, game_now)
            roll = self.rng.random()
            item = self._gift_reward(roll)
            actual = item
            amount = 1
            if item == "golden" and source == "bonus":
                actual = "snowflakes"
            elif item == "golden":
                economy = self._initialize(con, season, user)
                if economy["golden_awarded"]:
                    actual = "snowflakes"
            if actual == "snowballs":
                if r["snowballs"] >= 12:
                    actual = "snowflakes"
                else:
                    amount = min(3, 12 - r["snowballs"])
                    con.execute("UPDATE player_resources SET snowballs=MIN(12,snowballs+3) "
                                "WHERE season_key=? AND discord_user_id=?", (season, user))
            elif actual in ITEM_CAPS:
                quantity = self._quantity(con, season, user, actual)
                if quantity >= ITEM_CAPS[actual]:
                    actual = "snowflakes"
                else:
                    self._set_quantity(con, season, user, actual, quantity + 1)
                    if actual == "golden":
                        con.execute("UPDATE player_economy SET golden_awarded=1 "
                                    "WHERE season_key=? AND discord_user_id=?", (season, user))
            if actual == "snowflakes":
                amount = min(5, 100 - r["snowflakes"])
                con.execute("UPDATE player_resources SET snowflakes=MIN(100,snowflakes+5) "
                            "WHERE season_key=? AND discord_user_id=?", (season, user))
            con.execute("""INSERT INTO mystery_gifts(season_key,discord_user_id,day,
                source,interaction_id,reward,actual_reward,roll,amount,claimed_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (season, user, day, source, interaction, item, actual, roll,
                 amount, _timestamp(now)))
            return GiftResult(item, actual, source, amount=amount)
