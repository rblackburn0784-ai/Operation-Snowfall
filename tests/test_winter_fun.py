"""v0.2.0 activity isolation, purchase atomicity, replay and mission rotation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from snowfall.db.store import Store
from snowfall.services.combat import CombatEngine
from snowfall.services.economy import EconomyEngine
from snowfall.services.daily_missions import missions_for_day, daily_progress
from snowfall.services.winter_fun import (
    COSMETICS, DAILY_MODE_CAP, WinterFunEngine, WinterFunError,
)

START = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
KEY = "winter-2026"


class FixedRNG:
    def __init__(self, value=0.0):
        self.value = value

    def random(self):
        return self.value


@pytest.fixture
def game(tmp_path):
    db = Store(tmp_path / "snow.sqlite3")
    db.initialize()
    db.ensure_season(KEY, START)
    for number, city in [(101, "Chicago"), (102, "New York")]:
        db.register(KEY, number, f"Player{number}", city, START - timedelta(days=1))
    db.transition(KEY, 999, "start", START, "host launched")
    return db


def test_schema_reinitializes_and_preserves_immutable_score(game):
    assert game.schema_version() == 8
    with game.connect() as con:
        con.execute("INSERT INTO score_ledger (season_key,day,player_id,city,category,"
                    "points,source_key,created_at_utc) VALUES (?,?,?,?,'quest',20,?,?)",
                    (KEY, 1, 101, "Chicago", "prior", START.isoformat()))
    game.initialize()
    assert game.schema_version() == 8
    with game.connect() as con:
        assert con.execute("SELECT SUM(points) FROM score_ledger WHERE season_key=?", (KEY,)).fetchone()[0] == 20
        for table in ("cosmetic_unlocks", "cosmetic_equipped", "cosmetic_purchases", "arcade_events", "encounter_events"):
            assert con.execute("SELECT name FROM sqlite_master WHERE name=?", (table,)).fetchone()


def test_cosmetic_shop_purchase_equip_and_replay(game):
    engine = WinterFunEngine(game, FixedRNG())
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=30 WHERE discord_user_id=101")
    result = engine.buy(KEY, 101, "goggles", "buy-goggles", START)
    assert "Glacier Goggles" in result
    assert engine.buy(KEY, 101, "goggles", "buy-goggles", START) == result
    assert engine.shop(KEY, 101, START).balance == 20
    assert "goggles" in engine.shop(KEY, 101, START).unlocked
    with pytest.raises(WinterFunError, match="Already owned"):
        engine.buy(KEY, 101, "goggles", "another-purchase", START)
    with pytest.raises(WinterFunError, match="must unlock"):
        engine.equip(KEY, 101, "scarf", START)
    assert "Equipped" in engine.equip(KEY, 101, "goggles", START)
    assert engine.shop(KEY, 101, START).equipped["gear"] == "goggles"


def test_shop_rejects_overspending_and_unknown_keys(game):
    engine = WinterFunEngine(game)
    with pytest.raises(WinterFunError, match="Snowflakes"):
        engine.buy(KEY, 101, "gold_frame", "poor", START)
    with pytest.raises(WinterFunError, match="Unknown"):
        engine.buy(KEY, 101, "golden_snowball", "not-a-cosmetic", START)
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM cosmetic_purchases").fetchone()[0] == 0


def test_same_interaction_cannot_purchase_another_cosmetic(game):
    engine = WinterFunEngine(game)
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=40 WHERE discord_user_id=101")
    engine.buy(KEY, 101, "ice_frame", "collision", START)
    with pytest.raises(WinterFunError, match="Interaction ID"):
        engine.buy(KEY, 101, "snow_trail", "collision", START)
    assert engine.shop(KEY, 101, START).balance == 32


def test_concurrent_purchase_only_spends_once(game):
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=8 WHERE discord_user_id=101")
    def buy(i):
        try:
            return WinterFunEngine(game).buy(KEY, 101, "ice_frame", f"purchase-{i}", START)
        except WinterFunError:
            return "denied"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(buy, [1, 2]))
    assert sum(result != "denied" for result in results) == 1
    assert game.connect is not None
    assert game.schema_version() == 8
    assert WinterFunEngine(game).shop(KEY, 101, START).balance == 0


def test_arcade_modes_daily_caps_no_resource_or_leaderboard_effect(game):
    rng = FixedRNG(0.01)
    engine = WinterFunEngine(game, rng)
    before = CombatEngine(game).ledger_total(KEY, 101)
    for mode in ("target", "boss", "dodge"):
        for i in range(DAILY_MODE_CAP):
            score = engine.play(KEY, 101, mode, f"{mode}-{i}", START)
            assert score.points > 0
            assert score.attempts_used == i + 1
        with pytest.raises(WinterFunError, match="all three attempts"):
            engine.play(KEY, 101, mode, f"{mode}-excess", START)
    assert CombatEngine(game).ledger_total(KEY, 101) == before
    with game.connect() as con:
        for table in ("combat_events", "pve_events", "item_events", "quest_claims", "mystery_gifts", "prize_awards"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_gear_bonuses_only_arcade_and_do_not_change_hit_rates(game):
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=80 WHERE discord_user_id=101")
    engine = WinterFunEngine(game, FixedRNG(.70))
    normal = engine.play(KEY, 101, "target", "normal-shot", START)
    assert normal.points == 0
    engine.buy(KEY, 101, "goggles", "buy", START)
    engine.equip(KEY, 101, "goggles", START)
    aimed = engine.play(KEY, 101, "target", "aimed-shot", START)
    assert aimed.points == 50
    assert CombatEngine(game).ledger_total(KEY, 101) == 0


def test_daily_encounter_exactly_once_and_persistent(game):
    engine = WinterFunEngine(game)
    first = engine.encounter(KEY, 101, "find-1", START)
    second = engine.encounter(KEY, 101, "find-2", START)
    assert not first.repeated and second.repeated
    assert first.souvenir == second.souvenir
    assert engine.shop(KEY, 101, START).encounter.souvenir == first.souvenir
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM encounter_events").fetchone()[0] == 1
    assert CombatEngine(game).ledger_total(KEY, 101) == 0


def test_encounters_and_arcade_are_season_scoped(game):
    second = "winter-2027"
    game.ensure_season(second, START)
    game.register(second, 101, "Player101", "Chicago", START - timedelta(days=1))
    game.transition(second, 999, "start", START, "other season")
    engine = WinterFunEngine(game, FixedRNG())
    engine.encounter(KEY, 101, "one-season", START)
    engine.play(KEY, 101, "boss", "first-season-game", START)
    new = engine.shop(second, 101, START)
    assert new.encounter is None and new.arcade_used["boss"] == 0
    assert new.balance == 0


def test_modes_and_encounters_refuse_prestart_and_paused(game):
    game.transition(KEY, 999, "pause", START + timedelta(minutes=1), "test pause")
    engine = WinterFunEngine(game)
    with pytest.raises(WinterFunError, match="live"):
        engine.encounter(KEY, 101, "paused-encounter", START + timedelta(minutes=1))
    with pytest.raises(WinterFunError, match="live"):
        engine.play(KEY, 101, "target", "paused-mode", START + timedelta(minutes=1))
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM arcade_events").fetchone()[0] == 0


def test_rotating_missions_have_all_days_same_three_keys():
    keys = {"throws", "rivals", "community"}
    assert {m.key for m in missions_for_day(1)} == keys
    assert {m.key for m in missions_for_day(7)} == keys
    assert all({m.key for m in missions_for_day(d)} == keys for d in range(1, 8))
    assert len({tuple(m.title for m in missions_for_day(d)) for d in range(1, 8)}) == 7
    assert missions_for_day(1)[0].target == 5


def test_daily_quests_show_rotating_titles_and_same_rewards(game):
    engine = EconomyEngine(game)
    day1 = engine.quests(KEY, 101, START)
    assert day1[0].name == "Get your gloves on"
    with game.connect() as con:
        game_state = con.execute("SELECT started_at_utc FROM season_state WHERE season_key=?", (KEY,)).fetchone()
        assert game_state[0]
    day2 = engine.quests(KEY, 101, START + timedelta(days=1))
    assert day2[0].name == "Fortification Drill"
    assert [x.key for x in day2] == ["throws", "rivals", "community"]
    assert [x.target for x in day2] == [4, 2, 1]
    with game.connect() as con:
        assert daily_progress(con, KEY, 101, 2) == {"throws": 0, "rivals": 0, "community": 0}


def test_immutable_winter_event_history(game):
    engine = WinterFunEngine(game)
    engine.encounter(KEY, 101, "immutable-1", START)
    with game.connect() as con:
        with pytest.raises(sqlite3.DatabaseError, match="immutable winter event"):
            con.execute("DELETE FROM encounter_events WHERE season_key=?", (KEY,))


def test_no_any_prize_record_even_after_gear_and_all_modes(game):
    engine = WinterFunEngine(game, FixedRNG())
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=90 WHERE discord_user_id=101")
    for key in COSMETICS:
        if engine.shop(KEY, 101, START).balance >= COSMETICS[key].cost:
            engine.buy(KEY, 101, key, f"buy-{key}", START)
    for mode in ("target", "dodge", "boss"):
        engine.play(KEY, 101, mode, f"arcade-{mode}", START)
    engine.encounter(KEY, 101, "encounter", START)
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0


def test_migrating_v7_retains_players_and_score_rows(game):
    with game.connect() as con:
        con.execute("INSERT INTO score_ledger (season_key,day,player_id,city,category,"
                    "points,source_key,created_at_utc) VALUES (?,?,?,?,'quest',20,?,?)",
                    (KEY, 1, 101, "Chicago", "keep-me", START.isoformat()))
        for name in ("cosmetic_purchases", "encounter_events", "arcade_events", "cosmetic_unlocks"):
            for suffix in ("immutable_update", "immutable_delete"):
                con.execute(f"DROP TRIGGER IF EXISTS {name}_{suffix}")
        for name in ("cosmetic_purchases", "encounter_events", "arcade_events",
                     "cosmetic_unlocks", "cosmetic_equipped"):
            con.execute(f"DROP TABLE {name}")
        con.execute("PRAGMA user_version=7")
    game.initialize()
    game.initialize()
    assert game.schema_version() == 8
    assert game.get_player(KEY, 101).mr_username == "Player101"
    assert CombatEngine(game).ledger_total(KEY, 101) == 20
    assert not WinterFunEngine(game).shop(KEY, 101, START).unlocked


def test_encounter_three_choices_produce_distinct_souvenirs(tmp_path):
    result = []
    for idx, choice in enumerate(("help", "investigate", "prank"), 1):
        db = Store(tmp_path / f"encounter{idx}.db")
        db.initialize()
        db.ensure_season(KEY, START)
        db.register(KEY, 101, "Player101", "Chicago", START)
        db.transition(KEY, 999, "start", START, "test")
        result.append(WinterFunEngine(db).encounter(KEY, 101, f"choice-{idx}", START, choice).souvenir)
    assert len(set(result)) == 3


def test_steady_and_risky_have_different_arcade_outcomes(game):
    engine = WinterFunEngine(game, FixedRNG(.50))
    safe = engine.play(KEY, 101, "target", "safe", START, "steady")
    risky = engine.play(KEY, 101, "target", "risk", START, "risky")
    assert safe.points == 50 and risky.points == 0
    assert safe.style == "steady" and risky.style == "risky"
    with pytest.raises(WinterFunError, match="different mini-game"):
        engine.play(KEY, 101, "target", "risk", START, "steady")


def test_cross_season_replayed_purchase_cannot_reuse_interaction_id(game):
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=50 WHERE season_key=?", (KEY,))
    engine = WinterFunEngine(game)
    engine.buy(KEY, 101, "ice_frame", "shared-interaction", START)
    other = "winter-second"
    game.ensure_season(other, START)
    game.register(other, 101, "Player101", "Chicago", START)
    game.transition(other, 999, "start", START, "test")
    with game.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=50 WHERE season_key=?", (other,))
    with pytest.raises(WinterFunError, match="Interaction ID"):
        engine.buy(other, 101, "ice_frame", "shared-interaction", START)
    assert engine.shop(other, 101, START).balance == 50
