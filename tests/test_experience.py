"""v0.1.7 Headquarters: real clocks, read-model boundaries and rewards."""
from datetime import datetime, timedelta, timezone

import pytest

from snowfall.db.store import Store
from snowfall.services.combat import CombatEngine
from snowfall.services.economy import EconomyEngine
from snowfall.services.experience import headquarters, _wall_due
from snowfall.services.world import WorldEngine

KEY = "experience-2026"
START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "experience.sqlite3")
    db.initialize()
    db.ensure_season(KEY, START)
    return db


def go_live(db):
    db.register(KEY, 11, "SnowTheDude", "Chicago", START - timedelta(days=1))
    db.register(KEY, 22, "SomeRival", "New York", START - timedelta(days=1))
    db.transition(KEY, 900, "start", START, "Gameplay start")


def test_unregistered_account_cannot_gain_inventory_or_rank(store):
    status = headquarters(store, KEY, 999, START - timedelta(hours=5))
    assert status.player is None
    assert status.season_points == status.daily_points == 0
    assert status.rank is None and status.resources is None and not status.quests
    assert status.phase == "registration"
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM player_resources").fetchone()[0] == 0


def test_registered_preseason_headquarters_has_no_fake_regeneration(store):
    store.register(KEY, 11, "SnowTheDude", "Chicago", START - timedelta(days=1))
    status = headquarters(store, KEY, 11, START - timedelta(minutes=5))
    assert status.player.mr_username == "SnowTheDude"
    assert status.next_snowball is None and status.next_reset is None
    assert status.resources.snowballs == 8 and status.resources.warmth == 100
    assert status.phase == "registration" and status.quests == ()
    assert status.rank is None  # zero score must not be represented as first place


def test_accurate_regen_throw_cooldown_and_day_reset(store):
    go_live(store)
    combat = CombatEngine(store)
    combat.ready(KEY, 22, START)
    combat.throw(KEY, 11, 22, "quick", "one-shot", START)
    at = START + timedelta(seconds=5)
    result = headquarters(store, KEY, 11, at)
    assert result.phase == "live" and result.day == 1
    assert result.next_snowball == START + timedelta(minutes=20)
    assert result.next_warmth is None
    assert result.next_throw == START + timedelta(seconds=30)
    assert result.next_reset == START + timedelta(days=1)
    assert result.resources.snowballs == 7
    assert result.rank in (1, 2) if result.season_points > 0 else result.rank is None
    # A refresh must not prematurely consume snowballs or rewrite scores.
    old = combat.ledger_total(KEY, 11)
    assert headquarters(store, KEY, 11, at).resources.snowballs == 7
    assert combat.ledger_total(KEY, 11) == old
    later = headquarters(store, KEY, 11, START + timedelta(minutes=20))
    assert later.resources.snowballs == 8
    assert later.next_snowball == START + timedelta(minutes=40)
    assert later.next_throw is None


def test_pause_freezes_regeneration_and_reset_times(store):
    go_live(store)
    combat = CombatEngine(store)
    combat.ready(KEY, 22, START)
    combat.throw(KEY, 11, 22, "quick", "one-shot", START)
    paused_at = START + timedelta(seconds=10)
    store.transition(KEY, 900, "pause", paused_at, "Host safety pause")
    during_pause = headquarters(store, KEY, 11, START + timedelta(hours=4))
    assert during_pause.phase == "paused"
    assert during_pause.next_snowball is None
    assert during_pause.next_reset is None
    assert during_pause.next_throw is None
    assert "frozen" in during_pause.next_action
    assert during_pause.resources.snowballs == 7


def test_daily_quests_and_present_prompt_are_truthful(store):
    go_live(store)
    assert headquarters(store, KEY, 11, START).daily_gift == "Claim a quest"
    e = EconomyEngine(store)
    e.guard(KEY, 11, "on", "guard-1", START)
    ready = headquarters(store, KEY, 11, START)
    assert any(q.key == "community" and q.progress == 1 for q in ready.quests)
    assert "quest" in ready.next_action.lower()
    e.claim_quest(KEY, 11, "community", START)
    opened = headquarters(store, KEY, 11, START)
    assert opened.daily_gift == "Ready"
    assert opened.season_points == 20
    assert opened.daily_points == 20
    e.present(KEY, 11, "gift-1", START)
    done = headquarters(store, KEY, 11, START)
    assert done.daily_gift == "Opened"


def test_day_four_no_unearned_extra_present(store):
    go_live(store)
    at = START + timedelta(days=3)
    WorldEngine(store).tick(KEY, at)
    data = headquarters(store, KEY, 11, at)
    assert data.day == 4 and data.bonus_gift == "Claim all three"
    assert data.next_reset == START + timedelta(days=4)


def test_wall_time_projection_never_counts_down_paused_clock(store):
    go_live(store)
    season = store.season(KEY)
    assert _wall_due(season, START, START + timedelta(minutes=1)) == START + timedelta(minutes=1)
    assert _wall_due(season, START, START - timedelta(seconds=1)) is None
    assert _wall_due(season, START, None) is None
