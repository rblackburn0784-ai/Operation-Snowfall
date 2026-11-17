"""v0.2.1: state-aware suggestions, daily hub and privacy-safe menu contracts."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from snowfall.db.store import Store, _timestamp
from snowfall.services.combat import CombatEngine
from snowfall.services.economy import EconomyEngine
from snowfall.services.experience import headquarters

KEY = "ux-v021"
START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    store = Store(tmp_path / "ux.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    return store


def registered(store):
    store.register(KEY, 101, "TheDude", "Chicago", START - timedelta(days=1))


def live(store):
    registered(store)
    store.transition(KEY, 900, "start", START, "Live test")


def test_recommendation_registration_and_pre_event(db):
    status = headquarters(db, KEY, 101, START - timedelta(days=8))
    assert status.next_action_route == "guide"
    status = headquarters(db, KEY, 101, START - timedelta(days=1))
    assert status.next_action_route == "join"
    registered(db)
    status = headquarters(db, KEY, 101, START - timedelta(hours=1))
    assert status.next_action_route == "guide"
    assert status.arena_until is None


def test_recommendation_claim_present_and_arena(db):
    live(db)
    state = headquarters(db, KEY, 101, START)
    assert state.next_action_route == "player"  # voluntary opt-in first
    assert state.daily_gift == "Claim a quest"
    EconomyEngine(db).guard(KEY, 101, "on", "v021-guard", START)
    state = headquarters(db, KEY, 101, START)
    assert state.next_action_route == "quests"  # complete quest beats PvE
    EconomyEngine(db).claim_quest(KEY, 101, "community", START)
    state = headquarters(db, KEY, 101, START)
    assert state.daily_gift == "Ready"
    assert state.next_action_route == "quests"
    EconomyEngine(db).present(KEY, 101, "v021-gift", START)
    state = headquarters(db, KEY, 101, START)
    assert state.daily_gift == "Opened"
    # The existing economy actions already count as arena activity.
    assert state.next_action_route == "world"
    assert state.arena_until is not None
    CombatEngine(db).ready(KEY, 101, START)
    state = headquarters(db, KEY, 101, START + timedelta(seconds=1))
    assert state.arena_until == START + timedelta(hours=36)
    assert state.next_action_route == "world"


def test_recommendation_ko_pause_and_closure(db):
    live(db)
    CombatEngine(db).ready(KEY, 101, START)
    with db.connect() as con:
        con.execute("UPDATE player_resources SET knockout_until=? "
                    "WHERE season_key=? AND discord_user_id=?",
                    (_timestamp(START + timedelta(minutes=10)), KEY, 101))
    in_ko = headquarters(db, KEY, 101, START + timedelta(seconds=3))
    assert in_ko.next_action_route == "arcade"
    assert in_ko.knockout_due == START + timedelta(minutes=10)
    db.transition(KEY, 900, "pause", START + timedelta(seconds=5), "Test pause")
    frozen = headquarters(db, KEY, 101, START + timedelta(hours=1))
    assert frozen.next_action_route == "hq"
    assert frozen.knockout_due is None and frozen.arena_until is None
    db.transition(KEY, 900, "resume", START + timedelta(hours=1), "Resume")
    ended = headquarters(db, KEY, 101, START + timedelta(days=9))
    assert ended.next_action_route == "rankings"


def test_today_embed_and_menu_edit_privacy(db, monkeypatch):
    pytest.importorskip("discord")
    from snowfall.ui import today as ux
    from snowfall.ui.navigation import MainMenu, GameMenu
    from snowfall.ui.headquarters import HeadquartersView

    live(db)
    settings = SimpleNamespace(season_key=KEY, mode="production", guild_id=123,
                               admin_user_ids=frozenset())
    monkeypatch.setattr(ux, "_now", lambda: START)
    info = headquarters(db, KEY, 101, START)
    embed = ux.today_embed(info, settings)
    assert "0/3" in embed.fields[0].name
    assert "Claim a quest" in str(embed.fields[1].value)
    assert "Do Next" in {item.label for item in ux.TodayView(settings, db, 101).children}
    for cls in (MainMenu, GameMenu, HeadquartersView):
        labels = {item.label for item in cls(settings, db, 101).children}
        assert {"Today", "Do Next"} <= labels

    class Response:
        def __init__(self):
            self.messages = []
            self.defers = []
        async def defer(self, **kw):
            self.defers.append(kw)
        async def send_message(self, *args, **kw):
            self.messages.append((args, kw))

    class Interaction:
        def __init__(self, actor=101):
            self.user = SimpleNamespace(id=actor)
            self.guild_id, self.channel_id = 123, 445
            self.client = SimpleNamespace(practice=None)
            self.response = Response()
            self.edits = []
        async def edit_original_response(self, **kw):
            self.edits.append(kw)

    async def inspect():
        interaction = Interaction()
        await ux.show_today(interaction, settings, db, 101)
        assert isinstance(interaction.edits[-1]["view"], ux.TodayView)
        assert interaction.edits[-1]["allowed_mentions"].everyone is False
        await ux.quick_action(interaction, settings, db, 101)
        from snowfall.ui.navigation import PlayerMenu
        assert isinstance(interaction.edits[-1]["view"], PlayerMenu)
        stranger = Interaction(actor=202)
        await ux.quick_action(stranger, settings, db, 101)
        assert not stranger.edits
        assert stranger.response.messages
        # Navigation is never a score or purchase transaction.
        assert CombatEngine(db).ledger_total(KEY, 101) == 0
        with db.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM item_events").fetchone()[0] == 0

    asyncio.run(inspect())


def test_today_card_unregistered_and_pause(db):
    pytest.importorskip("discord")
    from snowfall.ui.today import today_embed

    settings = SimpleNamespace(mode="production")
    unregistered = headquarters(db, KEY, 101, START - timedelta(days=1))
    card = today_embed(unregistered, settings)
    assert "Not registered" in card.description
    live(db)
    db.transition(KEY, 900, "pause", START + timedelta(seconds=5), "Paused")
    info = headquarters(db, KEY, 101, START + timedelta(minutes=30))
    card = today_embed(info, settings)
    assert "Frozen during pause" in str(card.fields[-2].value)
