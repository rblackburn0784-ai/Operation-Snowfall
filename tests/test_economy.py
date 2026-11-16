"""Milestone C: deterministic item/quest/gift, concurrency and combat tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from snowfall.db.store import Store
from snowfall.services.combat import CombatEngine, CombatError
from snowfall.services.economy import (
    EconomyEngine, EconomyError, ITEM_CAPS, QUEST_TARGETS,
)

KEY = "winter-test"
START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


class Rng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    store.transition(KEY, 900, "start", START, "test")
    for i, city in [(1, "Chicago"), (2, "New York"), (3, "Detroit")]:
        store.register(KEY, i, f"player_{i}", city, START)
        CombatEngine(store).ready(KEY, i, START)
    return store


def grant(store, user=1, *, flakes=0, items=None, balls=None, warmth=None):
    e = EconomyEngine(store)
    e.inventory(KEY, user, START)
    with store.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if flakes is not None:
            c.execute("UPDATE player_resources SET snowflakes=? WHERE season_key=? "
                      "AND discord_user_id=?", (flakes, KEY, user))
        if warmth is not None:
            c.execute("UPDATE player_resources SET warmth=? WHERE season_key=? "
                      "AND discord_user_id=?", (warmth, KEY, user))
        if balls is not None:
            c.execute("UPDATE player_resources SET snowballs=? WHERE season_key=? "
                      "AND discord_user_id=?", (balls, KEY, user))
        for item, count in (items or {}).items():
            e._set_quantity(c, KEY, user, item, count)


def set_quest_eligible(store, user=1, day=1, quest="community"):
    # A legal guard action meets the temporary no-boss community objective.
    assert quest == "community" and day == 1
    EconomyEngine(store).guard(KEY, user, "on", "guard1", START)
    EconomyEngine(store).claim_quest(KEY, user, quest, START)


def test_version_4_migrated_and_existing_combat_survives(store):
    assert store.schema_version() == 4
    action = CombatEngine(store, Rng(.1)).throw(KEY, 1, 2, "quick", "base-combat", START)
    assert action.points_awarded >= 8
    store.initialize()
    assert CombatEngine(store).ledger_total(KEY, 1) == action.points_awarded
    assert EconomyEngine(store).inventory(KEY, 1, START).quantities["cocoa"] == 1


def test_starter_cocoa_only_once(store):
    e = EconomyEngine(store)
    assert e.inventory(KEY, 1, START).quantities["cocoa"] == 1
    grant(store, warmth=60)
    e.use(KEY, 1, "cocoa", "starter-cocoa", START)
    assert e.inventory(KEY, 1, START).quantities["cocoa"] == 0
    store.initialize()
    assert e.inventory(KEY, 1, START).quantities["cocoa"] == 0
    assert e.inventory(KEY, 1, START).warmth == 90


def test_craft_buys_exact_price_and_is_idempotent(store):
    grant(store, flakes=20)
    e = EconomyEngine(store)
    item = e.craft(KEY, 1, "mittens", "craft-1", START)
    assert not item.repeated
    assert e.craft(KEY, 1, "mittens", "craft-1", START).repeated
    inv = e.inventory(KEY, 1, START)
    assert inv.quantities["mittens"] == 1 and inv.snowflakes == 14
    with pytest.raises(EconomyError, match="another action"):
        e.craft(KEY, 1, "fort", "craft-1", START)


def test_craft_rejects_without_spending_and_item_capacity(store):
    e = EconomyEngine(store)
    with pytest.raises(EconomyError, match="Snowflakes"):
        e.craft(KEY, 1, "bomb", "no-flakes", START)
    grant(store, flakes=50, items={"bomb": ITEM_CAPS["bomb"]})
    with pytest.raises(EconomyError, match="maximum"):
        e.craft(KEY, 1, "bomb", "cap", START)
    assert e.inventory(KEY, 1, START).snowflakes == 50


def test_fort_discount_only_day_two(store):
    grant(store, flakes=30)
    e = EconomyEngine(store)
    e.craft(KEY, 1, "fort", "day1", START)
    assert e.inventory(KEY, 1, START).snowflakes == 20
    e.craft(KEY, 1, "fort", "day2", START + timedelta(days=1))
    assert e.inventory(KEY, 1, START + timedelta(days=1)).snowflakes == 12


def test_hot_chocolate_restores_up_to_30_and_daily_max(store):
    grant(store, items={"cocoa": 3}, warmth=10)
    e = EconomyEngine(store)
    e.use(KEY, 1, "cocoa", "coco1", START)
    e.use(KEY, 1, "cocoa", "coco2", START)
    assert e.inventory(KEY, 1, START).warmth == 70
    with pytest.raises(EconomyError, match="Daily use limit"):
        e.use(KEY, 1, "cocoa", "coco3", START)
    assert e.inventory(KEY, 1, START).quantities["cocoa"] == 1


def test_item_deploys_armour_and_blocks_second_fort(store):
    grant(store, items={"fort": 2})
    e = EconomyEngine(store)
    e.use(KEY, 1, "fort", "fort1", START)
    assert e.inventory(KEY, 1, START).armour_hp == 25
    with pytest.raises(EconomyError, match="current snow fort"):
        e.use(KEY, 1, "fort", "fort2", START)
    assert e.inventory(KEY, 1, START + timedelta(hours=6)).armour_hp == 0
    e.use(KEY, 1, "fort", "fort2", START + timedelta(hours=6))
    assert e.inventory(KEY, 1, START + timedelta(hours=6)).armour_hp == 25


def test_mittens_hit_chance_and_buff_consumed_on_miss(store):
    grant(store, items={"mittens": 1})
    e = EconomyEngine(store)
    e.use(KEY, 1, "mittens", "arm-mittens", START)
    # Quick 75% + 10% = 85%, so 0.80 hits; 0.90 misses.
    result = CombatEngine(store, Rng(.90)).throw(KEY, 1, 2, "quick", "miss-with-mittens", START)
    assert not result.hit and result.modifier_item == "mittens"
    assert not e.inventory(KEY, 1, START).mittens_armed
    result = CombatEngine(store, Rng(.80)).throw(
        KEY, 1, 3, "quick", "no-buff", START + timedelta(seconds=31))
    assert not result.hit


def test_bomb_boosts_only_power_and_is_consumed(store):
    grant(store, items={"bomb": 1})
    e = EconomyEngine(store)
    e.use(KEY, 1, "bomb", "arm-bomb", START)
    with pytest.raises(CombatError, match="Power Shot"):
        CombatEngine(store).throw(KEY, 1, 2, "quick", "no-quick", START)
    assert e.inventory(KEY, 1, START).bomb_armed
    attack = CombatEngine(store, Rng(.1)).throw(KEY, 1, 2, "power", "yes-power", START)
    assert attack.hit and attack.warmth_damage == 29
    assert attack.item_bonus_points == 5 and attack.modifier_item == "bomb"
    assert not e.inventory(KEY, 1, START).bomb_armed


def test_guard_reduces_accuracy_and_warmth_damage(store):
    EconomyEngine(store).guard(KEY, 2, "on", "guard-target", START)
    # Quick goes from 75% to 65%; at .70 this misses.
    miss = CombatEngine(store, Rng(.70)).throw(KEY, 1, 2, "quick", "guard-miss", START)
    assert not miss.hit and miss.guarded
    attack = CombatEngine(store, Rng(.1)).throw(KEY, 1, 2, "quick",
                                              "guard-hit", START + timedelta(seconds=31))
    assert attack.hit and attack.warmth_damage == 6
    with pytest.raises(CombatError, match="Lower your guard"):
        CombatEngine(store).throw(KEY, 2, 1, "quick", "guard-block", START)


def test_guard_expiration_and_cooldown_are_pause_aware(store):
    e = EconomyEngine(store)
    e.guard(KEY, 1, "on", "on", START)
    with pytest.raises(EconomyError, match="already active"):
        e.guard(KEY, 1, "on", "twice", START)
    e.guard(KEY, 1, "off", "off", START + timedelta(minutes=1))
    with pytest.raises(EconomyError, match="2-hour"):
        e.guard(KEY, 1, "on", "too-soon", START + timedelta(hours=1))
    store.transition(KEY, 900, "pause", START + timedelta(hours=1), "Pause")
    with pytest.raises(EconomyError, match="LIVE"):
        e.guard(KEY, 1, "on", "paused", START + timedelta(hours=3))
    store.transition(KEY, 900, "resume", START + timedelta(hours=4), "Resume")
    with pytest.raises(EconomyError, match="2-hour"):
        e.guard(KEY, 1, "on", "still-too-soon", START + timedelta(hours=4))
    e.guard(KEY, 1, "on", "ready", START + timedelta(hours=5))


def test_quest_progress_from_combat_and_exactly_once(store):
    e = EconomyEngine(store)
    assert all(q.progress == 0 for q in e.quests(KEY, 1, START))
    # Five legal misses satisfy the throwing objective, but not the two rival hits.
    for i in range(5):
        CombatEngine(store, Rng(.99)).throw(KEY, 1, 2, "quick",
                                           f"throw{i}", START + timedelta(seconds=31*i))
    quests = {q.key: q for q in e.quests(KEY, 1, START + timedelta(minutes=3))}
    assert quests["throws"].progress == 5 and quests["rivals"].progress == 0
    with pytest.raises(EconomyError, match="not complete"):
        e.claim_quest(KEY, 1, "rivals", START + timedelta(minutes=3))
    assert not e.claim_quest(KEY, 1, "throws", START + timedelta(minutes=3)).repeated
    assert e.claim_quest(KEY, 1, "throws", START + timedelta(minutes=3)).repeated
    assert CombatEngine(store).ledger_total(KEY, 1) == 20
    assert e.inventory(KEY, 1, START + timedelta(minutes=3)).snowflakes == 2
    assert e.quests(KEY, 1, START + timedelta(days=1))[0].progress == 0


def test_quest_community_fallback_guard_claim_and_present(store):
    e = EconomyEngine(store, Rng(.01))
    e.guard(KEY, 1, "on", "start-guard", START)
    community = [q for q in e.quests(KEY, 1, START) if q.key == "community"][0]
    assert community.progress == QUEST_TARGETS["community"]
    e.claim_quest(KEY, 1, "community", START)
    assert CombatEngine(store).ledger_total(KEY, 1) == 20
    # During guard, cannot attack but may claim a present.
    gift = e.present(KEY, 1, "gift1", START)
    assert gift.reward == "snowballs"
    assert e.present(KEY, 1, "gift1", START).repeated
    assert e.present(KEY, 1, "gift2", START).repeated
    assert CombatEngine(store).ledger_total(KEY, 1) == 20


def test_daily_gift_requires_quest_claim_and_not_just_progress(store):
    e = EconomyEngine(store)
    with pytest.raises(EconomyError, match="Claim a daily quest"):
        e.present(KEY, 1, "gift-no-quest", START)
    e.guard(KEY, 1, "on", "guard-to-claim", START)
    with pytest.raises(EconomyError, match="Claim a daily quest"):
        e.present(KEY, 1, "gift-no-claim", START)
    e.claim_quest(KEY, 1, "community", START)
    e.present(KEY, 1, "gift-after", START)


@pytest.mark.parametrize("roll,reward", [
    (0.0, "snowballs"), (.399, "snowballs"), (.4, "cocoa"), (.649, "cocoa"),
    (.65, "mittens"), (.849, "mittens"), (.85, "fort"), (.949, "fort"),
    (.95, "bomb"), (.989, "bomb"), (.99, "golden"), (.999, "golden")])
def test_gift_probability_boundaries(roll, reward):
    assert EconomyEngine._gift_reward(roll) == reward


def test_gift_full_inventory_substitutes_five_flakes(store):
    e = EconomyEngine(store, Rng(.50))
    set_quest_eligible(store)
    grant(store, flakes=20, items={"cocoa": 3})
    gift = e.present(KEY, 1, "gift-full", START)
    assert (gift.reward, gift.actual_reward) == ("cocoa", "snowflakes")
    assert e.inventory(KEY, 1, START).snowflakes == 25


def test_golden_once_per_season_and_special_throw(store):
    e = EconomyEngine(store, Rng(.999))
    set_quest_eligible(store)
    first = e.present(KEY, 1, "golden-1", START)
    assert first.actual_reward == "golden"
    inv = e.inventory(KEY, 1, START)
    assert inv.quantities["golden"] == 1
    # Golden is ammo itself: no standard snowball is spent.
    grant(store, flakes=0, balls=0)
    e.guard(KEY, 1, "off", "guard-off-golden", START)
    result = CombatEngine(store, Rng(.1)).throw(KEY, 1, 2, "golden", "golden-throw", START)
    assert result.hit and result.points_awarded > 0 and result.city_credit <= 10
    inv = e.inventory(KEY, 1, START)
    assert inv.quantities["golden"] == 0
    assert CombatEngine(store).snapshot(KEY, 1, START).snowballs == 0
    with pytest.raises(CombatError, match="Golden Snowball"):
        CombatEngine(store).throw(KEY, 1, 3, "golden", "golden-again",
                                      START + timedelta(seconds=31))
    # New day, a second Golden roll is substituted, not a second golden item.
    e.guard(KEY, 1, "on", "guard-next-day", START + timedelta(days=1))
    e.claim_quest(KEY, 1, "community", START + timedelta(days=1))
    second = e.present(KEY, 1, "golden-2", START + timedelta(days=1))
    assert second.actual_reward == "snowflakes"
    assert e.inventory(KEY, 1, START + timedelta(days=1)).quantities["golden"] == 0


def test_golden_transactional_replay_no_second_consumption(store):
    e = EconomyEngine(store, Rng(.999))
    set_quest_eligible(store)
    e.present(KEY, 1, "gold", START)
    e.guard(KEY, 1, "off", "guard-off-before-throw", START)
    engine = CombatEngine(store, Rng(.1))
    one = engine.throw(KEY, 1, 2, "golden", "the-gold", START)
    again = engine.throw(KEY, 1, 2, "golden", "the-gold", START + timedelta(minutes=3))
    assert one.points_awarded == again.points_awarded and again.repeated
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM item_events WHERE operation='use' "
                           "AND item_key='golden'").fetchone()[0] == 1


def test_day_four_bonus_requires_three_claims_and_never_golden(store):
    e = EconomyEngine(store, Rng(.999))
    with pytest.raises(EconomyError, match="Claim a daily quest"):
        e.present(KEY, 1, "extra-too-soon", START + timedelta(days=3), "bonus")
    # Simulate legitimate quest completions in game-day-four ledger.
    at = START + timedelta(days=3)
    with store.connect() as c:
        for quest in QUEST_TARGETS:
            c.execute("INSERT INTO quest_claims VALUES (?,?,?,?,?,?)",
                      (KEY, 1, 4, quest, 20, at.isoformat()))
    gift = e.present(KEY, 1, "extra", at, "bonus")
    assert (gift.reward, gift.actual_reward) == ("golden", "snowflakes")
    assert e.present(KEY, 1, "extra2", at, "bonus").repeated
    assert e.inventory(KEY, 1, at).quantities["golden"] == 0


def test_reject_during_pause_no_item_spend(store):
    grant(store, flakes=30)
    store.transition(KEY, 900, "pause", START + timedelta(hours=1), "pause")
    e = EconomyEngine(store)
    with pytest.raises(EconomyError, match="LIVE"):
        e.craft(KEY, 1, "fort", "during-pause", START + timedelta(hours=2))
    assert e.inventory(KEY, 1, START + timedelta(hours=2)).snowflakes == 30


def test_craft_race_spends_funds_once(store):
    grant(store, flakes=8)
    def run(i):
        try:
            EconomyEngine(store).craft(KEY, 1, "cocoa", f"race-{i}", START)
            return True
        except EconomyError:
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run, range(6)))
    assert sum(results) == 1
    inv = EconomyEngine(store).inventory(KEY, 1, START)
    assert inv.snowflakes == 0 and inv.quantities["cocoa"] == 2


def test_no_mutation_of_history(store):
    e = EconomyEngine(store)
    e.guard(KEY, 1, "on", "guard-1", START)
    e.claim_quest(KEY, 1, "community", START)
    e.present(KEY, 1, "gift1", START)
    with store.connect() as c:
        for table in ("item_events", "quest_claims", "mystery_gifts"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                c.execute(f"DELETE FROM {table}")


def test_quest_daily_60_point_ceiling_and_ledger(store):
    e = EconomyEngine(store)
    # Community quest: an actual guard activation (no free score until claimed).
    e.guard(KEY, 1, "on", "guard-day", START)
    e.guard(KEY, 1, "off", "lower-day", START)
    # Two successful hits on distinct rivals; remaining three legal misses.
    for i in range(5):
        rng = Rng(.1 if i < 2 else .99)
        target = 2 if i % 2 == 0 else 3
        CombatEngine(store, rng).throw(KEY, 1, target, "quick", f"daily-throw-{i}",
                                       START + timedelta(seconds=31 * i))
    board = {q.key: q for q in e.quests(KEY, 1, START + timedelta(minutes=3))}
    assert all(q.progress >= q.target for q in board.values())
    for key in QUEST_TARGETS:
        e.claim_quest(KEY, 1, key, START + timedelta(minutes=3))
    with store.connect() as c:
        score = c.execute("SELECT SUM(points) FROM score_ledger "
                          "WHERE season_key=? AND player_id=? AND day=? AND category='quest'",
                          (KEY, 1, 1)).fetchone()[0]
        assert score == 60
        assert c.execute("SELECT COUNT(*) FROM quest_claims WHERE season_key=? "
                         "AND discord_user_id=? AND day=1", (KEY, 1)).fetchone()[0] == 3
    assert EconomyEngine(store).inventory(KEY, 1, START + timedelta(minutes=3)).snowflakes >= 6


def test_gift_concurrency_only_one_reward(store):
    set_quest_eligible(store)
    def claim(i):
        return EconomyEngine(store, Rng(.50)).present(KEY, 1, f"gift-parallel-{i}", START)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert sum(not x.repeated for x in results) == 1
    assert EconomyEngine(store).inventory(KEY, 1, START).quantities["cocoa"] == 2


def test_invalid_and_cross_player_interaction_ids(store):
    grant(store, flakes=30)
    e = EconomyEngine(store)
    with pytest.raises(EconomyError, match="unique Discord"):
        e.craft(KEY, 1, "cocoa", "", START)
    e.craft(KEY, 1, "cocoa", "same-action", START)
    with pytest.raises(EconomyError, match="already used"):
        e.craft(KEY, 2, "cocoa", "same-action", START)


def test_migration_from_v3_keeps_combat_and_players(tmp_path):
    path = tmp_path / "legacy-v3.sqlite3"
    store = Store(path)
    store.initialize()
    store.ensure_season(KEY, START)
    store.transition(KEY, 900, "start", START, "launch")
    store.register(KEY, 1, "ExistingName", "Chicago", START)
    store.register(KEY, 2, "ExistingRival", "New York", START)
    CombatEngine(store).ready(KEY, 2, START)
    CombatEngine(store, Rng(.1)).throw(KEY, 1, 2, "quick", "legacy-throw", START)
    before = CombatEngine(store).ledger_total(KEY, 1)
    with store.connect() as c:
        for table in ("item_events", "quest_claims", "mystery_gifts"):
            for suffix in ("immutable_update", "immutable_delete"):
                c.execute(f"DROP TRIGGER IF EXISTS {table}_{suffix}")
            c.execute(f"DROP TABLE IF EXISTS {table}")
        c.execute("DROP TABLE IF EXISTS player_inventory")
        c.execute("DROP TABLE IF EXISTS player_economy")
        # Recreate an actual v3 combat_events shape with immutable triggers intact.
        for column in ("modifier_item", "guarded", "item_bonus_points", "city_credit"):
            c.execute(f"ALTER TABLE combat_events DROP COLUMN {column}")
        c.execute("PRAGMA user_version=3")
    store.initialize()
    store.initialize()
    assert store.schema_version() == 4
    assert CombatEngine(store).ledger_total(KEY, 1) == before
    with store.connect() as c:
        event = c.execute("SELECT city_credit FROM combat_events "
                          "WHERE interaction_id='legacy-throw'").fetchone()
        assert event[0] is None  # preserve immutable v3 history
    replay = CombatEngine(store).throw(KEY, 1, 2, "quick", "legacy-throw", START)
    assert replay.city_credit == before and replay.repeated
    assert store.get_player(KEY, 1).mr_username == "ExistingName"
    assert EconomyEngine(store).inventory(KEY, 1, START).quantities["cocoa"] == 1


def test_cocoa_not_usable_during_knockout(store):
    grant(store, warmth=0)
    with store.connect() as c:
        c.execute("UPDATE player_resources SET knockout_until=? WHERE season_key=? "
                  "AND discord_user_id=?", ((START + timedelta(minutes=30)).isoformat(), KEY, 1))
    with pytest.raises(EconomyError, match="knockout"):
        EconomyEngine(store).use(KEY, 1, "cocoa", "ko-cocoa", START)
    assert EconomyEngine(store).inventory(KEY, 1, START).quantities["cocoa"] == 1


def test_quest_and_gifts_do_not_exceed_snowflake_cap(store):
    grant(store, flakes=99)
    e = EconomyEngine(store, Rng(.5))
    e.guard(KEY, 1, "on", "guard-cap", START)
    result = e.claim_quest(KEY, 1, "community", START)
    assert "+1 Snowflakes" in result.text
    grant(store, flakes=100, items={"cocoa": 3})
    gift = e.present(KEY, 1, "flk-gift", START)
    assert gift.actual_reward == "snowflakes" and gift.amount == 0
    assert e.inventory(KEY, 1, START).snowflakes == 100
