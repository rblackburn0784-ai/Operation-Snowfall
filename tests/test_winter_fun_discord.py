"""Gateway-free Discord contract tests for v0.2.0 menus and slash commands."""
import pytest

discord = pytest.importorskip("discord")

from snowfall.commands.winter_fun import SnowFunGroup  # noqa: E402
from snowfall.ui.winter_fun import (  # noqa: E402
    WinterActivitiesView, WinterPicker, WinterConfirm, EncounterPicker,
)


class Settings:
    guild_id = 12345
    season_key = "test"
    mode = "production"


def test_snowfun_commands_are_under_discord_limits():
    group = SnowFunGroup(Settings(), object())
    assert {c.name for c in group.commands} == {"menu", "shop", "wardrobe", "encounter", "arcade", "showcase", "rivalries", "raid", "territory", "mystery"}
    assert len(group.commands) <= 25


def test_winter_menus_fit_mobile_button_rows():
    views = (
        WinterActivitiesView(Settings(), object(), 101),
        WinterPicker(Settings(), object(), 101, "play"),
        WinterPicker(Settings(), object(), 101, "buy"),
        WinterPicker(Settings(), object(), 101, "equip"),
        WinterConfirm(Settings(), object(), 101, "play", "target"),
        WinterConfirm(Settings(), object(), 101, "buy", "ice_frame"),
        EncounterPicker(Settings(), object(), 101),
    )
    for view in views:
        assert len(view.children) <= 25
        assert all(c.row is None or 0 <= c.row <= 4 for c in view.children)
        counts = {}
        for child in view.children:
            if child.row is not None:
                counts[child.row] = counts.get(child.row, 0) + 1
        assert all(count <= 5 for count in counts.values())
    assert not any(getattr(x, "label", "") == "Risky Play" for x in views[5].children)
    assert any(getattr(x, "label", "") == "Risky Play" for x in views[4].children)


def test_winter_menu_pins_to_same_registered_owner():
    view = WinterActivitiesView(Settings(), object(), 101)
    assert view.owner_id == 101
    assert not view.host_only
