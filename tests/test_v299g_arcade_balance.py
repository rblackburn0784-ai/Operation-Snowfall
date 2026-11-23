"""v2.9.9g — quantitative practice balancing without economic changes."""
import json
import random

from snowfall.platform.catch_arcade import DURATION_MS as CATCH_LIMIT, generate_schedule
from snowfall.platform.gallery_arcade import (
    AMMO, DURATION_MS as GALLERY_LIMIT, schedule_targets,
)
from snowfall.platform.safecracker_arcade import (
    DIRECTIONS, MIN_TRAVEL, _signal, proximity,
)
from snowfall.platform.snowman_arcade import (
    BONUSES, GEOMETRY, ROUNDS, TOTAL_PARTS, _score, make_blueprints,
)
from snowfall.platform.trivia_arcade import MAX_QUESTIONS, _make_deck


def test_gallery_late_waves_ease_reaction_without_changing_ammo_or_rewards():
    schedule = schedule_targets(random.Random(17))
    assert len(schedule) == 43 and AMMO == 32
    assert {item["wave"] for item in schedule} == {1, 2, 3}
    base = {1: 2100, 2: 1840, 3: 1600}
    for item in schedule:
        expected = base[item["wave"]]-(230 if item["kind"] == "gold" else 0)
        assert item["life"] == expected
        assert item["start"] + item["life"] <= GALLERY_LIMIT
        assert item["radius"] in (25, 28, 30)
    assert base[1] > base[2] > base[3]


def test_catch_late_waves_move_slightly_slower_but_remain_within_one_minute():
    for seed in (4, 8, 17, 42, 99):
        schedule = generate_schedule(random.Random(seed))
        assert len(schedule) == 45
        flight = {1: 2550, 2: 2220, 3: 1880}
        assert all(item["flight"] == flight[item["wave"]] for item in schedule)
        assert all(item["start"] + item["flight"] <= CATCH_LIMIT
                   for item in schedule)
        assert sum(item["kind"] == "hazard" for item in schedule) == 5
        assert all(item["kind"] in ("snowflake", "crystal", "gold", "hazard")
                   for item in schedule)
        assert flight[1] > flight[2] > flight[3]


def test_safe_hints_cover_a_wider_range_but_victory_requires_exact_alignment():
    assert DIRECTIONS == (1, -1, 1)
    assert MIN_TRAVEL == (40, 40, 40)
    def cue(dial,travel=40):
        return _signal({
            "stage": 0, "travel": travel, "dial": dial,
            "combination_json": json.dumps([0, 10, 20]),
        })
    assert cue(0) == "click"
    assert cue(3) == cue(37) == "near"
    assert cue(4) == cue(7) == "faint"
    assert cue(8) == "quiet"
    assert cue(0,travel=39) == "turn"
    assert proximity(3,0) == 3 and proximity(0,0) == 0


def test_snowman_bigger_touch_targets_keep_three_rounds_and_original_score():
    plans = make_blueprints(random.Random(42))
    assert len(plans) == 3 and TOTAL_PARTS == 20
    assert sum(len(parts) for _,parts,_ in ROUNDS) == 20
    assert BONUSES == (4, 6, 10)
    offsets = (0, 2, 4)
    for i,plan in enumerate(plans):
        for slot in plan["slots"]:
            assert slot["radius"] == GEOMETRY[slot["id"]][2]+offsets[i]
    assert _score(20, 0, 3) == 100
    assert _score(20, 1, 3) == 97
    assert _score(10, 2, 1) == 38


def test_trivia_question_counts_speed_bonuses_unchanged():
    deck = _make_deck(random.Random(42))
    assert MAX_QUESTIONS == 15
    assert [q["limit_ms"] for q in deck] == [16000]*5+[14000]*5+[12000]*5
    assert all(q["kind"] in ("gift", "truefalse", "scramble") for q in deck)
    assert len({q["id"] for q in deck}) == 15
