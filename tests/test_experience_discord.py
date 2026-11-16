"""v0.1.7 private Discord HQ, target finder and tutorial contracts."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("discord")

from snowfall.commands.public import SnowGroup  # noqa: E402
from snowfall.db.store import Store  # noqa: E402
from snowfall.services.combat import TargetView  # noqa: E402
from snowfall.ui.combat import TargetPicker, ThrowMenu, suggested_targets  # noqa: E402
from snowfall.ui.headquarters import (  # noqa: E402
    HeadquartersView, WelcomeTour,
)
from snowfall.ui.navigation import MainMenu, GameMenu, PlayerMenu  # noqa: E402

NOW = datetime.now(timezone.utc)


def fixture(tmp_path):
    store = Store(tmp_path / 'event.sqlite3')
    store.initialize()
    store.ensure_season('event', NOW + timedelta(days=4))
    settings = SimpleNamespace(season_key='event', guild_id=445, admin_user_ids=frozenset(),
                               mode='production')
    return settings, store


class Response:
    def __init__(self):
        self.defers, self.messages, self.edits = [], [], []

    async def defer(self, **k):
        self.defers.append(k)

    async def edit_message(self, **k):
        self.edits.append(k)

    async def send_message(self, *a, **k):
        self.messages.append((a, k))


class Interaction:
    def __init__(self, user_id=13):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id, self.channel_id = 445, 543
        self.client = SimpleNamespace(practice=None)
        self.response = Response()
        self.edits = []

    async def edit_original_response(self, **k):
        self.edits.append(k)


def button(view, label):
    return next(x for x in view.children if getattr(x, 'label', None) == label)


def test_menu_construction_and_discord_slash_command_limit(tmp_path):
    settings, store = fixture(tmp_path)
    assert len(SnowGroup(settings, store).commands) <= 25
    assert {'hq', 'guide'} <= {x.name for x in SnowGroup(settings, store).commands}
    menus = (MainMenu(settings, store, 13), GameMenu(settings, store, 13),
             PlayerMenu(settings, store, 13))
    for view in menus:
        assert any('Headquarters' in x.label for x in view.children if x.label)
    for view in (*menus, HeadquartersView(settings, store, 13)):
        assert all(x.row is None or 0 <= x.row <= 4 for x in view.children)
        assert len(view.children) <= 25


def test_headquarters_is_private_and_edits_original_message(tmp_path):
    settings, store = fixture(tmp_path)
    view = HeadquartersView(settings, store, 13)
    async def scenario():
        other = Interaction(user_id=55)
        assert not await view.interaction_check(other)
        assert other.response.messages
        owner = Interaction()
        assert await view.interaction_check(owner)
        await button(view, 'Refresh').callback(owner)
        assert owner.response.defers and len(owner.edits) == 1
        assert isinstance(owner.edits[0]['view'], HeadquartersView)
        assert owner.edits[0]['embed'].description.startswith('**Welcome')
    asyncio.run(scenario())


def test_welcome_tour_step_bounds_and_no_registration_without_window(tmp_path):
    settings, store = fixture(tmp_path)
    first = WelcomeTour(settings, store, 13, 0)
    last = WelcomeTour(settings, store, 13, 2)
    assert '◀ Previous' not in {x.label for x in first.children}
    assert 'Next ▶' not in {x.label for x in last.children}
    assert 'Join / Register' in {x.label for x in last.children}
    async def scenario():
        owner = Interaction()
        await button(first, 'Next ▶').callback(owner)
        assert isinstance(owner.edits[-1]['view'], WelcomeTour)
        assert owner.edits[-1]['view'].step == 1
        other = Interaction(55)
        assert not await first.interaction_check(other)
    asyncio.run(scenario())


def test_smart_rival_finder_prefers_fresh_healthy_legal_targets():
    targets = [TargetView(31, 'Fragile', 'Detroit', 19, 2),
               TargetView(22, 'Fresh', 'New York', 94, 2),
               TargetView(21, 'HitOnce', 'Los Angeles', 100, 1)]
    assert [t.discord_user_id for t in suggested_targets(targets)] == [22, 31, 21]
    assert [t.discord_user_id for t in targets] == [31, 22, 21]  # no mutation


def test_target_selection_buttons_recheck_against_live_engine(tmp_path, monkeypatch):
    settings, store = fixture(tmp_path)
    targets = [TargetView(31, 'Other', 'Detroit', 50, 2),
               TargetView(22, 'Fresh', 'New York', 99, 2)]
    from snowfall.services.combat import CombatEngine
    monkeypatch.setattr(CombatEngine, 'targets', lambda self, *a, **k: targets)
    picker = TargetPicker(settings, store, 13, targets)
    async def scenario():
        chosen = Interaction()
        await button(picker, 'Recommended Rival').callback(chosen)
        view = chosen.response.edits[-1]['view']
        assert isinstance(view, ThrowMenu) and view.target_id == 22
        random = Interaction()
        monkeypatch.setattr('snowfall.ui.combat.secrets.choice', lambda pool: pool[0])
        await button(picker, 'Surprise Me').callback(random)
        assert random.response.edits[-1]['view'].target_id == 31
        # Never execute a combat attack during a target selection.
        with store.connect() as con:
            assert con.execute('SELECT COUNT(*) FROM combat_events').fetchone()[0] == 0
    asyncio.run(scenario())
