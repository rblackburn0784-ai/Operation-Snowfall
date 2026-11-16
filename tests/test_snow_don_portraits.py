"""v0.1.6c: exact HP-to-image thresholds and supplied transparent art import."""
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw

from snowfall.graphics import cards, snow_don
from snowfall.services.world import PveResult, WorldStatus


@pytest.mark.parametrize("current,maximum,expected", [
    (150, 150, 100), (149, 150, 100), (135, 150, 90),
    (133, 150, 90), (120, 150, 80), (119, 150, 80),
    (100, 100, 100), (99, 100, 100), (90, 100, 90), (89, 100, 90),
    (80, 100, 80), (70, 100, 70), (50, 100, 50), (30, 100, 30),
    (20, 100, 20), (10, 100, 10), (9, 100, 10), (1, 100, 10),
    (0, 100, 10), (-5, 100, 10), (200, 100, 100), (0, 0, 10),
])
def test_health_stage_exact_thresholds(current, maximum, expected):
    assert snow_don.health_stage(current, maximum) == expected


def portrait_bytes(colour):
    sprite = Image.new("RGBA", (100, 250), (0, 0, 0, 0))
    ImageDraw.Draw(sprite).rectangle((15, 15, 85, 235), fill=(*colour, 255))
    output = BytesIO()
    sprite.save(output, format="PNG")
    return output.getvalue()


def make_pack(directory):
    source = directory / "snow_don_set.zip"
    with ZipFile(source, "w") as archive:
        for stage in snow_don.STAGES:
            archive.writestr(f"health_portraits/snow_don_{stage}.png",
                             portrait_bytes((stage, 25, 200 - stage)))
    return source


def test_installer_imports_exact_ten_files_without_extraction_traversal(tmp_path):
    source = make_pack(tmp_path)
    target = tmp_path / "installed"
    files = snow_don.install_portraits(source, target)
    assert len(files) == 10
    assert sorted(x.name for x in target.glob("*.png")) == sorted(
        f"snow_don_{stage}.png" for stage in snow_don.STAGES)
    assert all(p.parent == target for p in files)
    assert all(Image.open(p).getpixel((50, 50))[3] == 255 for p in files)


def test_installer_rejects_partial_or_opaque_pack(tmp_path):
    incomplete = tmp_path / "incomplete.zip"
    with ZipFile(incomplete, "w") as archive:
        archive.writestr("snow_don_100.png", portrait_bytes((100, 50, 50)))
    with pytest.raises(ValueError, match="Missing Snow Don portraits"):
        snow_don.install_portraits(incomplete, tmp_path / "no-partial-install")
    assert not (tmp_path / "no-partial-install").exists()

    opaque = tmp_path / "opaque.zip"
    with ZipFile(opaque, "w") as archive:
        for stage in snow_don.STAGES:
            sprite = Image.new("RGB", (60, 80), "white")
            out = BytesIO()
            sprite.save(out, format="PNG")
            archive.writestr(f"snow_don_{stage}.png", out.getvalue())
    with pytest.raises(ValueError, match="transparent"):
        snow_don.install_portraits(opaque, tmp_path / "no-opaque-install")


def test_missing_stage_is_not_substituted_with_wrong_damage_art(tmp_path):
    (tmp_path / "snow_don_100.png").write_bytes(portrait_bytes((100, 25, 100)))
    assert snow_don.portrait_path(90, tmp_path) is None
    scene = Image.new("RGBA", (960, 540), "black")
    assert snow_don.draw_portrait(scene, 90, 100, (650, 186, 923, 485),
                                  directory=tmp_path) is None


def test_status_and_boss_result_cards_show_matching_damage_portrait(tmp_path, monkeypatch):
    snow_don.install_portraits(make_pack(tmp_path), tmp_path / "installed")
    monkeypatch.setattr(snow_don, "PORTRAITS", tmp_path / "installed")

    status = WorldStatus(1, "live", "Opening Barrage", 100, 100, 0, 0,
                         72, 72, 0, 0, "Chicago")
    boss = PveResult("boss-1", "boss", 1, "Chicago", True, 10, 5, 0,
                     80, 100, False, False)
    for hp, expected_colour in [(100, 100), (99, 100), (90, 90), (80, 80), (19, 20), (0, 10)]:
        with Image.open(BytesIO(cards.world_status_card(replace(status, boss_hp=hp)))) as card:
            assert card.size == (960, 540)
            # The centre of the right-side character cannot be a legacy boss icon.
            pixel = card.getpixel((786, 320))
            assert pixel == (expected_colour, 25, 200 - expected_colour)
        with Image.open(BytesIO(cards.world_result_card(replace(boss, hp_after=hp)))) as card:
            assert card.size == (960, 540)
            assert card.getpixel((780, 330)) == (expected_colour, 25, 200 - expected_colour)
    # No mutation of authoritative scoring/health records.
    assert boss.hp_after == 80 and status.boss_hp == 100


def test_siege_does_not_use_snow_don_portraits(tmp_path, monkeypatch):
    snow_don.install_portraits(make_pack(tmp_path), tmp_path / "installed")
    monkeypatch.setattr(snow_don, "PORTRAITS", tmp_path / "installed")
    boss = PveResult("siege-1", "siege", 2, "Chicago", True, 10, 8, 0,
                     80, 100, False, False)
    with Image.open(BytesIO(cards.world_result_card(boss))) as card:
        assert card.size == (960, 540)
        assert card.getpixel((780, 330)) != (80, 25, 120)


def test_missing_portraits_fall_back_safely(monkeypatch, tmp_path):
    monkeypatch.setattr(snow_don, "PORTRAITS", tmp_path / "missing")
    status = WorldStatus(1, "live", "Opening Barrage", 90, 100, 0, 0,
                         72, 72, 0, 0, "Chicago")
    with Image.open(BytesIO(cards.world_status_card(status))) as card:
        assert card.size == (960, 540)
    boss = PveResult("boss-2", "boss", 1, "Chicago", True, 20, 5, 0,
                     50, 100, False, False)
    assert cards.world_result_card(boss).startswith(b"\x89PNG")
