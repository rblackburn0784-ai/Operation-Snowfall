"""v2.9.5b live-smoke regression for Discord Unknown interaction (10062).

Cross-project PostgreSQL ownership checks may outlast the 3-second Discord
interaction acknowledgement limit. Old world-menu buttons must defer BEFORE
identity reads, then edit the deferred original message, without consuming a
snowball, awarding points, or creating another response.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from snowfall.ui.world import WorldView, WorldConfirm


class Response:
    def __init__(self):
        self.events = []
        self.done = False

    def is_done(self):
        return self.done

    async def defer(self):
        if self.done:
            raise AssertionError("Interaction already acknowledged")
        self.done = True
        self.events.append("defer")

    async def edit_message(self, **kwargs):
        if self.done:
            raise AssertionError("Cannot edit initial response after defer")
        self.done = True
        self.events.append(("edit_initial", kwargs))

    async def send_message(self, *_args, **_kwargs):
        self.done = True
        self.events.append("send")


class VerifyIdentity:
    def __init__(self, response):
        self.response = response
        self.checked = 0

    def principal_for_discord(self, subject):
        assert self.response.is_done(), "Identity query began before Discord acknowledgement"
        assert subject == "123456789123456789"
        self.checked += 1
        return 6_000_000_000_000_000_002

    def links(self, principal):
        assert principal == 6_000_000_000_000_000_002
        assert self.response.is_done()
        self.checked += 1
        return [{"provider": "underworld", "subject": "owner-character"},
                {"provider": "discord", "subject": "123456789123456789"}]


def setup(view, label, *, linked=True, owner=True):
    button = next(x for x in view.children if getattr(x, "label", "") == label)
    response = Response()
    interaction = SimpleNamespace(
        data={"custom_id": button.custom_id},
        user=SimpleNamespace(id=123456789123456789 if owner else 987654321),
        guild_id=777,
        response=response,
        client=SimpleNamespace(
            unified_identity=VerifyIdentity(response) if linked else None,
            practice=None,
        ),
    )
    edits = []

    async def edit_original_response(**kwargs):
        assert response.is_done()
        edits.append(kwargs)

    interaction.edit_original_response = edit_original_response
    return interaction, edits


def settings():
    return SimpleNamespace(season_key="web-qa-2026", guild_id=777,
                           mode="production", is_test=False)


def test_boss_and_city_buttons_ack_before_both_postgres_identity_reads():
    async def run():
        for kind, label in (("boss", "Attack Snow Don"),
                            ("siege", "Attack City Fortress")):
            view = WorldView(settings(), SimpleNamespace(), 123456789123456789)
            interaction, edits = setup(view, label)
            assert await view.interaction_check(interaction)
            assert interaction.response.events == ["defer"]
            assert interaction.client.unified_identity.checked == 2
            await view._attack(interaction, kind)
            assert len(edits) == 1
            assert f"{kind.title()}** attack" in edits[0]["content"]
            assert isinstance(edits[0]["view"], WorldConfirm)
            assert interaction.response.events == ["defer"]
    asyncio.run(run())


def test_confirm_and_cancel_ack_before_postgres_lookup_without_double_defer():
    async def run():
        for label in ("Confirm Attack", "Cancel"):
            view = WorldConfirm(settings(), SimpleNamespace(),
                                123456789123456789, "boss")
            interaction, _edits = setup(view, label)
            assert await view.interaction_check(interaction)
            assert interaction.response.events == ["defer"]
            assert interaction.client.unified_identity.checked == 2
    asyncio.run(run())


def test_old_unlinked_sqlite_bot_retains_original_button_response():
    async def run():
        view = WorldView(settings(), SimpleNamespace(), 123456789123456789)
        interaction, edits = setup(view, "Attack Snow Don", linked=False)
        assert await view.interaction_check(interaction)
        assert not interaction.response.events
        await view._attack(interaction, "boss")
        assert interaction.response.events[0][0] == "edit_initial"
        assert not edits
    asyncio.run(run())


def test_wrong_player_cannot_force_deferred_menu_or_run_identity_query():
    async def run():
        view = WorldView(settings(), SimpleNamespace(), 123456789123456789)
        interaction, edits = setup(view, "Attack Snow Don", owner=False)
        assert not await view.interaction_check(interaction)
        assert interaction.response.events == ["send"]
        assert not edits
        assert interaction.client.unified_identity.checked == 0
    asyncio.run(run())


def test_navigation_buttons_do_not_receive_attack_specific_defer():
    async def run():
        view = WorldView(settings(), SimpleNamespace(), 123456789123456789)
        interaction, _edits = setup(view, "🏠 Home")
        # For non-attack navigation, the test identity must not insist on
        # early response; the existing home callback owns its response.
        interaction.client.unified_identity = SimpleNamespace(
            principal_for_discord=lambda _: 6_000_000_000_000_000_002,
            links=lambda _: [{"provider": "underworld"}],
        )
        assert await view.interaction_check(interaction)
        assert not interaction.response.events
    asyncio.run(run())
