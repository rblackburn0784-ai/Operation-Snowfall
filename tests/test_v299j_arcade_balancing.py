"""v2.9.9j: deterministic gameplay balancing and boundary regression tests.

These tests do not connect to Railway or touch player databases.
"""
import random

from snowfall.platform.gallery_arcade import (
    AMMO, DURATION_MS as GALLERY_DURATION, find_target,
    schedule_targets, target_position,
)
from snowfall.platform.safecracker_arcade import NOTCHES, proximity
from snowfall.platform.snowman_arcade import GEOMETRY, TOTAL_PARTS, make_blueprints
from snowfall.platform.catch_arcade import (
    BASKET_MAX, BASKET_MIN, CATCH_Y, DURATION_MS as CATCH_DURATION,
    flake_position, generate_schedule,
)
from snowfall.platform.trivia_arcade import (
    BANK, MAX_QUESTIONS, QUESTION_MS, TOTAL_MS,
)


def test_gallery_wave_progression_and_target_bounds():
    schedule = schedule_targets(random.Random(29910))
    assert len(schedule) > AMMO
    assert GALLERY_DURATION == 45_000
    assert {target["wave"] for target in schedule} == {1, 2, 3}
    assert any(target["kind"] == "decoy" for target in schedule)
    assert any(target["kind"] == "gold" for target in schedule)
    for target in schedule:
        assert 0 <= target["start"] < GALLERY_DURATION
        assert target["life"] > 0
        for moment in (target["start"], target["start"] + target["life"] // 2):
            x, y = target_position(target, moment)
            assert target["radius"] <= x <= 640 - target["radius"]
            assert target["radius"] <= y <= 360 - target["radius"]


def test_gallery_claimed_target_cannot_be_hit_again():
    schedule = schedule_targets(random.Random(29911))
    target = schedule[0]
    elapsed = target["start"] + 250
    x, y = target_position(target, elapsed)
    hit = find_target(schedule, set(), elapsed, round(x), round(y))
    assert hit is not None and hit["id"] == target["id"]
    assert find_target([target], {target["id"]}, elapsed, round(x), round(y)) is None


def test_safecracker_circular_proximity_is_symmetric():
    assert NOTCHES == 40
    for a in range(NOTCHES):
        assert proximity(a, a) == 0
        for b in range(NOTCHES):
            assert proximity(a, b) == proximity(b, a)
            assert 0 <= proximity(a, b) <= NOTCHES // 2
    assert proximity(0, 39) == 1


def test_snowman_blueprints_have_all_parts_and_valid_slots():
    blueprints = make_blueprints(random.Random(29912))
    assert len(blueprints) == 3
    assert TOTAL_PARTS == 20
    assert sum(len(stage["slots"]) for stage in blueprints) == TOTAL_PARTS
    for stage in blueprints:
        for slot in stage["slots"]:
            assert slot["id"] in GEOMETRY
            assert 0 <= slot["x"] <= 640
            assert 0 <= slot["y"] <= 360
            assert slot["radius"] > 0


def test_catch_schedule_spawns_three_waves_and_ends_in_time():
    schedule = generate_schedule(random.Random(29913))
    assert len(schedule) == 45
    assert {item["wave"] for item in schedule} == {1, 2, 3}
    assert {item["kind"] for item in schedule} == {
        "snowflake", "gold", "crystal", "hazard"
    }
    assert BASKET_MIN < BASKET_MAX
    assert max(item["impact"] for item in schedule) <= CATCH_DURATION
    for item in schedule:
        x, y = flake_position(item, item["impact"])
        assert 0 <= x <= 640
        assert abs(y - CATCH_Y) < 0.001


def test_trivia_three_levels_and_time_budget():
    assert len(BANK) == 3
    assert MAX_QUESTIONS == 15
    assert len(QUESTION_MS) == 3
    assert all(ms > 0 for ms in QUESTION_MS)
    assert TOTAL_MS > 0
    assert sum(5 * ms for ms in QUESTION_MS) == TOTAL_MS
