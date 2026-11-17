"""Season-scoped cosmetic milestones, authoritative statistics, schema upgrades."""
from datetime import datetime, timezone

import pytest

from snowfall.db.store import Store
from snowfall.services.achievements import AchievementEngine, TrophyError, DEFAULT_TITLE
from snowfall.services.boss_personality import (
    crossed_phases, phase_announcement, reached_phases, reaction_for_result,
)
from snowfall.services.world import PveResult

NOW = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
SEASON = 'christmas-test'


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / 'trophies.sqlite3')
    store.initialize()
    store.ensure_season(SEASON, NOW)
    store.register(SEASON, 11, 'TheDude', 'Chicago', NOW)
    return store


def test_migration_to_v7_is_idempotent_and_starts_with_no_titles(setup):
    assert setup.schema_version() == 8
    setup.initialize()
    assert setup.schema_version() == 8
    assert AchievementEngine(setup).cabinet(SEASON, 11).equipped_title == DEFAULT_TITLE
    with setup.connect() as con:
        assert 'player_titles' in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_initial_cabinet_is_all_locked_without_score_effects(setup):
    engine = AchievementEngine(setup)
    before = engine.cabinet(SEASON, 11)
    assert before.unlocked_count == 0
    assert before.records.accuracy == 0
    assert before.records.pvp_hits == 0
    assert len(before.trophies) == 16
    with pytest.raises(TrophyError, match='locked'):
        engine.equip(SEASON, 11, 'deadeye')
    with setup.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM score_ledger').fetchone()[0] == 0


def test_first_hit_unlocks_title_and_season_selection_persists(setup):
    with setup.connect() as con:
        con.execute('''INSERT INTO combat_events(interaction_id,season_key,day,
            attacker_id,target_id,target_city,style,happened_at_utc,effective_at_utc,
            hit,critical,hit_roll,armour_damage,warmth_damage,knocked_out,
            points_awarded,bonus_city,bonus_ko,defense_points)
            VALUES('first',?,1,11,22,'Detroit','quick',?,?,1,0,0.1,3,12,0,10,0,0,0)''',
            (SEASON, NOW.isoformat(), NOW.isoformat()))
    engine = AchievementEngine(setup)
    cab = engine.cabinet(SEASON, 11)
    assert cab.records.pvp_throws == 1 and cab.records.pvp_hits == 1
    assert cab.records.best_hit == 15 and cab.records.accuracy == 100.0
    assert cab.unlocked_count == 1
    assert engine.equip(SEASON, 11, 'first_flurry') == 'Snowball Rookie'
    assert engine.cabinet(SEASON, 11).equipped_key == 'first_flurry'
    setup.initialize()
    assert engine.cabinet(SEASON, 11).equipped_title == 'Snowball Rookie'
    engine.equip(SEASON, 11, 'none')
    assert engine.cabinet(SEASON, 11).equipped_title == DEFAULT_TITLE


def test_titles_never_cross_season_or_let_another_user_equip(setup):
    engine = AchievementEngine(setup)
    with pytest.raises(TrophyError, match='Register'):
        engine.cabinet(SEASON, 999)
    with pytest.raises(TrophyError, match='Register'):
        engine.equip(SEASON, 999, 'none')
    with pytest.raises(TrophyError, match='Unknown title'):
        engine.equip(SEASON, 11, 'arbitrary sql')
    setup.ensure_season('next-test', NOW)
    setup.register('next-test', 11, 'AnotherTheDude', 'New York', NOW)
    assert engine.cabinet('next-test', 11).unlocked_count == 0
    assert engine.cabinet('next-test', 11).equipped_title == DEFAULT_TITLE


def test_boss_record_counts_exclude_unsupported_shared_echo_damage(setup):
    with setup.connect() as con:
        for k, kind, damage, echo, hit in [
            ('boss1', 'boss', 18, 0, 1), ('boss2', 'boss', 20, 1, 1),
            ('siege1', 'siege', 14, 0, 1), ('siege2', 'siege', 14, 1, 1),
        ]:
            con.execute('''INSERT INTO pve_events(interaction_id,season_key,day,
                kind,attacker_id,city,happened_at_utc,effective_at_utc,hit_roll,
                hit,damage,echo,final_blow,points_awarded,hp_after,max_hp)
                VALUES(?,?,1,?,11,'Chicago',?,?,0.1,?,?,?,0,5,50,150)''',
                (k, SEASON, kind, NOW.isoformat(), NOW.isoformat(), hit, damage, echo))
    cab = AchievementEngine(setup).cabinet(SEASON, 11)
    assert cab.records.boss_damage == 18
    assert cab.records.siege_damage == 14
    assert cab.records.boss_attacks == 2 and cab.records.siege_attacks == 2
    assert cab.records.successful_boss_hits == 2
    assert cab.unlocked_count == 0


