"""v2.9.5: every older Discord button and modal must respect current links.

A guild slash-command tree check is NOT invoked for a button or modal.
These tests reproduce old views left open after account unlinks, including
the registration modal that can otherwise create a second canonical player.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from snowfall.platform.identity import IdentityError
from snowfall.ui.combat import CombatMenu
from snowfall.ui.dashboard import CityPicker, Dashboard, JoinModal, rules_text, dashboard_embed
from snowfall.ui.economy import EconomyView
from snowfall.ui.linked import require_linked_discord
from snowfall.ui.navigation import MenuView
from snowfall.ui.world import WorldView, WorldConfirm


ACTOR = 123456789012345678
GUILD = 987654321123456789


class FakeIdentity:
    def __init__(self, principal=None, failure=None):
        self.principal, self.failure = principal, failure
        self.lookups = []

    def principal_for_discord(self, subject):
        self.lookups.append(subject)
        if self.failure:
            raise self.failure
        return self.principal


class FakeInteraction:
    def __init__(self, identity, *, who=ACTOR, guild=GUILD, response_done=False):
        self.user = SimpleNamespace(id=who)
        self.guild_id = guild
        self.channel_id = 777777777777777777
        self.client = SimpleNamespace(unified_identity=identity, practice=None)
        self.responded = []
        self.followed = []
        self.response = SimpleNamespace(
            is_done=lambda: response_done,
            send_message=self._respond,
            send_modal=self._modal,
        )
        self.followup = SimpleNamespace(send=self._followup)

    async def _respond(self, text, **kwargs):
        self.responded.append((text, kwargs))

    async def _followup(self, text, **kwargs):
        self.followed.append((text, kwargs))

    async def _modal(self, modal):
        raise AssertionError("An unlinked user must never get a registration modal")


def fake_settings(*, season="web-qa-2026"):
    return SimpleNamespace(
        guild_id=GUILD, season_key=season, mode="production",
        is_test=False, admin_user_ids=frozenset(),
    )


def test_linked_account_gate_handles_disconnect_unlinked_and_db_outage():
    async def scenario():
        linked = FakeIdentity(6_000_000_000_000_000_005)
        assert await require_linked_discord(FakeInteraction(linked))
        assert linked.lookups == [str(ACTOR)]

        old = FakeIdentity(failure=IdentityError("Link does not exist"))
        interaction = FakeInteraction(old)
        assert not await require_linked_discord(interaction)
        assert len(interaction.responded) == 1
        assert interaction.responded[0][1]["ephemeral"] is True
        assert "Link your Discord login" in interaction.responded[0][0]

        outage = FakeIdentity(failure=RuntimeError("secret host and database password"))
        prior = FakeInteraction(outage, response_done=True)
        assert not await require_linked_discord(prior)
        assert prior.followed[0][1]["ephemeral"] is True
        assert "password" not in prior.followed[0][0]
        assert not prior.responded

        legacy = FakeInteraction(None)
        assert await require_linked_discord(legacy)
        assert legacy.responded == []
    asyncio.run(scenario())


def test_all_legacy_views_reject_unlinked_clicks_and_accept_linked_owner():
    async def scenario():
        settings = fake_settings()
        store = SimpleNamespace()
        views = (
            MenuView(settings, store, ACTOR),
            CombatMenu(settings, store, ACTOR),
            EconomyView(settings, store, ACTOR),
            WorldView(settings, store, ACTOR),
            WorldConfirm(settings, store, ACTOR, "boss"),
            Dashboard(settings, store),
        )
        for view in views:
            unlinked = FakeInteraction(FakeIdentity(failure=IdentityError("not linked")))
            assert not await view.interaction_check(unlinked), type(view).__name__
            assert unlinked.responded and unlinked.responded[0][1]["ephemeral"]
            linked = FakeInteraction(FakeIdentity(6_000_000_000_000_000_002))
            assert await view.interaction_check(linked), type(view).__name__
            wrong_user = FakeInteraction(FakeIdentity(6_000_000_000_000_000_003),
                                         who=ACTOR + 1)
            if isinstance(view, Dashboard):
                assert await view.interaction_check(wrong_user)
            else:
                assert not await view.interaction_check(wrong_user)

        picker = CityPicker(settings, store, ACTOR)
        city_option = next(c for c in picker.children if hasattr(c, "options"))
        unlinked = FakeInteraction(FakeIdentity(failure=IdentityError("not linked")))
        await city_option.callback(unlinked)
        assert unlinked.responded and unlinked.responded[0][1]["ephemeral"]

        modal = JoinModal(settings, store, "Chicago")
        # Simulate an old CityPicker/modal that remained open before the player
        # unlinked. The write cannot happen even with a valid declaration.
        modal.declaration._value = "I AGREE"
        modal.mr_username._value = "OldStandalone"
        unlinked = FakeInteraction(FakeIdentity(failure=IdentityError("not linked")))
        await modal.on_submit(unlinked)
        assert unlinked.responded and unlinked.responded[0][1]["ephemeral"]
    asyncio.run(scenario())


def test_qa_help_cannot_promise_prizes_or_unlinked_discord_play():
    settings = fake_settings()
    rules = rules_text(settings)
    assert "verified Underworld character" in rules
    assert "no real prizes" in rules.lower()
    assert "No MR password or account linking" not in rules
    assert "\\n" not in rules  # should contain real line breaks
    original = rules_text(fake_settings(season="christmas-2026"))
    assert "Self-declare" in original
    assert "Only individual awards receive prizes" in original


def test_qa_dashboard_footer_and_full_description():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    season = SimpleNamespace(
        phase=lambda at: "live",
        registration_opens=lambda: now - timedelta(days=7),
        planned_start=now - timedelta(days=1),
        projected_end=lambda at: now + timedelta(days=6),
        day=lambda at: 2,
    )
    qa = dashboard_embed(fake_settings(), season, now, 2)
    assert "SHARED QA" in qa.title
    assert "NO PRIZES" in qa.footer.text
    assert "Scheduled kickoff:" in qa.description
    assert "QA only — no prizes" in qa.description
    live = dashboard_embed(fake_settings(season="christmas-2026"), season, now, 2)
    assert "Scheduled kickoff:" in live.description
    assert "Individual only" in live.description
