"""Fake Discord transport verifying text-only fallback and stable message edits."""
import asyncio
from types import SimpleNamespace

import pytest

discord = pytest.importorskip("discord")

from snowfall.commands.public import SnowGroup  # noqa: E402
from snowfall.graphics import delivery  # noqa: E402
from snowfall.ui.dashboard import Dashboard  # noqa: E402
from snowfall.ui.world import WorldView  # noqa: E402


class FakeInteraction:
    def __init__(self):
        self.calls = []
        self.followup = SimpleNamespace(send=self.send)

    async def edit_original_response(self, **kwargs):
        self.calls.append(("edit", kwargs))

    async def send(self, **kwargs):
        self.calls.append(("send", kwargs))


def test_media_edit_uses_existing_message_once_and_has_alt_text():
    async def scenario():
        fake = FakeInteraction()
        await delivery.edit_result(fake, "You scored 20 points!", None,
                                   lambda: b"valid-picture", alt="Snowball critical hit")
        assert len(fake.calls) == 1
        action, args = fake.calls[0]
        assert action == "edit" and args["content"] == "You scored 20 points!"
        assert args["attachments"][0].description == "Snowball critical hit"
        assert args["embed"].image.url == "attachment://snowfall.png"
    asyncio.run(scenario())


def test_media_generation_failure_falls_back_to_full_text():
    async def scenario():
        fake = FakeInteraction()
        def fail():
            raise OSError("File unavailable")
        await delivery.edit_result(fake, "My hit is saved: +23 points!", None,
                                   fail, alt="fallback")
        assert len(fake.calls) == 1
        _, args = fake.calls[0]
        assert args["content"].startswith("My hit is saved")
        assert args["attachments"] == [] and args["embed"] is None
    asyncio.run(scenario())


def test_profile_fallback_uses_one_ephemeral_message(monkeypatch):
    async def scenario():
        fake = FakeInteraction()
        monkeypatch.setattr(delivery.cards, "profile_card", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        await delivery.send_profile(fake, "Full text remains", "TheDude", "Chicago", None, 25)
        assert len(fake.calls) == 1
        action, args = fake.calls[0]
        assert action == "send" and args["content"] == "Full text remains"
        assert args["ephemeral"] is True and args["allowed_mentions"].everyone is False
    # Test all controls without sending a real Discord message.
    asyncio.run(scenario())


def test_mobile_navigation_has_one_persistent_dashboard_and_public_podium():
    group = SnowGroup(SimpleNamespace(guild_id=13, season_key="season"), object())
    assert "champions" in {c.name for c in group.commands}
    dashboard = Dashboard(SimpleNamespace(guild_id=13), object())
    assert len(dashboard.children) <= 25
    assert all(getattr(control, "row", None) is None or control.row <= 4
               for control in dashboard.children)
    assert any(control.custom_id == "snowfall:v1:podium" for control in dashboard.children)
    world_view = WorldView(SimpleNamespace(guild_id=13), object(), 7)
    assert len(world_view.children) <= 6
    assert "Raid Headquarters" in {getattr(b, "label", None) for b in world_view.children}
