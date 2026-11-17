"""v0.2.0a cross-system regression checks for auditing and fair play."""
from datetime import datetime, timedelta, timezone

import pytest

from snowfall.db.store import Store
from snowfall.ops import award_csv, reconcile, safe_csv_cell
from snowfall.services.community import CommunityEngine
from snowfall.services.world import WorldEngine

START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
KEY = "security-audit-2026"


class CertainHit:
    def random(self):
        return 0.01


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "security.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    store.register(KEY, 101, "ChicagoOne", "Chicago", START - timedelta(days=1))
    store.register(KEY, 102, "ChicagoTwo", "Chicago", START - timedelta(days=1))
    store.register(KEY, 201, "NewYorkOne", "New York", START - timedelta(days=1))
    store.transition(KEY, 999, "start", START, "Audit test start")
    WorldEngine(store).tick(KEY, START)
    return store


def _quest_credit(con, user, day, key, source, points=20):
    con.execute("""INSERT INTO score_ledger
        (season_key,day,player_id,city,category,points,source_key,created_at_utc)
        VALUES (?, ?, ?, 'Chicago', 'quest', ?, ?, ?)""",
        (KEY, day, user, points, source, START.isoformat()))


def test_reconcile_detects_real_singular_quest_category_over_cap(game):
    with game.connect() as con:
        for index in range(4):
            _quest_credit(con, 101, 1, "throws", f"fake-quest-{index}")
    audit = reconcile(game, KEY)
    assert not audit["ok"]
    assert audit["quest_over_cap_count"] == 1
    assert audit["quest_unbacked_count"] == 4


def test_reconcile_matches_quest_claims_to_ledger_both_directions(game):
    with game.connect() as con:
        con.execute("""INSERT INTO quest_claims
            (season_key,discord_user_id,day,quest_key,points,claimed_at_utc)
            VALUES (?,?,1,'throws',20,?)""", (KEY, 101, START.isoformat()))
        _quest_credit(con, 101, 1, "throws", "quest:1:throws")
    assert reconcile(game, KEY)["ok"]
    with game.connect() as con:
        con.execute("""INSERT INTO quest_claims
            (season_key,discord_user_id,day,quest_key,points,claimed_at_utc)
            VALUES (?,?,1,'rivals',20,?)""", (KEY, 101, START.isoformat()))
    audit = reconcile(game, KEY)
    assert not audit["ok"]
    assert audit["quest_missing_count"] == 1


def test_reconcile_detects_unpaid_defense_points(game):
    with game.connect() as con:
        con.execute("""INSERT INTO combat_events
           (interaction_id,season_key,day,attacker_id,target_id,target_city,style,
            happened_at_utc,effective_at_utc,hit,critical,hit_roll,armour_damage,
            warmth_damage,knocked_out,points_awarded,bonus_city,bonus_ko,defense_points)
           VALUES(?,?,1,201,101,'Chicago','quick',?,?,1,0,0.1,5,0,0,0,0,0,2)""",
           ("defense-mismatch", KEY, START.isoformat(), START.isoformat()))
    audit = reconcile(game, KEY)
    assert not audit["ok"] and audit["defense_mismatch_count"] == 1
    assert audit["mismatched_combat_ids"] == []


def test_flagged_player_pve_cannot_complete_city_objectives(game):
    when = START + timedelta(days=1, minutes=1)
    WorldEngine(game, CertainHit()).attack(KEY, 101, "siege", "day2-siege-hit", when)
    before = CommunityEngine(game).headquarters(KEY, 102, when).objective
    assert before.day == 2 and before.progress == 14
    game.review(KEY, 999, 101, "flagged", "Identity dispute under review", when)
    after = CommunityEngine(game).headquarters(KEY, 102, when).objective
    assert after.progress == 0 and not after.completed


@pytest.mark.parametrize("value", [
    "=2+2", "+SUM(1,2)", "-1+2", "@SUM(1)", "   =HYPERLINK(1)", "\t=1",
])
def test_staff_csv_neutralizes_formula_cells(value):
    assert safe_csv_cell(value).startswith("'")
    exported = award_csv([{
        "place": 1, "discord_user_id": 101, "mr_username": value,
        "city": "Chicago", "points": 42, "reward": "=HYPERLINK(1)",
        "status": "pending",
    }]).decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in exported
    assert "'" + value in exported


def test_csv_keeps_normal_text_unchanged():
    assert safe_csv_cell("TheDude") == "TheDude"
    assert safe_csv_cell("Ordinary reward") == "Ordinary reward"
