"""Installed-discord checks for the single-application test-day commands and views."""
from datetime import datetime, timedelta, timezone
import pytest

pytest.importorskip("discord")
from snowfall.commands.admin import SnowAdminGroup  # noqa: E402
from snowfall.commands.public import SnowGroup  # noqa: E402
from snowfall.config import Settings  # noqa: E402
from snowfall.db.store import Store  # noqa: E402
from snowfall.practice import PracticeManager, ScopedSettings, ScopedStore  # noqa: E402
from snowfall.ui.dashboard import Dashboard  # noqa: E402
from snowfall.ui.combat import ThrowMenu  # noqa: E402
from snowfall.ui.economy import InventoryMenu  # noqa: E402
from snowfall.ui.world import WorldView  # noqa: E402


def fixture_manager(tmp_path):
    now = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)
    store = Store(tmp_path / "prod.sqlite3")
    store.initialize()
    store.ensure_season("prod", now + timedelta(days=20))
    settings = Settings("same-token", 123, frozenset({99}), "prod", "Snowfall",
                        now + timedelta(days=20), store.path,
                        announcement_channel_id=222, leaderboard_channel_id=333)
    return now, PracticeManager(settings, store)


def test_test_controls_are_registered_and_test_stop_does_not_close_bot(tmp_path):
    now, manager = fixture_manager(tmp_path)
    scoped = ScopedSettings(manager), ScopedStore(manager)
    admin = SnowAdminGroup(*scoped, practice=manager)
    player = SnowGroup(*scoped, practice=manager)
    names = {c.name for c in admin.commands}
    assert {"test-start", "test-day", "test-status", "test-end", "test-stop"} <= names
    assert len(admin.commands) <= 25  # Discord group limit
    assert "join" in {c.name for c in player.commands}
    # The v0.1.6 'test-stop' command is now a safe in-app alias.
    legacy = next(c for c in admin.commands if c.name == "test-stop")
    assert "test_end.callback" in legacy.callback.__code__.co_names or "test_end" in legacy.callback.__code__.co_names
    session = manager.start(2, 444, 99, now)
    assert session.settings.token == manager.live_settings.token
    manager.end()


def test_practice_dashboard_is_not_a_second_persistent_production_view(tmp_path):
    now, manager = fixture_manager(tmp_path)
    production = Dashboard(manager.live_settings, manager.live_store)
    production_ids = [c.custom_id for c in production.children if c.custom_id]
    day = manager.start(6, 444, 99, now)
    assert manager.for_interaction(444)
    practice = Dashboard(ScopedSettings(manager), ScopedStore(manager))
    practice_ids = [c.custom_id for c in practice.children if c.custom_id]
    assert practice.timeout == 900
    assert production.timeout is None
    assert len(practice_ids) == len(set(practice_ids))
    assert not set(practice_ids) & set(production_ids)
    assert all("rehearsal" in key for key in practice_ids)
    assert practice.store is day.store
    manager.end()


def test_practice_inventory_combat_and_boss_views_bind_test_store(tmp_path):
    now, manager = fixture_manager(tmp_path)
    day = manager.start(3, 444, 99, now)
    assert manager.for_interaction(444)
    settings, store = ScopedSettings(manager), ScopedStore(manager)
    for view in (
        InventoryMenu(settings, store, 99),
        WorldView(settings, store, 99),
        ThrowMenu(settings, store, 99, 100, "Rival"),
    ):
        assert view.store is day.store
        assert view.settings.season_key == day.settings.season_key
    manager.end()
    assert all(not view.store.active for view in (
        InventoryMenu(day.settings, day.store, 99),
        WorldView(day.settings, day.store, 99),
        ThrowMenu(day.settings, day.store, 99, 100, "Rival"),
    ))
