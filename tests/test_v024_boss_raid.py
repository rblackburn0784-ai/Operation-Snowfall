"""v0.2.4 Snow Don phase evolution, cooperative raid and cinematic integrity."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine, PveResult
from snowfall.services.boss_raid import RaidEngine
from snowfall.services.boss_personality import (
    boss_banter, phase_story, phase_transitions, crossed_phases,
)
from snowfall.services.broadcast import boss_defeated_announcement
from snowfall.graphics.raid_cards import (
    raid_board_card, raid_leaders_card, phase_transition_animation,
    final_defeat_cinematic,
)

START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
KEY = "raid-v024"


class FixedRNG:
    def __init__(self, value=0.0):
        self.value = value

    def random(self):
        return self.value


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "snow-don-raid.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    for uid, city in [(1, "Chicago"), (2, "New York"), (3, "Detroit"),
                      (4, "Chicago"), (5, "Philadelphia"), (6, "Las Vegas")]:
        store.register(KEY, uid, f"Raider{uid}", city, START - timedelta(days=1))
    store.transition(KEY, 900, "start", START, "launch")
    WorldEngine(store).tick(KEY, START)
    return store


def attack(store, seq, uid, *, hit=True):
    return WorldEngine(store, FixedRNG(0 if hit else .99)).attack(
        KEY, uid, "boss", f"boss-{seq}",
        START + timedelta(seconds=31 * seq))


def win(game):
    last = None
    for i in range(14):
        last = attack(game, i, (i % 3) + 1)
    assert last and last.final_blow
    return last


def image(data):
    assert data and data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) < 2_000_000
    with Image.open(BytesIO(data)) as card:
        assert card.size == (960, 540)
        assert card.mode == "RGB"


def test_initial_raid_and_realtime_multi_city_team_progress(game):
    report = RaidEngine(game).report(KEY, 1)
    assert report.remaining_hp == report.max_hp == 168
    assert report.phase == "The Don Rules the Streets"
    assert report.shared_damage == 0 and report.contributors == 0
    assert report.milestones == () and report.next_milestone == 25
    attack(game, 0, 1)
    attack(game, 1, 2, hit=False)
    attack(game, 2, 3)
    report = RaidEngine(game).report(KEY, 1)
    assert report.shared_damage == 24
    assert report.hit_count == 2 and report.misses == 1
    assert report.contributors == 2
    assert {r.name for r in report.cities} == {"Chicago", "Detroit"}
    assert report.member(2).shared_damage == 0
    assert report.member(1).shared_hits == 1
    assert not report.defeated
    image(raid_board_card(report, viewer_id=1))
    image(raid_leaders_card(report))
    assert CombatEngine(game).ledger_total(KEY, 1) == 5
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0


def test_shared_defeat_once_raid_honours_echoes_and_restart(game):
    final = win(game)
    report = RaidEngine(game).report(KEY, 1)
    assert report.defeated
    assert report.shared_damage == 168 and report.remaining_hp == 0
    assert report.progress == 100 and report.milestones == (25, 50, 75, 100)
    assert report.next_milestone is None
    assert report.contributors == 3 and report.hit_count == 14
    assert report.final_hitter == "Raider2"
    assert report.member(1).shared_damage == 60
    assert report.member(2).shared_damage == 60
    assert report.member(3).shared_damage == 48
    assert report.member(2).final_blow
    assert RaidEngine(game).final_result(KEY, 1) == final
    assert "3 raiders" in boss_defeated_announcement(1, report)
    assert "training echoes" in boss_defeated_announcement(1, report)
    before = CombatEngine(game).ledger_total(KEY, 2)
    echo = attack(game, 50, 4)
    assert echo.echo and not echo.final_blow and echo.hp_after == 0
    after_echo = RaidEngine(game).report(KEY, 1)
    assert after_echo.echo_attacks == 1
    assert after_echo.contributors == 3 and after_echo.shared_damage == 168
    assert after_echo.member(4).shared_damage == 0
    assert CombatEngine(game).ledger_total(KEY, 2) == before
    assert RaidEngine(game).final_result(KEY, 1) == final
    repeated = WorldEngine(game).attack(KEY, 2, "boss", final.interaction_id,
                                        START + timedelta(hours=1))
    assert repeated.repeated and repeated.points == final.points
    assert RaidEngine(game).report(KEY, 1) == after_echo
    reopened = Store(game.path)
    reopened.initialize()
    assert reopened.schema_version() == 9
    assert RaidEngine(reopened).report(KEY, 1) == after_echo
    with reopened.connect() as con:
        for table in ("combat_events", "prize_awards"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM pve_events").fetchone()[0] == 15


def test_day_rollover_raid_scope_and_disabled_boss(tmp_path, game):
    attack(game, 0, 1)
    WorldEngine(game).tick(KEY, START + timedelta(days=1))
    report = RaidEngine(game).report(KEY, 2)
    assert report.shared_damage == 0 and report.contributors == 0
    assert report.remaining_hp == report.max_hp
    assert RaidEngine(game).final_result(KEY, 2) is None
    with pytest.raises(ValueError, match="1–7"):
        RaidEngine(game).report(KEY, 8)
    with pytest.raises(ValueError, match="not spawned"):
        RaidEngine(game).report(KEY, 7)
    disabled = Store(tmp_path / "disabled.sqlite3")
    disabled.initialize()
    disabled.ensure_season(KEY, START)
    WorldEngine(disabled).configure_boss(KEY, 900, False, None, "host disabled", START)
    disabled.register(KEY, 31, "Solo", "Chicago", START - timedelta(days=1))
    disabled.transition(KEY, 900, "start", START, "start")
    WorldEngine(disabled).tick(KEY, START)
    d = RaidEngine(disabled).report(KEY, 1)
    assert not d.enabled and not d.defeated
    assert RaidEngine(disabled).final_result(KEY, 1) is None
    image(raid_board_card(d, viewer_id=31))


def test_phase_crossings_story_and_stable_boss_taunts():
    phase = PveResult("phase-75", "boss", 1, "Chicago", True,
                      6, 5, 0, 149, 200, False, False)
    assert crossed_phases(155, 149, 200) == (75,)
    assert phase_transitions(phase) == (75,)
    assert "75%" in phase_story(phase)
    assert "hat" in phase_story(phase).lower()
    triple = replace(phase, damage=160, hp_after=40)
    assert phase_transitions(triple) == (75, 50, 25)
    assert all(f"{level}%" in phase_story(triple) for level in (75, 50, 25))
    assert boss_banter(phase) == boss_banter(phase)
    assert boss_banter(replace(phase, hit=False))
    assert any(term in boss_banter(replace(phase, echo=True)).lower()
               for term in ("training", "practise"))
    assert phase_transitions(replace(phase, repeated=True)) == ()
    assert phase_transitions(replace(phase, echo=True)) == ()
    assert phase_transitions(replace(phase, final_blow=True)) == ()
    assert phase_transitions(replace(phase, kind="siege")) == ()
    assert boss_banter(replace(phase, kind="siege")) is None


def test_phase_gif_and_cinematic_have_correct_size_frames_and_fallback():
    phase = PveResult("cross-75", "boss", 1, "Chicago", True,
                      12, 5, 0, 144, 200, False, False)
    effect = phase_transition_animation(phase)
    assert effect and effect.startswith(b"GIF89a") and len(effect) < 4_000_000
    with Image.open(BytesIO(effect)) as gif:
        assert gif.n_frames == 9 and gif.size == (480, 270)
    assert phase_transition_animation(replace(phase, echo=True)) is None
    assert phase_transition_animation(replace(phase, hit=False)) is None
    assert phase_transition_animation(replace(phase, repeated=True)) is None
    assert phase_transition_animation(replace(phase, final_blow=True)) is None
    assert phase_transition_animation(phase, maximum_bytes=10) is None
    final = replace(phase, interaction_id="real-final", hp_after=0,
                    damage=12, final_blow=True)
    cinematic = final_defeat_cinematic(final)
    assert cinematic and cinematic.startswith(b"GIF89a") and len(cinematic) < 4_000_000
    with Image.open(BytesIO(cinematic)) as gif:
        assert gif.n_frames == 16 and gif.size == (480, 270)
    assert final_defeat_cinematic(replace(final, repeated=True)) is None
    assert final_defeat_cinematic(replace(final, echo=True)) is None
    assert final_defeat_cinematic(replace(final, kind="siege")) is None
    assert final_defeat_cinematic(replace(final, final_blow=False)) is None
    assert final_defeat_cinematic(final, maximum_bytes=10) is None


def test_raid_reads_cannot_change_scores_or_award_victory_twice(game):
    result = win(game)
    with game.connect() as con:
        before = [con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("score_ledger", "pve_events", "prize_awards", "item_events")]
    for _ in range(3):
        report = RaidEngine(game).report(KEY, 1)
        image(raid_board_card(report, viewer_id=1))
        image(raid_leaders_card(report))
        final = RaidEngine(game).final_result(KEY, 1)
        assert final and final.interaction_id == result.interaction_id
        assert final_defeat_cinematic(final) is not None
    with game.connect() as con:
        after = [con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                 for table in ("score_ledger", "pve_events", "prize_awards", "item_events")]
    assert before == after


def test_discord_raid_navigation_and_safe_defeat_replay(game, monkeypatch):
    pytest.importorskip("discord")
    from snowfall.commands.winter_fun import SnowFunGroup
    from snowfall.ui.world import WorldView, WorldConfirm, result_text
    from snowfall.ui.raid import RaidView, raid_text, show_raid
    from snowfall.ui.navigation import GameMenu

    settings = SimpleNamespace(guild_id=12345, season_key=KEY,
                               mode="production", admin_user_ids=frozenset())
    monkeypatch.setattr("snowfall.ui.raid._now", lambda: START)
    command_names = {c.name for c in SnowFunGroup(settings, game).commands}
    assert "raid" in command_names
    assert "Snow Don Raid" in {getattr(b, "label", "") for b in GameMenu(settings, game, 1).children}
    assert "Raid Headquarters" in {getattr(b, "label", "") for b in WorldView(settings, game, 1).children}
    for view in (RaidView(settings, game, 1), WorldView(settings, game, 1),
                 WorldConfirm(settings, game, 1, "boss")):
        assert len(view.children) <= 25
        assert all(b.row is None or b.row <= 4 for b in view.children)
    assert "co-op progress" in raid_text(RaidEngine(game).report(KEY, 1), 1).lower()
    assert "Points: **+5**" in result_text(
        PveResult("hit", "boss", 1, "Chicago", True, 12, 5, 0, 150, 168, False, False))

    class Interaction:
        def __init__(self):
            self.user = SimpleNamespace(id=1)
            self.guild_id = 12345
            self.channel_id = 200
            self.client = SimpleNamespace(practice=None)
            self.response = SimpleNamespace(defer=self.defer)
            self.edits = []
        async def defer(self, **kw):
            pass
        async def edit_original_response(self, **kw):
            self.edits.append(kw)

    async def scenario():
        event = Interaction()
        await show_raid(event, settings, game, 1)
        assert len(event.edits) == 1
        assert event.edits[0]["view"].owner_id == 1
        assert event.edits[0]["attachments"]  # locally rendered PNG
        test = Interaction()
        replay_view = RaidView(settings, game, 1)
        replay_button = next(b for b in replay_view.children
                             if getattr(b, "label", None) == "Victory Replay")
        await replay_button.callback(test)
        assert test.edits and "unlocks after" in test.edits[0]["content"]

    asyncio.run(scenario())
