"""Milestone E graphic safety and original artwork contracts; no Discord gateway."""
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image

from snowfall.graphics import cards
from snowfall.services.combat import CombatResult, ResourceView
from snowfall.services.world import CityStanding, WorldStatus, PveResult


@pytest.fixture
def resource():
    return ResourceView(8, 82, 13, 3, None, None, None, 150, 2, None, None)


@pytest.fixture
def battle():
    return CombatResult("x", 2, 1, 2, "New York", "power", True, True, 3, 23,
                        False, 23, 2, 5, 0, 0.15, 0.07)


@pytest.fixture
def world():
    return WorldStatus(2, "live", "Fortification Frenzy", 120, 450, 2, 15,
                       80, 230, 2, 16, "Chicago")


@pytest.fixture
def boss():
    return PveResult("b", "boss", 2, "Chicago", True, 18, 8, 0, 0, 450, False, True)


def assert_card(data, expected=(960, 540)):
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(data)) as card:
        assert card.size == expected
        assert card.mode == "RGB"
    assert len(data) < 2_000_000


def test_all_six_city_scenes_are_real_bundled_webps():
    for city in cards.CITIES:
        path = cards.ART / "cities" / (city.lower().replace(" ", "_") + ".webp")
        assert path.is_file(), city
        with Image.open(path) as image:
            assert image.size == (960, 540)
            image.verify()


def test_item_icons_have_transparency_and_correct_dimensions():
    for item in ("snowball", "cocoa", "fort", "mittens", "bomb", "golden", "boss", "siege"):
        with Image.open(cards.ART / "items" / (item + ".png")) as icon:
            assert icon.size == (192, 192) and icon.mode == "RGBA"
            assert icon.getpixel((0, 0))[3] == 0


def test_profile_card(resource):
    assert_card(cards.profile_card("Snow Dude", "Chicago", resource, 234,
                                   review="self-declared"))


def test_profile_with_hostile_multiline_long_player_name_is_safe(resource):
    assert_card(cards.profile_card("@everyone\n" + "X" * 200,
                                   "New York", resource, 9999999))
    assert "\n" not in cards.clean("A\nB")


def test_battle_static_for_hit_miss_ko_and_golden(battle):
    for variant in (battle, replace(battle, hit=False, critical=False, points_awarded=0),
                    replace(battle, knocked_out=True), replace(battle, style="golden")):
        assert_card(cards.battle_card(variant, "Rival"))


def test_world_status_boss_siege_and_null_day(world):
    assert_card(cards.world_status_card(world))
    assert_card(cards.world_status_card(replace(world, day=None, city=None, theme=None,
                                                boss_max_hp=0, siege_max_hp=0)))


def test_world_result_both_attack_types_and_echo(boss):
    assert_card(cards.world_result_card(boss))
    assert_card(cards.world_result_card(replace(boss, kind="siege", echo=True,
                                                final_blow=False, hp_after=99)))


def test_champions_card_does_not_require_winners_or_city():
    assert_card(cards.champions_card([], []))
    city = CityStanding("Chicago", 18000, 8, 2, 1, 250, True, 700, False)
    assert_card(cards.champions_card([("TheDude", "Chicago", 1, 450),
                                      ("Nevaa", "New York", 2, 420)],
                                     [city], final=True))


def test_renderer_handles_missing_scene_gracefully(monkeypatch, resource):
    monkeypatch.setattr(cards, "ART", cards.ART / "nonexistent")
    assert_card(cards.profile_card("Lost", "Chicago", resource, 0))


def test_traversal_city_does_not_read_arbitrary_paths(resource):
    assert_card(cards.profile_card("Name", "../../etc", resource, 0))


def test_critical_and_ko_animations_under_discord_upload_budget(battle):
    for variant in (battle, replace(battle, critical=False, knocked_out=True)):
        gif = cards.hit_animation(variant, "Another rival")
        assert gif is not None and gif.startswith(b"GIF89a") and len(gif) < 4_000_000
        with Image.open(BytesIO(gif)) as image:
            assert image.n_frames == 9
            assert image.size == (480, 270)


def test_regular_hits_and_misses_have_no_gif(battle):
    assert cards.hit_animation(replace(battle, critical=False), "Target") is None
    assert cards.hit_animation(replace(battle, hit=False), "Target") is None


def test_boss_final_blow_animation_and_echo_policy(boss):
    animated = cards.world_animation(boss)
    assert animated is not None and len(animated) < 4_000_000
    with Image.open(BytesIO(animated)) as image:
        assert image.n_frames == 9
    assert cards.world_animation(replace(boss, final_blow=False)) is None


def test_tiny_animation_limit_returns_none_without_broken_image(boss):
    assert cards.world_animation(boss, maximum_bytes=10) is None


def test_no_background_image_does_not_modify_game_result(battle, monkeypatch):
    before = repr(battle)
    monkeypatch.setattr(cards, "ART", cards.ART / "missing")
    assert_card(cards.battle_card(battle, "Rival"))
    assert repr(battle) == before
