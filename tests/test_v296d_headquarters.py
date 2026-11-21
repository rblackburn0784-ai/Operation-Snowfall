"""Private web HQ is based on real Discord read models, never fabricated awards."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from snowfall.platform.headquarters_view import headquarters_view
from snowfall.services.achievements import Trophy, CombatRecords
from snowfall.services.winter_fun import COSMETICS


def test_hq_reads_owned_equipment_and_earned_titles():
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    owned = next(k for k, v in COSMETICS.items() if v.category == "frame")
    unowned = next(k for k, v in COSMETICS.items() if v.category == "portrait")
    trophy = Trophy("first_flurry", "First Flurry", "Snowball Rookie",
                    "Land your first PvP hit", 1, 1, True)
    cabinet = SimpleNamespace(equipped_title=trophy.title, trophies=(trophy,),
                              records=CombatRecords(*([0]*16)))
    hq = SimpleNamespace(player=object(), phase="live", day=4, daily_points=8,
                         rank=5, season_points=42, resources=SimpleNamespace(today_pvp=8),
                         next_snowball=now, next_warmth=None, next_throw=None,
                         next_reset=None, arena_until=None, knockout_due=None, shield_due=None,
                         next_action="Find a rival", next_action_route="fight",
                         daily_gift="Opened", bonus_gift="Not today", quests=())
    store = object()
    with patch("snowfall.platform.headquarters_view.headquarters", return_value=hq) as read, \
         patch("snowfall.platform.headquarters_view.AchievementEngine") as medals, \
         patch("snowfall.platform.headquarters_view.WinterFunEngine") as wardrobe:
        medals.return_value.cabinet.return_value = cabinet
        wardrobe.return_value.shop.return_value = SimpleNamespace(
            unlocked=(owned,), equipped={"frame": owned, "portrait": unowned})
        result = headquarters_view(store, "qa", 42, now)
        read.assert_called_once_with(store, "qa", 42, now)
        medals.return_value.cabinet.assert_called_once_with("qa", 42)
        wardrobe.return_value.shop.assert_called_once_with("qa", 42, now)
    assert result["title"] == "Snowball Rookie"
    assert result["rarity"] == COSMETICS[owned].rarity
    assert result["trophies"][0]["unlocked"] is True
    assert result["timers"]["snowball"] == now
    assert result["caps"] == {"snowballs": 12, "warmth": 100, "pvp": 300}
    assert result["rank"] == 5 and result["daily_points"] == 8
    assert "player" not in result and "account_id" not in result


def test_unregistered_does_not_load_private_cabinet():
    hq = SimpleNamespace(player=None, phase="ready", day=None)
    with patch("snowfall.platform.headquarters_view.headquarters", return_value=hq), \
         patch("snowfall.platform.headquarters_view.AchievementEngine") as medals:
        result = headquarters_view(object(), "qa", 42)
        assert result == {"registered": False, "phase": "ready", "day": None}
        medals.assert_not_called()
