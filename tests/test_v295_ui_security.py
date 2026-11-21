"""v2.9.5 regression: protect every Discord UI entrypoint in shared QA.

These tests do not log in to Discord or connect to Railway. They emulate
the real Discord callback path, which *bypasses* CommandTree guards.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from snowfall.platform.discord_security import (
    UNAVAILABLE_MESSAGE, UNLINKED_MESSAGE, check_linked_player, shared_qa,
)
from snowfall.platform.identity import IdentityError


class FakeIdentity:
    def __init__(self, mode):
        self.mode = mode
        self.lookups = []

    def principal_for_discord(self, user_id):
        self.lookups.append(user_id)
        if self.mode == "linked":
            return 6_000_000_000_000_000_002
        if self.mode == "offline":
            raise ConnectionError("sensitive internal connection error")
        raise IdentityError("Discord login has not been linked")


class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, *, ephemeral=False, **kwargs):
        self.messages.append((content, ephemeral))


def fake_interaction(mode="unlinked", *, admin=False, name="snow menu", session=None):
    client = SimpleNamespace(
        store=SimpleNamespace(unified_discord=True),
        unified_identity=FakeIdentity(mode),
        practice=None,
    )
    return SimpleNamespace(
        client=client, response=FakeResponse(),
        user=SimpleNamespace(id=123456789123456789, roles=[]),
        guild_id=987654321987654321, channel_id=111111111111111111,
        command=SimpleNamespace(qualified_name=name),
    )


def _settings():
    return SimpleNamespace(
        guild_id=987654321987654321, season_key="web-qa-2026",
        mode="production", admin_user_ids=frozenset({123456789123456789}),
        staff_role_ids=frozenset(), is_test=False,
    )


def test_unlinked_old_menu_and_combat_buttons_are_rejected():
    from snowfall.ui.navigation import MenuView
    from snowfall.ui.combat import CombatMenu
    from snowfall.ui.economy import EconomyView
    from snowfall.ui.world import WorldView, WorldConfirm
    from snowfall.ui.dashboard import Dashboard

    async def run():
        actor = 123456789123456789
        settings, store = _settings(), SimpleNamespace(unified_discord=True)
        views = [
            MenuView(settings, store, actor),
            CombatMenu(settings, store, actor),
            EconomyView(settings, store, actor),
            WorldView(settings, store, actor),
            WorldConfirm(settings, store, actor, "boss"),
            Dashboard(settings, store),
        ]
        for view in views:
            interaction = fake_interaction()
            assert not await view.interaction_check(interaction), type(view).__name__
            assert interaction.response.messages[-1] == (UNLINKED_MESSAGE, True)
            assert interaction.client.unified_identity.lookups == [str(actor)]
        for view in views:
            interaction = fake_interaction("linked")
            assert await view.interaction_check(interaction), type(view).__name__
    asyncio.run(run())


def test_unlinked_registration_modal_and_wire_submission_are_rejected():
    from snowfall.ui.dashboard import JoinModal
    from snowfall.ui.wire import SubmitStory

    async def run():
        settings, store = _settings(), SimpleNamespace(unified_discord=True)
        registration = JoinModal(settings, store, "Chicago")
        registration.declaration._value = "I AGREE"
        registration.mr_username._value = "UnlinkedCheater"
        interaction = fake_interaction()
        await registration.on_submit(interaction)
        assert interaction.response.messages[-1] == (UNLINKED_MESSAGE, True)

        story = SubmitStory(settings, store, 123456789123456789)
        interaction = fake_interaction()
        await story.on_submit(interaction)
        assert interaction.response.messages[-1] == (UNLINKED_MESSAGE, True)
    asyncio.run(run())


def test_database_outage_fails_closed_for_interactive_game():
    async def run():
        interaction = fake_interaction("offline")
        assert not await check_linked_player(interaction)
        assert interaction.response.messages[-1] == (UNAVAILABLE_MESSAGE, True)
        assert "sensitive" not in str(interaction.response.messages[-1])
    asyncio.run(run())


def test_original_sqlite_worker_preserves_legacy_discord_access():
    async def run():
        interaction = fake_interaction()
        interaction.client.unified_identity = None
        interaction.client.store.unified_discord = False
        assert not shared_qa(interaction.client)
        assert await check_linked_player(interaction)
        assert not interaction.response.messages
    asyncio.run(run())


def test_admin_control_commands_disabled_in_shared_qa_even_for_host():
    from snowfall.commands.admin import SnowAdminGroup

    async def run():
        settings, store = _settings(), SimpleNamespace(unified_discord=True)
        admin = SnowAdminGroup(settings, store)
        for name in (
            "snowadmin start", "snowadmin finalize", "snowadmin adjust-score",
            "snowadmin publish-dashboard", "snowadmin approve-launch",
            "snowadmin prize-status", "snowadmin test-start", "snowadmin panel",
            "snowadmin backup",
        ):
            interaction = fake_interaction("linked", name=name)
            assert not await admin.interaction_check(interaction), name
            assert "disabled" in interaction.response.messages[-1][0]
        # Read-only status remains available to configured staff.
        interaction = fake_interaction("linked", name="snowadmin status")
        assert await admin.interaction_check(interaction)
    asyncio.run(run())


def test_legacy_host_navigation_cannot_bypass_admin_lock():
    from snowfall.ui.navigation import MenuView

    async def run():
        interaction = fake_interaction("linked")
        view = MenuView(_settings(), SimpleNamespace(unified_discord=True),
                        interaction.user.id, host_only=True, admin_context=True)
        assert not await view.interaction_check(interaction)
        assert "read-only" in interaction.response.messages[-1][0]
    asyncio.run(run())


def test_shared_qa_labels_never_promise_real_prizes():
    from snowfall.ui.navigation import _mode
    from snowfall.ui.dashboard import dashboard_embed
    from snowfall.db.store import Season
    settings = _settings()
    assert "NO REAL PRIZES" in _mode(settings)
    # The dashboard renderer separately recognises the isolated QA season
    # even though the Railway environment is named "production".
    import inspect
    source = inspect.getsource(dashboard_embed)
    assert 'settings.season_key == "web-qa-2026"' in source
