"""Discord-library contracts for v0.1.6b's one-message menus and host controls."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("discord")

from snowfall.config import Settings  # noqa: E402
from snowfall.commands.public import SnowGroup  # noqa: E402
from snowfall.commands.admin import SnowAdminGroup  # noqa: E402
from snowfall.db.store import Store  # noqa: E402
from snowfall.practice import PracticeManager  # noqa: E402
from snowfall.ui.dashboard import Dashboard, CityPicker  # noqa: E402
from snowfall.ui.combat import ThrowMenu, ConfirmThrow, RetryView  # noqa: E402
from snowfall.ui.economy import InventoryMenu, ItemPicker, QuestsMenu  # noqa: E402
from snowfall.ui.world import WorldView, WorldConfirm  # noqa: E402
from snowfall.ui.navigation import (  # noqa: E402
    MainMenu, GameMenu, PlayerMenu, RankingsMenu, HelpMenu,
    AdminPanel, BroadcastMenu, BroadcastConfirm, TestCentre as SnowTestCentre,
    TestDaySelect as SnowTestDaySelect, TestConfirm as SnowTestConfirm,
)


def prepare(tmp_path: Path):
    now = datetime.now(timezone.utc)
    db = Store(tmp_path / "live.sqlite3")
    db.initialize()
    db.ensure_season("december-live", now + timedelta(days=14))
    settings = Settings("bot-token", 1122, frozenset({77}), "december-live", "Snowfall",
                        now + timedelta(days=14), db.path,
                        announcement_channel_id=222, leaderboard_channel_id=333,
                        backup_dir=tmp_path / "backups")
    return settings, db, PracticeManager(settings, db)


class FakeResponse:
    def __init__(self):
        self.defers = []
        self.messages = []

    async def defer(self, **kw):
        self.defers.append(kw)

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeInteraction:
    def __init__(self, manager, channel=444, user_id=77):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = manager.live_settings.guild_id
        self.channel_id = channel
        self.client = SimpleNamespace(practice=manager, settings=manager.live_settings,
                                      store=manager.live_store)
        self.response = FakeResponse()
        self.edits = []

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


def button(view, label):
    return next(x for x in view.children if getattr(x, "label", None) == label)


def test_private_main_menu_navigation_and_host_visibility(tmp_path):
    settings, store, manager = prepare(tmp_path)
    nonhost = MainMenu(settings, store, 88)
    host = MainMenu(settings, store, 77)
    assert "Admin / Test" not in {x.label for x in nonhost.children}
    assert "Admin / Test" in {x.label for x in host.children}

    async def path():
        event = FakeInteraction(manager)
        assert await host.interaction_check(event)
        assert not await nonhost.interaction_check(event)
        assert event.response.messages
        await button(host, "Game Menus").callback(event)
        assert isinstance(event.edits[-1]["view"], GameMenu)
        assert event.response.defers  # navigation acknowledges components promptly
        game = event.edits[-1]["view"]
        await button(game, "Rankings").callback(event)
        assert isinstance(event.edits[-1]["view"], RankingsMenu)
        await button(event.edits[-1]["view"], "Home").callback(event)
        assert isinstance(event.edits[-1]["view"], MainMenu)
    asyncio.run(path())


def test_host_panel_is_private_and_does_not_use_practice_store_for_live_status(tmp_path):
    settings, store, manager = prepare(tmp_path)
    day = manager.start(2, 444, 77, datetime.now(timezone.utc))
    panel = AdminPanel(settings, store, 77, manager)
    assert panel.store is manager.live_store
    assert panel.store is not day.store
    assert panel.admin_context
    assert isinstance(BroadcastMenu(settings, store, 77, manager), AdminPanel)
    assert isinstance(BroadcastConfirm(settings, store, 77, manager, "leaderboard"), AdminPanel)

    async def guarded():
        other = FakeInteraction(manager, user_id=88)
        assert not await panel.interaction_check(other)
        host = FakeInteraction(manager)
        assert await panel.interaction_check(host)
        await button(panel, "Test Centre").callback(host)
        assert isinstance(host.edits[-1]["view"], SnowTestCentre)
        assert host.edits[-1]["view"].store is store
    asyncio.run(guarded())
    manager.end()


def test_test_panel_confirms_day_switch_delete_and_archive_without_live_mutation(tmp_path):
    settings, live, manager = prepare(tmp_path)
    before = live.season(settings.season_key)
    starting = SnowTestConfirm(settings, live, 77, manager, "start", day=1, channel_id=444)

    async def play():
        event = FakeInteraction(manager)
        await button(starting, "✅ Confirm Test Action").callback(event)
        assert manager.session is not None and manager.session.day == 1
        first = manager.session.store
        assert "TEST Day 1" in event.edits[-1]["content"]
        switch = SnowTestConfirm(settings, live, 77, manager, "switch", day=7)
        await button(switch, "✅ Confirm Test Action").callback(event)
        assert manager.session is not None and manager.session.day == 7
        assert first.active is False
        assert not first.path.exists()
        stop = SnowTestConfirm(settings, live, 77, manager, "delete")
        old_path = manager.session.store.path
        await button(stop, "✅ Confirm Test Action").callback(event)
        assert manager.session is None and not old_path.exists()
        archive_start = SnowTestConfirm(settings, live, 77, manager, "start", day=4,
                                    channel_id=444)
        await button(archive_start, "✅ Confirm Test Action").callback(event)
        archive = SnowTestConfirm(settings, live, 77, manager, "archive")
        await button(archive, "✅ Confirm Test Action").callback(event)
        assert manager.session is None
        assert len(list(manager.archive_dir.glob("test-day-4-*.sqlite3"))) == 1
    asyncio.run(play())
    assert live.season(settings.season_key) == before
    assert live.registrations(settings.season_key) == []


def test_stale_rehearsal_menu_is_revoked_after_reset(tmp_path):
    settings, store, manager = prepare(tmp_path)
    first = manager.start(3, 444, 77, datetime.now(timezone.utc))
    old = GameMenu(first.settings, first.store, 77)
    manager.change_day(4, 77, datetime.now(timezone.utc))
    async def stale():
        event = FakeInteraction(manager)
        assert not await old.interaction_check(event)
        assert "ended" in event.response.messages[-1][0][0].lower()
    asyncio.run(stale())
    manager.end()


def test_prod_menu_fails_closed_in_active_test_channel(tmp_path):
    settings, store, manager = prepare(tmp_path)
    manager.start(1, 444, 77, datetime.now(timezone.utc))
    async def route():
        event = FakeInteraction(manager)
        assert not await MainMenu(settings, store, 77).interaction_check(event)
        assert "test day" in event.response.messages[-1][0][0].lower()
    asyncio.run(route())
    manager.end()


def test_nested_navigation_and_discord_button_limits(tmp_path):
    settings, store, manager = prepare(tmp_path)
    for view in (
        Dashboard(settings, store), MainMenu(settings, store, 77), GameMenu(settings, store, 77),
        PlayerMenu(settings, store, 77), RankingsMenu(settings, store, 77),
        HelpMenu(settings, store, 77), AdminPanel(settings, store, 77, manager),
        SnowTestCentre(settings, store, 77, manager),
        SnowTestDaySelect(settings, store, 77, manager, "start"),
        SnowTestConfirm(settings, store, 77, manager, "delete"),
        CityPicker(settings, store, 77),
        ThrowMenu(settings, store, 77, 88, "rival"),
        ConfirmThrow(settings, store, 77, 88, "rival", "power"),
        RetryView(settings, store, 77),
        InventoryMenu(settings, store, 77), ItemPicker(settings, store, 77, "craft"),
        QuestsMenu(settings, store, 77),
        WorldView(settings, store, 77), WorldConfirm(settings, store, 77, "boss"),
    ):
        assert len(view.children) <= 25, type(view).__name__
        assert all(getattr(child, "row", None) is None or child.row <= 4
                   for child in view.children), type(view).__name__
    for view in (ThrowMenu(settings, store, 77, 88, "rival"),
                 InventoryMenu(settings, store, 77),
                 QuestsMenu(settings, store, 77), WorldView(settings, store, 77)):
        assert {"◀ Game Menus", "🏠 Home"} <= {c.label for c in view.children}
    assert "Main Menu" in {b.label for b in Dashboard(settings, store).children}
    assert len(SnowGroup(settings, store).commands) <= 25
    assert len(SnowAdminGroup(settings, store).commands) <= 25
    assert "menu" in {c.name for c in SnowGroup(settings, store).commands}
    assert "panel" in {c.name for c in SnowAdminGroup(settings, store).commands}
