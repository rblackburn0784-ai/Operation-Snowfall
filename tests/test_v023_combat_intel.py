"""v0.2.3: read-only rivalry history, targeting, menus, flair and no-prize drills."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.services.combat import CombatEngine, CombatResult, TargetView
from snowfall.services.combat_flair import fight_beat
from snowfall.services.combat_intel import CombatIntelEngine, target_order
from snowfall.graphics import cards
from snowfall.graphics.combat_cards import rivalry_card

NOW = datetime(2026, 12, 21, 20, tzinfo=timezone.utc)
KEY = "combat-v023"


@pytest.fixture
def game(tmp_path):
    db = Store(tmp_path / "intel.sqlite3")
    db.initialize()
    db.ensure_season(KEY, NOW)
    for user, name, city in [(101, "TheDude", "Chicago"), (202, "Aizen", "New York"),
                             (303, "Nevaa", "Detroit"), (404, "Jago", "Las Vegas")]:
        db.register(KEY, user, name, city, NOW - timedelta(days=1))
    db.transition(KEY, 900, "start", NOW, "Launch")
    return db


def append(db, seq: int, attacker: int, target: int, *, hit=True, points=8, knocked_out=False):
    cities = {101: "Chicago", 202: "New York", 303: "Detroit", 404: "Las Vegas"}
    columns = ("interaction_id season_key day attacker_id target_id target_city style "
               "happened_at_utc effective_at_utc hit critical hit_roll crit_roll "
               "armour_damage warmth_damage knocked_out points_awarded bonus_city "
               "bonus_ko defense_points").split()
    args = (f"b{seq}", KEY, 1, attacker, target, cities[target], "quick",
            (NOW + timedelta(seconds=40 * seq)).isoformat(),
            (NOW + timedelta(seconds=40 * seq)).isoformat(),
            int(hit), 0, 0.1 if hit else 0.95, 0.7 if hit else None,
            0, 8 if hit else 0, int(knocked_out), points if hit else 0, 0, 0, 0)
    with db.connect() as con:
        con.execute(f"INSERT INTO combat_events ({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})", args)


def test_retaliation_alerts_and_scorer_streaks_are_derived_from_history(game):
    append(game, 1, 101, 202)
    append(game, 2, 202, 101)
    append(game, 3, 101, 202, hit=False)
    append(game, 4, 202, 101)
    state = CombatIntelEngine(game).snapshot(KEY, 101)
    assert state.current_streak == 0 and state.best_streak == 1
    assert [r.user_id for r in state.revenge_alerts] == [202]
    assert state.rival(202).received_hits == 2
    assert state.rival(202).accuracy == 50
    append(game, 5, 101, 202)
    state = CombatIntelEngine(game).snapshot(KEY, 101)
    assert state.current_streak == 1
    assert not state.revenge_alerts
    assert state.rival(202).revenges == 1
    assert state.rival(202).last_revenge_interaction == "b5"
    append(game, 6, 101, 303, hit=False)
    append(game, 7, 303, 101)
    assert [r.user_id for r in CombatIntelEngine(game).snapshot(KEY, 101).revenge_alerts] == [303]
    append(game, 8, 101, 303)
    append(game, 9, 101, 303)
    final = CombatIntelEngine(game).snapshot(KEY, 101)
    assert final.current_streak == 2 and final.best_streak == 2
    assert final.revenge_count == 2
    assert final.rival(303).last_revenge_interaction == "b8"
    assert not final.revenge_alerts


def test_no_revenge_or_streak_for_unscored_hit(game):
    append(game, 1, 202, 101, hit=True, points=0)
    state = CombatIntelEngine(game).snapshot(KEY, 101)
    assert state.revenge_alerts == ()
    append(game, 2, 101, 202, hit=True, points=0)
    state = CombatIntelEngine(game).snapshot(KEY, 101)
    assert state.current_streak == 0
    assert state.rival(202).hits == 0
    assert state.rival(202).attacks == 1


def test_revenge_smart_fresh_and_vulnerable_sort_only_known_eligible_targets(game):
    append(game, 1, 303, 101)
    intel = CombatIntelEngine(game).snapshot(KEY, 101)
    pool = [
        TargetView(202, "Aizen", "New York", 50, 2),
        TargetView(303, "Nevaa", "Detroit", 90, 1),
        TargetView(404, "Jago", "Las Vegas", 10, 2),
    ]
    assert target_order(pool, intel, "revenge")[0].discord_user_id == 303
    assert target_order(pool, intel, "smart")[0].discord_user_id == 303
    assert target_order(pool, intel, "vulnerable")[0].discord_user_id == 404
    assert target_order(pool, intel, "fresh")[0].discord_user_id == 202
    assert target_order(pool[:1], intel, "revenge") == []
    with pytest.raises(ValueError, match="Unknown"):
        target_order(pool, intel, "admin_override")


def test_revenge_reaction_is_stable_not_random_and_never_rewards_twice(game):
    append(game, 1, 202, 101)
    append(game, 2, 101, 202)
    intel = CombatIntelEngine(game).snapshot(KEY, 101)
    result = CombatResult("b2", 1, 101, 202, "New York", "quick", True,
                          False, 0, 8, False, 8, 0, 0, 0, .1, .8)
    beat = fight_beat(result, intel)
    assert beat.revenge
    assert beat.streak == 1
    assert beat.pair_hits == 1 and beat.pair_received == 1
    assert fight_beat(result, intel) == beat
    duplicate = fight_beat(replace(result, repeated=True), intel)
    assert duplicate.repeat and not duplicate.revenge
    assert duplicate.headline == "PREVIOUSLY RECORDED"


def test_image_cards_include_rivalry_overlays_and_png_limits(game):
    append(game, 1, 303, 101)
    append(game, 2, 101, 303)
    intel = CombatIntelEngine(game).snapshot(KEY, 101)
    result = CombatResult("b2", 1, 101, 303, "Detroit", "quick", True,
                          True, 0, 12, False, 11, 0, 0, 0, .1, .02)
    beat = fight_beat(result, intel)
    base = cards.battle_card(result, "Nevaa")
    fancy = cards.battle_card(result, "Nevaa", beat=beat)
    assert base != fancy
    for blob in (fancy, rivalry_card(intel, "Chicago")):
        assert blob.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(blob) < 2_000_000
        with Image.open(BytesIO(blob)) as im:
            assert im.size == (960, 540)
            assert im.mode == "RGB"
    animation = cards.hit_animation(result, "Nevaa", beat=beat)
    assert animation and animation.startswith(b"GIF89a") and len(animation) < 4_000_000


def test_history_is_season_scoped_and_read_only(game):
    append(game, 1, 202, 101)
    game.ensure_season("next", NOW)
    game.register("next", 101, "NewDude", "Chicago", NOW)
    assert CombatIntelEngine(game).snapshot("next", 101).rivalries == ()
    with pytest.raises(ValueError, match="Register"):
        CombatIntelEngine(game).snapshot(KEY, 9999)
    with game.connect() as con:
        before = [con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("combat_events", "score_ledger", "prize_awards")]
    for _ in range(3):
        CombatIntelEngine(game).snapshot(KEY, 101)
        target_order([], CombatIntelEngine(game).snapshot(KEY, 101))
    with game.connect() as con:
        after = [con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                 for table in ("combat_events", "score_ledger", "prize_awards")]
    assert before == after == [1, 0, 0]


def test_discord_menus_and_sandbox_tactics_are_private_and_score_neutral(game):
    pytest.importorskip("discord")
    from snowfall.commands.public import SnowGroup
    from snowfall.commands.winter_fun import SnowFunGroup
    from snowfall.ui.combat import ThrowMenu, TargetPicker, RetryView
    from snowfall.ui.combat_lab import CombatLab
    from snowfall.ui.rivalries import RivalryView, rivalry_text
    from snowfall.ui.navigation import GameMenu

    config = SimpleNamespace(guild_id=121, season_key=KEY, mode="production",
                             admin_user_ids=frozenset())
    practice = SimpleNamespace(guild_id=121, season_key=KEY, mode="practice",
                               admin_user_ids=frozenset())
    commands = {c.name for c in SnowGroup(config, game).commands}
    assert len(commands) <= 25 and "targets" in commands
    fun = {c.name for c in SnowFunGroup(config, game).commands}
    assert "rivalries" in fun and "showcase" in fun
    assert "Rivalry Dossier" in {b.label for b in GameMenu(config, game, 101).children}
    assert "Tactics Lab" not in {b.label for b in ThrowMenu(config, game, 101, 202, "Aizen").children}
    assert "Tactics Lab" in {b.label for b in ThrowMenu(practice, game, 101, 202, "Aizen").children}
    with pytest.raises(ValueError, match="practice"):
        CombatLab(config, game, 101, 202, "Aizen")
    choices = [TargetView(202, "Aizen", "New York", 100, 2)]
    menus = (TargetPicker(config, game, 101, choices), RetryView(config, game, 101),
             RivalryView(config, game, 101), CombatLab(practice, game, 101, 202, "Aizen"))
    for view in menus:
        assert len(view.children) <= 25
        assert all(b.row is None or b.row <= 4 for b in view.children)
    assert "Revenge Rival" in {b.label for b in menus[0].children}
    assert "Rivalry Dossier" in {b.label for b in menus[1].children}
    alert = rivalry_text(CombatIntelEngine(game).snapshot(KEY, 101))
    assert "No outstanding" in alert

    class FakeResponse:
        def __init__(self):
            self.edits = []
        async def edit_message(self, **kwargs):
            self.edits.append(kwargs)

    class FakeInteraction:
        response = FakeResponse()

    async def drills():
        lab = menus[-1]
        await lab._run(FakeInteraction(), "feint")
        await lab._run(FakeInteraction(), "stance")
        assert len(FakeInteraction.response.edits) == 2
        assert "No snowballs" in FakeInteraction.response.edits[1]["content"]

    asyncio.run(drills())
    assert CombatEngine(game).ledger_total(KEY, 101) == 0
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM combat_events").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
