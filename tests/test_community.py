"""Community statistics are independent of individual scores and paid rewards."""
from datetime import datetime, timedelta, timezone

import pytest

from snowfall.db.store import Store
from snowfall.services.community import CommunityEngine, CommunityError, wire_story
from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine

START = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
KEY = "community-2026"


class FixedMissRNG:
    def random(self):
        return 0.99


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "city.sqlite3")
    db.initialize()
    db.ensure_season(KEY, START)
    for uid, name, city in [(11, "TheDude", "Chicago"), (12, "Santa Joe", "Chicago"),
                             (21, "Frost Jack", "New York"), (31, "Ice Tom", "Detroit")]:
        db.register(KEY, uid, name, city, START - timedelta(days=2))
    return db


def go_live(store):
    store.transition(KEY, 11, "start", START, "community test")
    WorldEngine(store).tick(KEY, START)


def test_new_city_headquarters_and_unregistered_rejection(store):
    engine = CommunityEngine(store)
    pre = engine.headquarters(KEY, 11, START - timedelta(hours=1))
    assert pre.city == "Chicago"
    assert pre.day is None and pre.objective is None
    assert pre.members == 2
    assert len(pre.rivalries) == 5
    with pytest.raises(CommunityError, match="Register first"):
        engine.headquarters(KEY, 90000, START)
    go_live(store)
    info = engine.headquarters(KEY, 11, START)
    assert info.day == 1 and info.objective.target == 4
    assert info.objective.progress == 0 and not info.objective.completed
    assert info.city_siege_hp is not None


def test_city_objective_and_rivalry_are_read_only(store):
    go_live(store)
    combat = CombatEngine(store, FixedMissRNG())
    combat.ready(KEY, 21, START)
    for n in range(4):
        # Two scoring hits per target per day still applies; the city challenge
        # also counts legal misses/throws, not duplicate/replayed requests.
        for uid in (11, 12):
            if n < 2:
                t = START + timedelta(seconds=31 * (n + 1) + (uid - 11) * 100)
                combat.throw(KEY, uid, 21, "quick", f"city-{n}-{uid}", t)
    engine = CommunityEngine(store)
    info = engine.headquarters(KEY, 11, START + timedelta(minutes=10))
    assert info.objective.progress == 4 and info.objective.completed
    ny = next(r for r in info.rivalries if r.opponent == "New York")
    assert ny.throws == 4 and ny.hits == 0
    before = CombatEngine(store).ledger_total(KEY, 11)
    for _ in range(3):
        assert engine.headquarters(KEY, 11, START + timedelta(minutes=10)).objective.completed
    assert CombatEngine(store).ledger_total(KEY, 11) == before


def test_wire_requires_finished_day_and_reports_only_recorded_facts(store):
    go_live(store)
    engine = CommunityEngine(store)
    with pytest.raises(CommunityError, match="not complete"):
        engine.recap(KEY, 1, START + timedelta(hours=23))
    news = engine.recap(KEY, 1, START + timedelta(days=1))
    assert news.day == 1 and news.players_scoring == 0
    assert news.top_player is None and news.leading_city is None
    text = wire_story(news)
    assert "No scoring players" in text and "No city qualified" in text
    assert "THE SNOWFALL WIRE" in text
    assert "individual-only" in text
    assert engine.latest_completed_day(KEY, START + timedelta(days=1)) == 1


def test_community_reports_are_isolated_across_seasons_and_databases(store, tmp_path):
    go_live(store)
    other = Store(tmp_path / "practice.sqlite3")
    other.initialize()
    other.ensure_season("practice", START)
    other.register("practice", 11, "TheDude", "Chicago", START - timedelta(days=1))
    other.transition("practice", 11, "start", START, "test")
    WorldEngine(other).tick("practice", START)
    assert CommunityEngine(other).headquarters("practice", 11, START).members == 1
    assert CommunityEngine(store).headquarters(KEY, 11, START).members == 2
    assert store.schema_version() >= 5


def test_paused_time_cannot_publish_a_future_wire(store):
    go_live(store)
    store.transition(KEY, 11, "pause", START + timedelta(hours=12), "freeze")
    engine = CommunityEngine(store)
    assert engine.latest_completed_day(KEY, START + timedelta(days=9)) == 0
    with pytest.raises(CommunityError, match="not complete"):
        engine.recap(KEY, 1, START + timedelta(days=9))


def test_rival_summary_has_only_five_other_cities(store):
    go_live(store)
    e = CommunityEngine(store)
    opponents = e.rivalry_summary(KEY, 11)
    assert len(opponents) == 5
    assert "Chicago" not in {r.opponent for r in opponents}
    assert all(r.hits == 0 and r.damage_received == 0 for r in opponents)
    with pytest.raises(CommunityError, match="Day"):
        e.rivalry_summary(KEY, 11, day=8)


def test_no_city_rewards_or_prize_changes(store):
    go_live(store)
    engine = CommunityEngine(store)
    for day in range(1, 8):
        now = START + timedelta(days=day)
        engine.recap(KEY, day, now)
    with store.connect() as con:
        assert not con.execute("SELECT 1 FROM prize_awards WHERE season_key=?", (KEY,)).fetchone()
        assert not con.execute("SELECT 1 FROM score_ledger WHERE season_key=?", (KEY,)).fetchone()
