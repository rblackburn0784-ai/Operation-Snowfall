"""v0.1.2 transactional PvP regression tests; no Discord gateway required."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from snowfall.db.store import Store
from snowfall.services.combat import CombatEngine, CombatError

START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
KEY = "christmas-2026"


class FixedRng:
    def __init__(self, *values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "snowfall.sqlite3")
    s.initialize()
    s.ensure_season(KEY, START)
    s.transition(KEY, 999, "start", START, "Launch")
    return s


def join(s, uid, city="New York"):
    s.register(KEY, uid, f"Player_{uid}", city, START)


def enter(s, uid, at=START):
    CombatEngine(s).ready(KEY, uid, at)


def prepare(s):
    join(s, 1, "Chicago")
    join(s, 2)
    enter(s, 1)
    enter(s, 2)


def test_migration_and_immutable_history(store):
    assert store.schema_version() == 6
    prepare(store)
    result = CombatEngine(store, FixedRng(.1, .9)).throw(KEY, 1, 2, "quick", "evt1", START)
    assert result.points_awarded == 13
    with store.connect() as con:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("UPDATE score_ledger SET points=999 WHERE player_id=1")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("DELETE FROM combat_events WHERE interaction_id='evt1'")
    assert CombatEngine(store).ledger_total(KEY, 1) == 13


def test_ready_is_required_and_no_unearned_points(store):
    join(store, 1, "Chicago")
    join(store, 2, "New York")
    engine = CombatEngine(store)
    assert engine.targets(KEY, 1, START) == []
    with pytest.raises(CombatError, match="inactive"):
        engine.throw(KEY, 1, 2, "quick", "01", START)
    assert engine.ledger_total(KEY, 2) == 0
    engine.ready(KEY, 2, START)
    assert [r.discord_user_id for r in engine.targets(KEY, 1, START)] == [2]
    assert engine.ledger_total(KEY, 2) == 0
    with pytest.raises(CombatError, match="LIVE"):
        engine.ready(KEY, 1, START - timedelta(seconds=1))


def test_duplicate_request_does_not_spend_twice(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng(.1, .9))
    hit = engine.throw(KEY, 1, 2, "standard", "same-id", START)
    assert hit.hit and not hit.critical and hit.points_awarded == 17
    before = engine.snapshot(KEY, 1, START)
    replay = engine.throw(KEY, 1, 2, "standard", "same-id", START + timedelta(days=2))
    assert replay.repeated and replay.points_awarded == 17
    after = engine.snapshot(KEY, 1, START)
    assert (before.snowballs, before.today_pvp) == (after.snowballs, after.today_pvp)
    with pytest.raises(CombatError, match="different attack"):
        engine.throw(KEY, 1, 2, "power", "same-id", START)
    assert engine.ledger_total(KEY, 1) == 17


def test_miss_cooldown_and_regeneration_no_bank_at_cap(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng(.99, .99))
    miss = engine.throw(KEY, 1, 2, "quick", "m1", START)
    assert not miss.hit and miss.points_awarded == 0
    assert engine.snapshot(KEY, 1, START).snowballs == 7
    with pytest.raises(CombatError, match="cooldown"):
        engine.throw(KEY, 1, 2, "quick", "m2", START + timedelta(seconds=29))
    assert engine.snapshot(KEY, 1, START + timedelta(minutes=20)).snowballs == 8
    assert engine.snapshot(KEY, 1, START + timedelta(hours=8)).snowballs == 12
    # Spending while full begins a fresh 20-minute timer, not a banked burst.
    engine.throw(KEY, 1, 2, "quick", "m2", START + timedelta(hours=8))
    assert engine.snapshot(KEY, 1, START + timedelta(hours=8, minutes=1)).snowballs == 11
    assert engine.snapshot(KEY, 1, START + timedelta(hours=8, minutes=20)).snowballs == 12
    assert engine.ledger_total(KEY, 1) == 0


def test_first_city_bonus_critical_and_pair_hit_limit(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng(.1, .05, .1, .9))
    one = engine.throw(KEY, 1, 2, "power", "p1", START)
    assert one.critical and one.points_awarded == 26
    assert one.warmth_damage == 26
    two = engine.throw(KEY, 1, 2, "quick", "p2", START + timedelta(seconds=31))
    assert two.points_awarded == 8 and not two.critical
    with pytest.raises(CombatError, match="Two scoring hits"):
        engine.throw(KEY, 1, 2, "quick", "p3", START + timedelta(seconds=62))
    assert engine.snapshot(KEY, 1, START + timedelta(seconds=62)).snowballs == 6
    assert engine.ledger_total(KEY, 1) == 34


def test_three_incoming_hits_grant_15minute_shield(store):
    join(store, 2)
    enter(store, 2)
    for uid in (1, 3, 4):
        join(store, uid, "Chicago")
        enter(store, uid)
    engine = CombatEngine(store, FixedRng(.1, .9, .1, .9, .1, .9))
    for i, uid in enumerate((1, 3, 4)):
        engine.throw(KEY, uid, 2, "quick", f"hit-{i}", START + timedelta(seconds=40*i))
    with pytest.raises(CombatError, match="shield"):
        engine.throw(KEY, 1, 2, "quick", "blocked", START + timedelta(minutes=3))
    assert 2 not in {t.discord_user_id for t in engine.targets(KEY, 1, START + timedelta(minutes=3))}
    assert 2 in {t.discord_user_id for t in engine.targets(KEY, 1, START + timedelta(minutes=18))}


def test_ko_30minute_recovery_and_warmth_regen(store):
    prepare(store)
    with store.connect() as con:
        con.execute("UPDATE player_resources SET warmth=7 WHERE discord_user_id=2")
    engine = CombatEngine(store, FixedRng(.1, .9))
    result = engine.throw(KEY, 1, 2, "quick", "ko", START)
    assert result.knocked_out and result.warmth_damage == 8
    assert result.bonus_ko == 10
    assert engine.snapshot(KEY, 2, START + timedelta(minutes=29)).warmth == 0
    with pytest.raises(CombatError, match="knocked out"):
        engine.throw(KEY, 1, 2, "quick", "ko2", START + timedelta(minutes=1))
    assert engine.snapshot(KEY, 2, START + timedelta(minutes=30)).warmth == 50
    assert engine.snapshot(KEY, 2, START + timedelta(minutes=50)).warmth == 55
    assert engine.snapshot(KEY, 2, START + timedelta(minutes=50)).knockout_until is None


def test_fort_absorption_credits_defense_points(store):
    prepare(store)
    with store.connect() as con:
        con.execute("UPDATE player_resources SET armour_hp=18 WHERE discord_user_id=2")
    engine = CombatEngine(store, FixedRng(.01, .9))
    result = engine.throw(KEY, 1, 2, "standard", "fort", START)
    assert result.warmth_damage == 0 and result.armour_damage == 14
    assert result.defense_points == 2
    assert engine.ledger_total(KEY, 2) == 2
    assert engine.snapshot(KEY, 2, START).armour_hp == 4


def test_inactive_account_is_not_targetable(store):
    prepare(store)
    engine = CombatEngine(store)
    later = START + timedelta(hours=36, seconds=1)
    assert engine.targets(KEY, 1, later) == []
    with pytest.raises(CombatError, match="inactive"):
        engine.throw(KEY, 1, 2, "quick", "too-late", later)
    engine.ready(KEY, 2, later)
    assert engine.targets(KEY, 1, later)[0].discord_user_id == 2


def test_score_cap_next_day_reset_and_snowflakes(store):
    join(store, 1, "Chicago")
    enter(store, 1)
    engine = CombatEngine(store, FixedRng(*([.01, .9] * 200)))
    score = 0
    for i in range(42):
        target = 100 + i
        join(store, target)
        enter(store, target)
        at = START + timedelta(minutes=20*i)
        if score >= 300:
            with pytest.raises(CombatError, match="cap reached"):
                engine.throw(KEY, 1, target, "quick", f"cap-{i}", at)
            break
        result = engine.throw(KEY, 1, target, "quick", f"cap-{i}", at)
        score += result.points_awarded
    assert score == 300
    assert engine.snapshot(KEY, 1, START + timedelta(hours=14)).today_pvp == 300
    assert engine.ledger_total(KEY, 1, 1) == 300
    assert engine.snapshot(KEY, 1, START + timedelta(hours=14)).snowflakes <= 100
    fresh = START + timedelta(days=1, minutes=1)
    engine.ready(KEY, 2 if store.get_player(KEY, 2) else 100, fresh)
    assert engine.throw(KEY, 1, 100, "quick", "day-2", fresh).day == 2
    assert engine.ledger_total(KEY, 1, 2) == 8 + 5


def test_pause_freezes_regen_cooldown_and_days(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng(.99, .99))
    at = START + timedelta(hours=5)
    engine.throw(KEY, 1, 2, "quick", "miss", at)
    store.transition(KEY, 999, "pause", at + timedelta(seconds=5), "Pause")
    assert engine.snapshot(KEY, 1, at + timedelta(days=2)).snowballs == 11
    with pytest.raises(CombatError, match="LIVE"):
        engine.throw(KEY, 1, 2, "quick", "paused", at + timedelta(hours=1))
    store.transition(KEY, 999, "resume", at + timedelta(days=2), "Resume")
    with pytest.raises(CombatError, match="cooldown"):
        engine.throw(KEY, 1, 2, "quick", "still-cool", at + timedelta(days=2, seconds=10))
    engine.throw(KEY, 1, 2, "quick", "after-cool", at + timedelta(days=2, seconds=25))
    assert engine.snapshot(KEY, 1, at + timedelta(days=2, seconds=25)).day == 1


def test_concurrent_last_snowball_only_spent_once(store):
    prepare(store)
    with store.connect() as con:
        con.execute("UPDATE player_resources SET snowballs=1 WHERE discord_user_id=1")
    when = START + timedelta(seconds=20)
    def attempt(i):
        try:
            return CombatEngine(store, FixedRng(.01, .9)).throw(
                KEY, 1, 2, "quick", f"parallel-{i}", when,
            )
        except CombatError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(attempt, (1, 2)))
    assert sum(isinstance(x, CombatError) for x in (a,b)) == 1
    assert CombatEngine(store).snapshot(KEY, 1, when).snowballs == 0
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM combat_events").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 1


def test_score_ledger_ignores_disqualified(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng(.01, .9))
    engine.throw(KEY, 1, 2, "quick", "ok", START)
    assert engine.leaderboard(KEY)[0][0] == "Player_1"
    store.review(KEY, 999, 1, "disqualified", "Confirmed abuse", START)
    assert all(row[2] != 1 for row in engine.leaderboard(KEY))
    assert engine.ledger_total(KEY, 1) == 13  # never delete historic scores


def test_invalid_attacks_cost_nothing(store):
    prepare(store)
    join(store, 3, "Chicago")
    engine = CombatEngine(store)
    with pytest.raises(CombatError, match="Friendly fire"):
        engine.throw(KEY, 1, 3, "quick", "friend", START)
    with pytest.raises(CombatError, match="yourself"):
        engine.throw(KEY, 1, 1, "quick", "self", START)
    with pytest.raises(CombatError, match="Choose"):
        engine.throw(KEY, 1, 2, "rocket", "bad", START)
    assert engine.snapshot(KEY, 1, START).snowballs == 8


def test_preregistered_players_regenerate_from_start_even_if_offline(tmp_path):
    s = Store(tmp_path / "start-time.sqlite3")
    s.initialize()
    s.ensure_season(KEY, START)
    s.register(KEY, 1, "BeforeLaunch", "Chicago", START - timedelta(days=1))
    s.transition(KEY, 99, "start", START, "Start")
    engine = CombatEngine(s)
    assert engine.snapshot(KEY, 1, START + timedelta(hours=1)).snowballs == 11
    assert engine.snapshot(KEY, 1, START + timedelta(hours=4)).snowballs == 12
    s.register(KEY, 2, "LateJoiner", "Detroit", START + timedelta(hours=4))
    assert engine.snapshot(KEY, 2, START + timedelta(hours=4)).snowballs == 8
    assert engine.snapshot(KEY, 2, START + timedelta(hours=4, minutes=20)).snowballs == 9


def test_shield_requires_three_new_hits_to_reactivate(store):
    join(store, 2)
    enter(store, 2)
    for uid in (1, 3, 4, 5, 6, 7):
        join(store, uid, "Chicago")
        enter(store, uid)
    engine = CombatEngine(store, FixedRng(*([.01, .9] * 6)))
    for i, uid in enumerate((1, 3, 4)):
        engine.throw(KEY, uid, 2, "quick", f"first-{uid}", START + timedelta(seconds=i*31))
    shield_end = START + timedelta(seconds=62, minutes=15)
    engine.throw(KEY, 5, 2, "quick", "new1", shield_end)
    r = engine.snapshot(KEY, 2, shield_end)
    assert r.shield_until == START + timedelta(seconds=62, minutes=15)
    engine.throw(KEY, 6, 2, "quick", "new2", shield_end + timedelta(seconds=31))
    engine.throw(KEY, 7, 2, "quick", "new3", shield_end + timedelta(seconds=62))
    assert engine.snapshot(KEY, 2, shield_end + timedelta(seconds=62)).shield_until > shield_end


def test_end_of_season_clamps_regeneration(store):
    prepare(store)
    end = START + timedelta(days=7)
    with store.connect() as con:
        con.execute("UPDATE player_resources SET snowballs=0, snowball_regen_at=? "
                    "WHERE discord_user_id=1", ((end - timedelta(seconds=3)).isoformat(),))
    engine = CombatEngine(store)
    assert engine.snapshot(KEY, 1, end + timedelta(days=30)).snowballs == 0
    with pytest.raises(CombatError, match="LIVE"):
        engine.throw(KEY, 1, 2, "quick", "too-late", end)


def test_disqualified_cannot_enter_or_throw(store):
    prepare(store)
    store.review(KEY, 999, 1, "disqualified", "Abuse", START)
    with pytest.raises(CombatError, match="disqualified"):
        CombatEngine(store).ready(KEY, 1, START)
    with pytest.raises(CombatError, match="disqualified"):
        CombatEngine(store).throw(KEY, 1, 2, "quick", "reject", START)


def test_rng_failure_is_atomic(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng())
    with pytest.raises(StopIteration):
        engine.throw(KEY, 1, 2, "quick", "fault", START)
    assert CombatEngine(store).snapshot(KEY, 1, START).snowballs == 8
    assert CombatEngine(store).ledger_total(KEY, 1) == 0
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM combat_events").fetchone()[0] == 0


def test_critical_and_hit_roll_are_recorded_immutably(store):
    prepare(store)
    engine = CombatEngine(store, FixedRng(.15, .04))
    result = engine.throw(KEY, 1, 2, "power", "roll-1", START)
    assert result.hit_roll == .15 and result.crit_roll == .04 and result.critical
    with store.connect() as con:
        row = con.execute("SELECT hit_roll,crit_roll,critical FROM combat_events").fetchone()
    assert (row["hit_roll"], row["crit_roll"], row["critical"]) == (.15, .04, 1)


def test_expired_fort_armour_cannot_absorb_an_attack(store):
    prepare(store)
    expires = START + timedelta(minutes=1)
    with store.connect() as con:
        con.execute("UPDATE player_resources SET armour_hp=25, armour_expires_at=? "
                    "WHERE discord_user_id=2", (expires.isoformat(),))
    engine = CombatEngine(store, FixedRng(.01, .9))
    result = engine.throw(KEY, 1, 2, "quick", "expired-fort", expires)
    assert result.armour_damage == 0
    assert result.warmth_damage == 8
    assert result.defense_points == 0
    assert engine.snapshot(KEY, 2, expires).armour_hp == 0


def test_migration_from_existing_v2_keeps_season_and_users(tmp_path):
    path = tmp_path / "old.sqlite3"
    db = Store(path)
    db.initialize()
    db.ensure_season(KEY, START)
    db.register(KEY, 123, "Legacy_User", "Chicago", START - timedelta(days=1))
    with db.connect() as con:
        con.execute("PRAGMA user_version=2")
        for table in ("player_resources", "score_ledger", "combat_events"):
            for suffix in ("immutable_update", "immutable_delete"):
                con.execute(f"DROP TRIGGER IF EXISTS {table}_{suffix}")
            con.execute(f"DROP TABLE IF EXISTS {table}")
    replacement = Store(path)
    replacement.initialize()
    replacement.initialize()  # migration is repeat-safe
    assert replacement.schema_version() == 6
    assert replacement.get_player(KEY, 123).mr_username == "Legacy_User"
    assert replacement.season(KEY).planned_start == START
    assert CombatEngine(replacement).snapshot(KEY, 123, START).snowballs == 8
