"""v2.9.5: QA must not issue official prizes or overwrite guild broadcasts."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from snowfall.commands.admin import SnowAdminGroup
from snowfall.platform.unified_discord import UnifiedDiscordStore


class Response:
    def __init__(self):
        self.messages = []

    async def send_message(self, message, **kwargs):
        self.messages.append((message, kwargs))


def interaction(*, shared=True, command="export-prizes"):
    response = Response()
    store = (SimpleNamespace(unified_discord=True) if shared else
             SimpleNamespace(unified_discord=False))
    user = SimpleNamespace(id=101, roles=[])
    ctx = SimpleNamespace(
        client=SimpleNamespace(store=store),
        user=user, guild_id=777, channel_id=888,
        command=SimpleNamespace(name=command),
        response=response,
    )
    return ctx


def group():
    # __init__ only registers slash command callbacks; no database queries.
    settings = SimpleNamespace(
        guild_id=777, admin_user_ids=frozenset({101}),
        staff_role_ids=frozenset(), season_key="web-qa-2026",
    )
    return SnowAdminGroup(settings, SimpleNamespace(), practice=None)


def test_official_prize_launch_and_public_broadcast_commands_disabled():
    async def check():
        g = group()
        for command in ("approve-launch", "export-prizes", "prize-status",
                        "finalize", "publish-leaderboards", "announce-day"):
            ctx = interaction(command=command)
            assert not await g.interaction_check(ctx)
            assert ctx.response.messages[0][1]["ephemeral"] is True
            assert "disabled" in ctx.response.messages[0][0]
            # This also protects direct callback paths if they bypass group
            # command checks (e.g. a future admin menu).
            ctx2 = interaction(command=command)
            assert await g._qa_forbidden(ctx2, command)
            assert ctx2.response.messages[0][1]["ephemeral"]
        allowed = interaction(command="status")
        assert await g.interaction_check(allowed)
        assert not allowed.response.messages

        normal = interaction(shared=False, command="export-prizes")
        assert await g.interaction_check(normal)
        assert not await g._qa_forbidden(normal, "export-prizes")
    asyncio.run(check())


def test_qa_status_is_not_confused_with_real_prize_event():
    assert UnifiedDiscordStore.unified_discord
    assert not getattr(SimpleNamespace(), "unified_discord", False)
