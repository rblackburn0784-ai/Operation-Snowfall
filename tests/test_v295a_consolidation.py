"""v2.9.5a — review guards preserved when consolidating two release streams."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from snowfall.platform.identity import IdentityConflict
from snowfall.platform.unified_discord import MappedConnection


class RecordingConnection:
    def __init__(self):
        self.commands = []

    def execute(self, statement, args=()):
        self.commands.append((statement, args))
        return SimpleNamespace(fetchall=lambda: [
            ("123456789012345678", 6_000_000_000_000_000_002)
        ])


def test_raw_discord_snowflake_is_blocked_instead_of_becoming_a_new_player():
    pg = RecordingConnection()
    con = MappedConnection(pg)
    assert len(pg.commands) == 1
    con.execute("SELECT ? WHERE discord_user_id=?", (17, 123456789012345678))
    assert pg.commands[-1][1] == (17, 6_000_000_000_000_000_002)
    with pytest.raises(IdentityConflict, match="no longer linked"):
        con.execute("INSERT INTO players(discord_user_id) VALUES (?)",
                    (234567890123456789,))
    assert len(pg.commands) == 2  # No unlinked player write reached DB.


class Response:
    def __init__(self):
        self.messages = []

    async def send_message(self, text, *, ephemeral=False, **_kwargs):
        self.messages.append((text, ephemeral))

    def is_done(self):
        return bool(self.messages)


def interaction(command="start"):
    client = SimpleNamespace(store=SimpleNamespace(unified_discord=True),
                             unified_identity=None, practice=None)
    return SimpleNamespace(
        client=client, response=Response(),
        user=SimpleNamespace(id=101, roles=[]),
        guild_id=777, channel_id=888,
        command=SimpleNamespace(name=command),
    )


def test_shared_qa_admin_is_read_only_except_audit_and_status():
    from snowfall.commands.admin import SnowAdminGroup
    setting = SimpleNamespace(guild_id=777, admin_user_ids=frozenset({101}),
                              staff_role_ids=frozenset(), season_key="web-qa-2026")
    group = SnowAdminGroup(setting, SimpleNamespace(), practice=None)

    async def run():
        for action in ("start", "pause", "resume", "finalize", "review",
                       "adjust-score", "approve-launch", "test-start",
                       "test-day", "test-end", "publish-dashboard",
                       "publish-leaderboards", "export-prizes", "prize-status"):
            ctx = interaction(action)
            assert not await group.interaction_check(ctx), action
            assert ctx.response.messages[-1][1] is True
            assert "disabled" in ctx.response.messages[-1][0]
        for action in ("status", "test-status", "launch-check"):
            assert await group.interaction_check(interaction(action)), action

    asyncio.run(run())


def test_old_host_panel_cannot_bypass_qa_lock():
    from snowfall.ui.navigation import MenuView

    async def run():
        settings = SimpleNamespace(
            guild_id=777, season_key="web-qa-2026",
            admin_user_ids=frozenset({101}), mode="production"
        )
        ctx = interaction()
        view = MenuView(settings, SimpleNamespace(), 101,
                        host_only=True, admin_context=True)
        assert not await view.interaction_check(ctx)
        assert "disabled" in ctx.response.messages[-1][0]
    asyncio.run(run())


def test_wire_modal_rechecks_link_even_when_invoked_from_old_menu():
    from snowfall.ui.wire import SubmitStory
    from snowfall.platform.identity import IdentityError

    class RevokedIdentity:
        def principal_for_discord(self, _discord):
            raise IdentityError("Account link revoked")

    async def run():
        ctx = interaction()
        ctx.client.unified_identity = RevokedIdentity()
        settings = SimpleNamespace(guild_id=777, season_key="web-qa-2026",
                                   mode="production")
        view = SubmitStory(settings, SimpleNamespace(), 101)
        await view.on_submit(ctx)
        assert ctx.response.messages[-1][1] is True
        assert "Link your Discord" in ctx.response.messages[-1][0]
    asyncio.run(run())
