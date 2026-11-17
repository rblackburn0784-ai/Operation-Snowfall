"""v0.2.5: six-city district control is read-only and honourary."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store, CITIES
from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine
from snowfall.services.territory import (
    TerritoryEngine, TerritoryError, CITY_STYLE, FRONTIERS, schedule_for_day,
    _winner,
)
from snowfall.graphics.territory_cards import (
    territory_map_card, city_banners_card, city_territory_card,
)

START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
KEY = "territory-v025"


class HitRNG:
    def random(self):
        return 0.0


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "wars.sqlite3")
    db.initialize()
    db.ensure_season(KEY, START)
    people = [(101, "TheDude", "Chicago"), (102, "Jago", "Chicago"),
              (201, "WestSide", "Los Angeles"), (202, "CoastFox", "Los Angeles"),
              (301, "Empire", "New York"), (401, "Slots", "Las Vegas"),
              (501, "Motor", "Detroit"), (601, "Liberty", "Philadelphia")]
    for uid, name, city in people:
        db.register(KEY, uid, name, city, START - timedelta(days=1))
    return db


def launch(db):
    db.transition(KEY, 900, "start", START, "Kickoff")
    WorldEngine(db).tick(KEY, START)


def four_real_hits(db):
    e = CombatEngine(db, HitRNG())
    e.ready(KEY, 201, START)
    e.ready(KEY, 202, START)
    hits = []
    for uid, target, seconds, index in (
        (101, 201, 31, 1),
        (102, 202, 34, 2),
        (101, 201, 70, 3),
        (102, 202, 73, 4),
    ):
        hits.append(e.throw(KEY, uid, target, "quick", f"territory-hit-{index}",
                            START + timedelta(seconds=seconds)))
    assert all(h.hit and h.points_awarded > 0 for h in hits)
    return hits


def state_counts(db):
    with db.connect() as con:
        return tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("combat_events", "score_ledger", "pve_events",
                                   "item_events", "prize_awards", "mystery_gifts"))


def check_png(contents):
    assert contents and contents[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(contents) < 2_000_000
    with Image.open(BytesIO(contents)) as img:
        assert img.size == (960, 540)
        assert img.mode == "RGB"


def test_schedule_is_six_cities_three_opponents_every_day_and_complete_round_robin():
    pairings = set()
    for day in range(1, 8):
        matches = schedule_for_day(day)
        assert len(matches) == 3
        assert set(city for m in matches for city in m) == set(CITIES)
        assert all(a != b for a, b in matches)
        if day <= 5:
            pairings.update(tuple(sorted(m)) for m in matches)
    assert len(pairings) == 15
    assert len(CITY_STYLE) == 6 and len(FRONTIERS) == 3
    assert schedule_for_day(6) == schedule_for_day(1)
    assert schedule_for_day(7) == schedule_for_day(2)
    for bad in (0, -1, 8):
        with pytest.raises(TerritoryError):
            schedule_for_day(bad)
    assert _winner(0, 0, "Chicago", "Detroit") is None
    assert _winner(3, 3, "Chicago", "Detroit") is None


def test_prelaunch_map_is_private_and_all_strongholds_neutral(store):
    board = TerritoryEngine(store).board(KEY, 101, START - timedelta(hours=1))
    assert board.viewer_city == "Chicago"
    assert board.day is None and board.current_day is None
    assert len(board.banners) == len(board.districts) == 6
    assert board.matches == () and board.missions == ()
    assert all(d.owner is None for d in board.districts)
    assert board.banner("Chicago").registered == 2
    check_png(territory_map_card(board))
    check_png(city_banners_card(board))
    check_png(city_territory_card(board, "Chicago"))
    with pytest.raises(TerritoryError, match="not available"):
        TerritoryEngine(store).board(KEY, 101, START, day=1)
    with pytest.raises(TerritoryError, match="Register"):
        TerritoryEngine(store).board(KEY, 98765, START)


def test_six_city_day_one_map_neutral_when_all_teams_tied(store):
    launch(store)
    board = TerritoryEngine(store).board(KEY, 101, START)
    assert board.day == board.current_day == 1
    assert len(board.matches) == 3
    assert len(board.districts) == 12
    assert len(board.contested) == 6
    assert not any(d.owner for d in board.districts)
    assert board.match("Chicago").opponent("Chicago") == "Los Angeles"
    assert board.match("Chicago").rally_a == board.match("Chicago").rally_b == 0
    assert [m.name for m in board.missions] == [
        "Rally the Crew", "Rival City Ambush", "Local City Mission"]
    assert board.missions[0].target == 2
    assert board.missions[1].target == 2
    assert board.banner("Chicago").mission_target == 4
    assert board.banner("Chicago").stronghold_quorum == 2
    assert not board.banner("Chicago").mission_complete
    check_png(territory_map_card(board))
    check_png(territory_map_card(board, highlighted_city="Los Angeles"))
    check_png(city_banners_card(board))
    check_png(city_territory_card(board, "Detroit"))


def test_real_city_cooperation_claims_home_and_two_frontiers_without_extra_points(store):
    launch(store)
    old = TerritoryEngine(store).board(KEY, 101, START)
    four = four_real_hits(store)
    before = state_counts(store)
    war = TerritoryEngine(store).board(KEY, 101, START + timedelta(minutes=5))
    assert war.banner("Chicago").mission_complete
    assert war.banner("Chicago").mission_progress == 4
    assert war.banner("Chicago").active == 2
    assert war.banner("Chicago").rally_marks >= 8
    assert war.banner("Los Angeles").rally_marks == 0
    duel = war.match("Chicago")
    assert duel and duel.hits_a == 4 and duel.hits_b == 0
    assert duel.rally_owner == duel.duel_owner == "Chicago"
    assert len(war.held("Chicago")) == 3
    assert {d.kind for d in war.held("Chicago")} == {"home", "rally", "duel"}
    assert all(goal.complete for goal in war.missions)
    assert not any(d.owner == "Los Angeles" for d in war.districts)
    assert old.matches != war.matches
    assert CombatEngine(store).ledger_total(KEY, 101) == (
        four[0].points_awarded + four[2].points_awarded)
    for _ in range(4):
        board = TerritoryEngine(store).board(KEY, 101, START + timedelta(minutes=5))
        assert len(board.held("Chicago")) == 3
        assert TerritoryEngine(store).rivalries(KEY, 101, "Los Angeles")
        check_png(territory_map_card(board))
        check_png(city_banners_card(board))
        check_png(city_territory_card(board, "Chicago"))
    assert state_counts(store) == before


def test_duplicate_combat_replay_and_antifraud_review_change_honours_only(store):
    launch(store)
    four = four_real_hits(store)
    original = state_counts(store)
    repeated = CombatEngine(store, HitRNG()).throw(
        KEY, 101, 201, "quick", four[0].interaction_id,
        START + timedelta(minutes=8))
    assert repeated.repeated and state_counts(store) == original
    before = TerritoryEngine(store).board(KEY, 101, START + timedelta(minutes=7))
    assert len(before.held("Chicago")) == 3
    store.review(KEY, 900, 102, "flagged", "duplicate registration review",
                 START + timedelta(minutes=10))
    revised = TerritoryEngine(store).board(KEY, 101, START + timedelta(minutes=10))
    assert revised.banner("Chicago").active == 1
    assert revised.banner("Chicago").mission_progress == 2
    # Existing city mission rescales after review; home territory still
    # requires the original eligible-activity quorum fixed at day kickoff.
    assert revised.banner("Chicago").mission_complete
    assert revised.banner("Chicago").stronghold_quorum == 2
    assert revised.banner("Chicago").active == 1
    assert revised.match("Chicago").hits_a == 2
    assert revised.match("Chicago").rally_owner == "Chicago"
    assert len(revised.held("Chicago")) == 2
    assert state_counts(store) == original
    with pytest.raises(TerritoryError, match="Unknown"):
        TerritoryEngine(store).rivalries(KEY, 101, "Atlantis")
    with pytest.raises(TerritoryError, match="Register"):
        TerritoryEngine(store).rivalries(KEY, 98765, "Chicago")


def test_day_scoping_frozen_paused_and_future_days_never_open_early(store):
    launch(store)
    four_real_hits(store)
    day1 = TerritoryEngine(store).board(KEY, 101, START + timedelta(minutes=5))
    assert len(day1.held("Chicago")) == 3
    with pytest.raises(TerritoryError, match="not available"):
        TerritoryEngine(store).board(KEY, 101, START, day=2)
    store.transition(KEY, 900, "pause", START + timedelta(hours=12), "pause")
    paused = TerritoryEngine(store).board(KEY, 101, START + timedelta(days=3))
    assert paused.phase == "paused"
    assert paused.day == paused.current_day == 1
    assert len(paused.held("Chicago")) == 3
    store.transition(KEY, 900, "resume", START + timedelta(days=3), "resume")
    day2_at = START + timedelta(days=4, minutes=1)
    WorldEngine(store).tick(KEY, day2_at)
    day2 = TerritoryEngine(store).board(KEY, 101, day2_at)
    assert day2.day == day2.current_day == 2
    assert not day2.held("Chicago")
    assert TerritoryEngine(store).board(KEY, 101, day2_at, day=1).day == 1
    with pytest.raises(TerritoryError, match="not available"):
        TerritoryEngine(store).board(KEY, 101, day2_at, day=3)


def test_board_is_season_scoped_and_no_purchases_or_prizes(store):
    launch(store)
    four_real_hits(store)
    other = "other"
    store.ensure_season(other, START)
    store.register(other, 101, "AltDude", "Chicago", START - timedelta(days=1))
    store.transition(other, 900, "start", START, "another season")
    other_board = TerritoryEngine(store).board(other, 101, START)
    assert other_board.day == 1
    assert not other_board.held("Chicago")
    assert all(m.hits_a == 0 and m.hits_b == 0 for m in other_board.matches)
    assert state_counts(store)[-1] == 0
    assert store.schema_version() == 9


def test_player_city_scores_and_rivalry_stats_are_real_city_pvp_records(store):
    launch(store)
    four_real_hits(store)
    summary = TerritoryEngine(store).rivalries(KEY, 101, "Chicago")
    assert len(summary) == 5
    los_angeles = next(s for s in summary if s.opponent == "Los Angeles")
    assert los_angeles.throws == 4 and los_angeles.hits == 4
    assert los_angeles.damage_dealt > 0
    la = TerritoryEngine(store).rivalries(KEY, 101, "Los Angeles")
    chicago = next(s for s in la if s.opponent == "Chicago")
    assert chicago.hits_received == 4 and chicago.damage_received > 0


def test_discord_selectors_and_navigation_are_one_message_read_only(store, monkeypatch):
    discord = pytest.importorskip("discord")
    from snowfall.ui.territory import TerritoryView, show_territory, territory_text
    from snowfall.ui.community import CityHubView
    from snowfall.ui.navigation import GameMenu
    from snowfall.commands.winter_fun import SnowFunGroup

    launch(store)
    settings = SimpleNamespace(guild_id=42, season_key=KEY,
                               mode="production", admin_user_ids=frozenset())
    monkeypatch.setattr("snowfall.ui.territory._now",
                        lambda: START + timedelta(minutes=5))
    board = TerritoryEngine(store).board(KEY, 101, START)
    view = TerritoryView(settings, store, 101, board)
    assert view.owner_id == 101
    assert sum(isinstance(child, discord.ui.Select)
               for child in view.children) == 2
    assert len(view.children) == 12
    assert all(child.row is None or 0 <= child.row <= 4 for child in view.children)
    assert "City Wars Map" in {getattr(c, "label", "") for c in GameMenu(settings, store, 101).children}
    assert "Territory Map" in {getattr(c, "label", "") for c in CityHubView(settings, store, 101).children}
    assert "territory" in {c.name for c in SnowFunGroup(settings, store).commands}
    assert "honorary" in territory_text(board).lower()
    assert "Neutral" in territory_text(board, page="matchups")
    assert "collaborative" in territory_text(board, page="missions").lower()
    assert "Season-to-Date" in territory_text(
        board, page="rivals",
        rivalries=TerritoryEngine(store).rivalries(KEY, 101, "Chicago"))
    assert "Banners" in territory_text(board, page="banners")

    class Event:
        def __init__(self):
            self.user = SimpleNamespace(id=101)
            self.guild_id = 42
            self.client = SimpleNamespace(practice=None)
            self.channel_id = 99
            self.response = SimpleNamespace(defer=self.defer)
            self.edits = []
        async def defer(self, **kw):
            pass
        async def edit_original_response(self, **kw):
            self.edits.append(kw)

    async def run():
        event = Event()
        await show_territory(event, settings, store, 101)
        assert len(event.edits) == 1
        assert event.edits[0]["view"].owner_id == 101
        assert event.edits[0]["attachments"]
        old = state_counts(store)
        event2 = Event()
        await show_territory(event2, settings, store, 101, page="banners", day=1)
        assert len(event2.edits) == 1
        assert state_counts(store) == old
    asyncio.run(run())
