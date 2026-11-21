"""Visual state follows the Discord engine and never mutates the raid."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from snowfall.graphics.snow_don import health_stage
from snowfall.platform.boss_visuals import current_boss, visuals


@pytest.mark.parametrize("maximum", [150, 151, 643, 100000])
def test_exact_bot_damage_stage(maximum):
    for hp in range(1, maximum + 1, max(1, maximum // 200)):
        result = visuals(hp, maximum)
        assert result["tier"] == health_stage(hp, maximum)
        assert result["portrait"].endswith(f"snow_don_{result['tier']}.png")
    for n in range(1, 11):
        hp = max(1, maximum * n // 10)
        assert visuals(hp, maximum)["tier"] == health_stage(hp, maximum)
    assert visuals(0, maximum)["tier"] == 0


@pytest.mark.parametrize("hp,state,scene", [
    (150, "healthy", "phase_ice"), (113, "healthy", "phase_ice"),
    (112, "cracked", "rage_tommy"), (76, "cracked", "rage_tommy"),
    (75, "wounded", "rage_snowball"), (38, "wounded", "rage_snowball"),
    (37, "critical", "phase_frostfire"), (1, "critical", "phase_frostfire"),
    (0, "defeated", "final_defeat"),
])
def test_splash_scene_and_committed_assets(hp, state, scene):
    value = visuals(hp, 150)
    assert value["state"] == state
    assert value["splash"].endswith(scene + ".webp")
    root = Path(__file__).resolve().parents[1] / "src/snowfall/graphics"
    for asset in ("portrait", "splash"):
        assert (root / value[asset].lstrip("/")).is_file()


def test_disabled_or_unspawned_is_not_a_defeat():
    assert visuals(0, 0)["state"] == "waiting"
    assert visuals(0, 150, enabled=False)["state"] == "disabled"
    assert visuals(0, 150)["portrait"].endswith("snow_don_0.webp")


def test_read_current_day_not_day_one_and_no_writes():
    store = Mock()
    season = store.season.return_value
    season.phase.return_value = "live"
    season.day.return_value = 4
    game = SimpleNamespace(store=store, season="isolated-test")
    report = SimpleNamespace(remaining_hp=76, max_hp=150, enabled=True,
                             hit_count=8, misses=3, contributors=2, echo_attacks=0)
    with patch("snowfall.platform.boss_visuals.RaidEngine") as raid:
        raid.return_value.report.return_value = report
        result = current_boss(game)
        raid.return_value.report.assert_called_once_with("isolated-test", 4)
    assert result["day"] == 4 and result["tier"] == 60
    assert result["hit_count"] == 8
    store.connect.assert_not_called()


def test_not_spawned_and_prestart_wait():
    store = Mock()
    season = store.season.return_value
    season.phase.return_value = "live"
    season.day.return_value = 3
    game = SimpleNamespace(store=store, season="isolated-test")
    with patch("snowfall.platform.boss_visuals.RaidEngine") as raid:
        raid.return_value.report.side_effect = ValueError("The Snow Don has not spawned for this day.")
        assert current_boss(game)["state"] == "waiting"
    season.phase.return_value = "ready"
    season.day.return_value = None
    assert current_boss(game)["hp"] is None
