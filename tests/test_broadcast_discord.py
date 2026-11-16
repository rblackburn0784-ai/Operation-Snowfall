"""Live-library contract tests with a fake transport; no Discord gateway connection."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

discord = pytest.importorskip("discord")

from snowfall.config import Settings  # noqa: E402
from snowfall.db.store import Store  # noqa: E402
from snowfall.services.world import WorldEngine  # noqa: E402
from snowfall.ui.broadcast import BroadcastPublisher  # noqa: E402

START = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
KEY = "broadcast-discord-testing"
GUILD = 4567
LEADERBOARD = 777701
ANNOUNCEMENTS = 777702
BOT_USER = 9000


class FakeMessage:
    def __init__(self, channel, msg_id, *, content=None, embed=None):
        self.channel = channel
        self.id = msg_id
        self.content = content
        self.embeds = [embed] if embed else []
        self.author = SimpleNamespace(id=BOT_USER)
        self.edits = 0
        self.jump_url = f"https://discord.example/channels/{GUILD}/{channel.id}/{self.id}"

    async def edit(self, *, content=None, embed=None, **_):
        self.content = content
        self.embeds = [embed] if embed else []
        self.edits += 1
        return self

    async def delete(self):
        self.channel.messages.pop(self.id, None)


class FakeChannel:
    def __init__(self, id, guild_id=GUILD):
        self.id = id
        self.guild = SimpleNamespace(id=guild_id)
        self.messages = {}
        self.sends = 0

    async def send(self, content=None, *, embed=None, **_):
        self.sends += 1
        msg = FakeMessage(self, self.id * 10 + self.sends,
                          content=content, embed=embed)
        self.messages[msg.id] = msg
        return msg

    async def fetch_message(self, msg_id):
        return self.messages[msg_id]

    async def history(self, limit=100):
        for msg in list(self.messages.values())[-limit:][::-1]:
            yield msg


class FakeBot:
    def __init__(self, channels):
        self.channels = {c.id: c for c in channels}
        self.user = SimpleNamespace(id=BOT_USER)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id):
        return self.channels[channel_id]


def setup(tmp_path):
    store = Store(tmp_path / "snowfall.db")
    store.initialize()
    store.ensure_season(KEY, START)
    store.register(KEY, 42, "SnowDude", "Chicago", START - timedelta(days=2))
    settings = Settings("not-a-real-token", GUILD, frozenset({900}), KEY,
                        "Operation Snowfall", START, tmp_path / "snowfall.db",
                        announcement_channel_id=ANNOUNCEMENTS,
                        leaderboard_channel_id=LEADERBOARD)
    board = FakeChannel(LEADERBOARD)
    announcements = FakeChannel(ANNOUNCEMENTS)
    publisher = BroadcastPublisher(FakeBot([board, announcements]), settings, store)
    return store, board, announcements, publisher


def test_five_minute_single_board_edits_after_restart(tmp_path):
    async def scenario():
        store, board, notices, publisher = setup(tmp_path)
        first = await publisher.update_leaderboard(START - timedelta(days=1))
        assert board.sends == 1 and len(board.messages) == 1
        assert len(first.embeds) == 1
        assert "Individual" in first.embeds[0].fields[0].name
        assert "City" in first.embeds[0].fields[1].name
        assert store.get_published(KEY, "leaderboard") == (board.id, first.id)
        second = await publisher.update_leaderboard(START - timedelta(days=1, minutes=-5))
        assert second.id == first.id and first.edits == 1
        assert board.sends == 1
        # New bot process, same saved DB message ID.
        restarted = BroadcastPublisher(publisher.bot, publisher.settings, store)
        third = await restarted.update_leaderboard(START)
        assert third.id == first.id and board.sends == 1 and first.edits == 2
        assert notices.sends == 0
    asyncio.run(scenario())


def test_migrate_two_legacy_boards_into_one_existing_message(tmp_path):
    async def scenario():
        store, board, _, publisher = setup(tmp_path)
        individual = await board.send("Legacy individual")
        city = await board.send("Legacy city")
        store.record_published(KEY, 900, "individual_board", board.id, individual.id, START)
        store.record_published(KEY, 900, "city_board", board.id, city.id, START)
        new = await publisher.update_leaderboard(START)
        assert new.id == individual.id
        assert board.sends == 2  # No third message
        assert list(board.messages) == [individual.id]
        assert store.get_published(KEY, "leaderboard") == (board.id, individual.id)
    asyncio.run(scenario())


def test_recover_orphaned_send_without_creating_duplicate(tmp_path):
    async def scenario():
        store, board, _, publisher = setup(tmp_path)
        first = await publisher.update_leaderboard(START)
        with store.connect() as con:
            con.execute("DELETE FROM published_messages WHERE season_key=? AND message_kind=?",
                        (KEY, "leaderboard"))
        restarted = BroadcastPublisher(publisher.bot, publisher.settings, store)
        found = await restarted.update_leaderboard(START + timedelta(minutes=5))
        assert found.id == first.id and board.sends == 1
        assert store.get_published(KEY, "leaderboard") == (board.id, first.id)
    asyncio.run(scenario())


def test_announcements_once_per_phase_day_boss_defeat_and_conclusion(tmp_path):
    async def scenario():
        store, _, notices, publisher = setup(tmp_path)
        before_start = START - timedelta(days=1)
        await publisher.ensure_announcements(before_start)
        await publisher.ensure_announcements(before_start)
        assert notices.sends == 1
        assert "REGISTRATION IS OPEN" in next(iter(notices.messages.values())).content
        # The ready phase (host has not started yet) is a different once-only notice.
        await publisher.ensure_announcements(START)
        assert notices.sends == 2
        store.transition(KEY, 900, "start", START, "test")
        WorldEngine(store).tick(KEY, START)
        await publisher.ensure_announcements(START)
        await publisher.ensure_announcements(START)
        assert notices.sends == 3
        with store.connect() as con:
            con.execute("UPDATE world_days SET boss_hp=0 WHERE season_key=? AND day=1",
                        (KEY,))
        await publisher.ensure_announcements(START + timedelta(minutes=1))
        await publisher.ensure_announcements(START + timedelta(minutes=2))
        assert notices.sends == 4
        WorldEngine(store).tick(KEY, START + timedelta(days=1))
        await publisher.ensure_announcements(START + timedelta(days=1))
        assert notices.sends == 5
        assert "Fortification Frenzy" in list(notices.messages.values())[-1].content
        await publisher.ensure_announcements(START + timedelta(days=7))
        await publisher.ensure_announcements(START + timedelta(days=7))
        assert notices.sends == 6
        assert "LAST SNOWBALL" in list(notices.messages.values())[-1].content
    asyncio.run(scenario())


def test_manual_reannounce_edits_in_place_and_recovers_orphan(tmp_path):
    async def scenario():
        store, _, notices, publisher = setup(tmp_path)
        store.transition(KEY, 900, "start", START, "test")
        WorldEngine(store).tick(KEY, START)
        first = await publisher.publish_current_day(START)
        assert notices.sends == 1
        again = await publisher.publish_current_day(START, refresh_existing=True)
        assert again.id == first.id and first.edits == 1 and notices.sends == 1
        with store.connect() as con:
            con.execute("DELETE FROM published_messages WHERE season_key=? AND message_kind=?",
                        (KEY, "theme_day_1"))
        restarted = BroadcastPublisher(publisher.bot, publisher.settings, store)
        await restarted.ensure_announcements(START + timedelta(minutes=2))
        assert notices.sends == 1
    asyncio.run(scenario())


def test_wrong_guild_channel_is_rejected_without_post(tmp_path):
    async def scenario():
        _, board, _, publisher = setup(tmp_path)
        board.guild.id = 999999
        with pytest.raises(ValueError, match="not in the configured event server"):
            await publisher.update_leaderboard(START)
        assert board.sends == 0
    asyncio.run(scenario())


def test_embedded_discord_schedule_is_exactly_five_minutes():
    from snowfall.app import SnowfallBot
    assert SnowfallBot.refresh_leaderboard.minutes == [5.0]
    assert SnowfallBot.refresh_world.minutes == [1.0]
