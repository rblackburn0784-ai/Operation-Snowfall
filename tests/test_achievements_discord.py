"""Discord menu contracts for cosmetic titles and achievements."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip('discord')

from snowfall.db.store import Store
from snowfall.services.achievements import AchievementEngine
from snowfall.ui.trophies import TrophyCabinet, TitleChooser, cabinet_text, records_embed


def fixture(tmp_path):
    store = Store(tmp_path / 'trophy_menu.sqlite3')
    store.initialize()
    now = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
    store.ensure_season('menu-test', now)
    store.register('menu-test', 27, 'SnowDude', 'Chicago', now)
    return SimpleNamespace(guild_id=12345, season_key='menu-test',
                           admin_user_ids=frozenset(), mode='production'), store


def test_trophy_buttons_and_record_layout(tmp_path):
    config, store = fixture(tmp_path)
    view = TrophyCabinet(config, store, 27)
    labels = {i.label for i in view.children if i.label}
    assert {'Equip Title', 'Combat Records', 'Game Menus', 'Home', 'Headquarters'} <= labels
    assert all(i.row is None or 0 <= i.row <= 4 for i in view.children)
    cab = AchievementEngine(store).cabinet('menu-test', 27)
    assert '0/16' in cabinet_text(cab)
    assert 'SnowDude' in records_embed(cab).description
    choice = TitleChooser(config, store, 27, cab)
    selects = [item for item in choice.children if hasattr(item, 'options')]
    assert len(selects) == 1
    assert {o.value for o in selects[0].options} == {'none'}
    assert not any(getattr(i, 'custom_id', '').startswith('admin') for i in choice.children)