def test_phase_crossing_exact_boundary_and_echo_handling():
    assert crossed_phases(151, 150, 200) == (75,)
    assert crossed_phases(200, 50, 200) == (75, 50, 25)
    assert crossed_phases(150, 149, 200) == ()
    assert crossed_phases(100, 80, 200) == ()
    assert crossed_phases(100, 0, 0) == ()
    hit = PveResult('id', 'boss', 3, 'Chicago', True, 1, 5, 0, 150, 200, False, False)
    assert 'hat' in reaction_for_result(hit).lower()
    from dataclasses import replace
    assert reaction_for_result(replace(hit, echo=True)) is None
    assert reaction_for_result(replace(hit, hit=False)) is None
    assert reaction_for_result(replace(hit, kind='siege')) is None
    assert 'fallen' in reaction_for_result(replace(hit, hp_after=0, final_blow=True)).lower()


def test_phase_announcement_is_validated():
    assert '75%' in phase_announcement(3, 75)
    assert '50%' in phase_announcement(3, 50)
    assert '25%' in phase_announcement(3, 25)
    with pytest.raises(ValueError):
        phase_announcement(8, 75)
    with pytest.raises(ValueError):
        phase_announcement(1, 45)


def test_phase_reads_live_boss_hp_and_ignores_disabled(setup):
    assert reached_phases(setup, SEASON, 1) == ()
    with setup.connect() as con:
        con.execute('''INSERT INTO world_days(season_key,day,effective_start_utc,
            theme,boss_initial_hp,boss_hp,created_at_utc)
            VALUES(?,1,?,'Opening Barrage',200,100,?)''',
            (SEASON, NOW.isoformat(), NOW.isoformat()))
    assert reached_phases(setup, SEASON, 1) == (75, 50)
    with setup.connect() as con:
        con.execute('INSERT INTO world_settings(season_key,boss_enabled) VALUES (?,0)', (SEASON,))
    assert reached_phases(setup, SEASON, 1) == ()


def test_real_old_v6_database_upgrade_keeps_score_tables(tmp_path):
    """A v6 migration must not update immutable history or reset score rows."""
    path = tmp_path / 'history.sqlite3'
    store = Store(path)
    store.initialize()
    store.ensure_season(SEASON, NOW)
    store.register(SEASON, 11, 'TheDude', 'Chicago', NOW)
    with store.connect() as con:
        con.execute("INSERT INTO score_ledger(season_key,day,player_id,city,category,points,source_key,created_at_utc) VALUES(?,1,11,'Chicago','quest',20,'quest1',?)", (SEASON, NOW.isoformat()))
        con.execute('PRAGMA user_version=6')
        con.execute('DROP TABLE player_titles')
    store.initialize()
    assert store.schema_version() == 8
    with store.connect() as con:
        assert con.execute('SELECT points FROM score_ledger').fetchone()[0] == 20
        assert con.execute('SELECT COUNT(*) FROM player_titles').fetchone()[0] == 0


def test_trophy_illustration_png_and_boss_victory_are_cosmetic(setup):
    from io import BytesIO
    from PIL import Image
    from snowfall.graphics import cards
    cab = AchievementEngine(setup).cabinet(SEASON, 11)
    picture = cards.trophy_cabinet_card(cab)
    with Image.open(BytesIO(picture)) as rendered:
        assert rendered.size == (960, 540)
        assert rendered.mode == 'RGB'
    from dataclasses import replace
    final = PveResult('b1', 'boss', 2, 'Chicago', True, 18, 15, 0,
                      0, 150, False, True)
    sample = cards.world_result_card(final)
    assert sample.startswith(b'\x89PNG\r\n\x1a\n')
    assert repr(final) == repr(replace(final))
