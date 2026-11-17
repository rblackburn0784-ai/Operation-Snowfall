"""Discord-free gateway fakes prove wire notices don't duplicate after restart."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

discord = pytest.importorskip("discord")

from snowfall.config import Settings  # noqa: E402
from snowfall.db.store import Store  # noqa: E402
from snowfall.services.world import WorldEngine  # noqa: E402
from snowfall.ui.broadcast import BroadcastPublisher  # noqa: E402
from snowfall.ui.community import CityHubView  # noqa: E402

START = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
KEY = "wire-demo-2026"


class Message:
    def __init__(self, channel, id, content):
        self.channel = channel
        self.id = id
        self.content = content
        self.author = SimpleNamespace(id=500)
        self.embeds = []

    async def edit(self, content=None, **_):
        self.content = content
        return self


class Channel:
    def __init__(self):
        self.id = 7002
        self.guild = SimpleNamespace(id=4242)
        self.sends = 0
        self.messages = {}

    async def send(self, content, **_):
        self.sends += 1
        msg = Message(self, 100 + self.sends, content)
        self.messages[msg.id] = msg
        return msg

    async def fetch_message(self, id):
        return self.messages[id]

    async def history(self, limit=100):
        for msg in list(self.messages.values())[-limit:][::-1]:
            yield msg


class Bot:
    def __init__(self, channel):
        self.channel = channel
        self.user = SimpleNamespace(id=500)

    def get_channel(self, id):
        return self.channel if self.channel.id == id else None


def setup(tmp_path):
    store = Store(tmp_path / "local.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    store.register(KEY, 1, "TheDude", "Chicago", START - timedelta(days=2))
    store.transition(KEY, 600, "start", START, "test")
    WorldEngine(store).tick(KEY, START)
    channel = Channel()
    settings = Settings("TOKEN", 4242, frozenset({600}), KEY, "Operation Snowfall",
                        START, store.path, announcement_channel_id=channel.id)
    return store, channel, BroadcastPublisher(Bot(channel), settings, store)


def test_wire_one_report_after_each_completed_day_and_restart(tmp_path):
    async def scenario():
        store, channel, publisher = setup(tmp_path)
        assert await publisher.publish_wire_recaps(START + timedelta(hours=23)) is None
        assert channel.sends == 0
        first = await publisher.publish_wire_recaps(START + timedelta(days=1))
        assert first is not None and channel.sends == 1
        assert "DAY 1/7" in first.content and "No city qualified" in first.content
        assert "Snowfall marker:" in first.content
        assert await publisher.publish_wire_recaps(START + timedelta(days=1, minutes=1)) is None
        restarted = BroadcastPublisher(publisher.bot, publisher.settings, store)
        assert await restarted.publish_wire_recaps(START + timedelta(days=1, minutes=2)) is None
        assert channel.sends == 1
        second = await restarted.publish_wire_recaps(START + timedelta(days=2))
        assert second is not None and channel.sends == 2
        assert "DAY 2/7" in second.content
        # A long outage recovers at most one issue per scheduler invocation.
        for n in range(3, 8):
            await restarted.publish_wire_recaps(START + timedelta(days=7))
        assert channel.sends == 7
        assert await restarted.publish_wire_recaps(START + timedelta(days=7)) is None
        assert store.get_published(KEY, "wire_day_7") is not None
    asyncio.run(scenario())


def test_wire_does_not_post_before_kickoff(tmp_path):
    store = Store(tmp_path / "data.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    channel = Channel()
    settings = Settings("TOKEN", 4242, frozenset({600}), KEY, "Operation Snowfall",
                        START, store.path, announcement_channel_id=channel.id)
    publisher = BroadcastPublisher(Bot(channel), settings, store)
    assert asyncio.run(publisher.publish_wire_recaps(START + timedelta(days=4))) is None
    assert channel.sends == 0


def test_city_hq_view_owner_and_navigation_layout(tmp_path):
    store, _, publisher = setup(tmp_path)
    view = CityHubView(publisher.settings, store, 1)
    labels = {x.label for x in view.children}
    assert {"City HQ", "Co-op Mission", "Rivalries", "Snowfall Wire", "Home"} <= labels
    assert len(view.children) <= 25
    assert all(x.row is None or 0 <= x.row <= 4 for x in view.children)
