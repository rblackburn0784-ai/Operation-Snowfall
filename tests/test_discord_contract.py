"""Check discord.py actually accepts our slash-command groups and UI layouts.

Runs in GitHub Actions where discord.py is installed; local minimal Python
runtimes without Discord skip this gateway-free contract test.
"""
import pytest

discord = pytest.importorskip("discord")

from snowfall.commands.public import SnowGroup  # noqa: E402
from snowfall.ui.dashboard import Dashboard  # noqa: E402
from snowfall.ui.combat import ThrowMenu  # noqa: E402
from snowfall.ui.economy import InventoryMenu, QuestsMenu  # noqa: E402


class Settings:
    guild_id = 12345
    season_key = "test"


def test_command_count_and_menus_do_not_exceed_discord_limits():
    group = SnowGroup(Settings(), object())
    names = {c.name for c in group.commands}
    assert {"craft", "use", "inventory", "guard", "quests", "claim", "present"} <= names
    assert len(names) <= 25
    for view in (Dashboard(Settings(), object()), InventoryMenu(Settings(), object(), 8),
                 QuestsMenu(Settings(), object(), 8),
                 ThrowMenu(Settings(), object(), 8, 9, "rival")):
        assert len(view.children) <= 25
        assert all(getattr(x, "row", None) is None or x.row <= 4 for x in view.children)
