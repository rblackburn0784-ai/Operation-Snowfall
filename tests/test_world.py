"""Milestone D: persistent NPC fights, normalized city points and fair day boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from snowfall.db.store import CITIES, Store
from snowfall.services.world import WorldEngine, WorldError, THEMES
from snowfall.services.combat import CombatEngine
from snowfall.services.economy import EconomyEngine

KEY = 'world-2026'
START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


class FixedRNG:
    def __init__(self, n=0.0):
        self.n = n

    def random(self):
        return self.n


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / 'snow.sqlite3')
    db.initialize()
    db.ensure_season(KEY, START)
    for user, city in [(1, 'Chicago'),(2,'New York'),(3,'Detroit'),
                       (4,'Chicago'),(5,'Chicago'),(6,'New York')]:
        db.register(KEY, user, f'player_{user}', city, START - timedelta(days=1))
    db.transition(KEY, 800, 'start', START, 'test event started')
    return db


def attempt(db, user, kind='boss', n=0, t=None, rng=0):
    t = t if t is not None else START + timedelta(seconds=31*n)
    return WorldEngine(db, FixedRNG(rng)).attack(KEY,user,kind,f'{kind}-{user}-{n}-{t}',t)


def snapshot(db, day, city=None):
    with db.connect() as c:
        if city:
            return dict(c.execute('SELECT * FROM world_sieges WHERE season_key=? AND day=? '
                                  'AND city=?',(KEY,day,city)).fetchone())
        return dict(c.execute('SELECT * FROM world_days WHERE season_key=? AND day=?',
                              (KEY,day)).fetchone())


def credit(db, city, user, amount, day=1):
    with db.connect() as c:
        c.execute("INSERT INTO score_ledger (season_key,day,player_id,city,category,points,"
                  "source_key,created_at_utc) VALUES (?,?,?,?,'quest',?,?,?)",
                  (KEY,day,user,city,amount,f'test:{day}:{user}',START.isoformat()))


def test_migration_v5_and_day_initialised_once(store):
    assert store.schema_version() == 9
    first = WorldEngine(store).tick(KEY,START)
    assert first == (1,[1],[])
    assert WorldEngine(store).tick(KEY, START + timedelta(minutes=1)) == (1,[],[])
    boss = snapshot(store,1)
    assert boss['boss_initial_hp'] == 168  # 6 preregistrations x 28
    assert boss['theme'] == THEMES[0]
    assert snapshot(store,1,'Chicago')['initial_hp'] == 72
    assert snapshot(store,1,'New York')['initial_hp'] == 72
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM world_sieges WHERE day=1').fetchone()[0] == 6


def test_boss_hit_miss_and_shared_cooldown(store):
    one = attempt(store,1,n=0,rng=0)
    assert one.hit and one.damage == 12 and one.points == 5 and one.hp_after == 156
    with pytest.raises(WorldError,match='cooldown'):
        attempt(store,1,n=1,t=START + timedelta(seconds=15),rng=0)
    missed = attempt(store,1,n=2,rng=.99)
    assert not missed.hit and missed.damage == 0 and missed.points == 0
    assert CombatEngine(store).snapshot(KEY,1,START+timedelta(seconds=62)).snowballs == 6
    assert snapshot(store,1)['boss_hp'] == 156
    assert CombatEngine(store).ledger_total(KEY,1) == 5


def test_replay_and_other_pve_type_reuse_rejected(store):
    first=attempt(store,1,n=0)
    replay=WorldEngine(store).attack(KEY,1,'boss',first.interaction_id,
                                     START+timedelta(minutes=6))
    assert replay.repeated and first.points == replay.points
    with pytest.raises(WorldError,match='different attack'):
        WorldEngine(store).attack(KEY,1,'siege',first.interaction_id,START+timedelta(minutes=6))
    assert CombatEngine(store).ledger_total(KEY,1) == 5


def test_boss_defeat_awards_each_contributor_once_and_echo_after(store):
    # Fourteen 12-point hits defeat the 168-HP boss. Each player has <= 6 attempts.
    final = None
    for i in range(14):
        final = attempt(store, (i % 3)+1, n=i, rng=0)
    assert final.final_blow and final.hp_after == 0
    assert snapshot(store,1)['boss_hp'] == 0
    with store.connect() as c:
        totals = [WorldEngine._sum(c,KEY,i,1,'boss') for i in (1,2,3)]
        assert totals == [35, 45, 30]  # A=5 hits, B=5 hits & final, C=4 hits
        before_clear = c.execute("SELECT COUNT(*) FROM score_ledger WHERE source_key='boss:clear:1'").fetchone()[0]
        assert before_clear == 3
    # A fourth player was asleep during the global fight; six normal attempts are available.
    echoes=[]
    for j in range(6):
        echoes.append(attempt(store,4,n=100+j,t=START+timedelta(minutes=30,seconds=j*31)))
    assert all(r.echo and not r.final_blow and r.points == 5 for r in echoes)
    assert sum(r.points for r in echoes) == 30
    assert snapshot(store,1)['boss_hp'] == 0
    with store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM score_ledger WHERE source_key='boss:clear:1'").fetchone()[0] == 3


def test_siege_hit_and_rubble_still_scores_but_no_extra_city_clear(store):
    results=[]
    for user,n in ((1,0),(4,1),(5,2),(1,3),(4,4),(5,5)):
        results.append(attempt(store,user,'siege',n=n))
    assert all(r.hit for r in results)
    # Chicago fort starts at 72 HP, 6 x 14 defeats it.
    assert results[-1].final_blow and snapshot(store,1,'Chicago')['hp']==0
    late=attempt(store,1,'siege',n=10,t=START+timedelta(minutes=11))
    assert late.echo and late.hit and late.points == 8
    assert snapshot(store,1,'Chicago')['hp']==0
    assert len([r for r in results if r.final_blow])==1
    with pytest.raises(WorldError,match='limit'):
        # P1 already has 3 siege attempts (0,3,10): one more then blocked
        attempt(store,1,'siege',n=11,t=START+timedelta(minutes=12))
        attempt(store,1,'siege',n=12,t=START+timedelta(minutes=13))


def test_city_score_five_slot_denominator_bonus_and_minimum(store):
    WorldEngine(store).tick(KEY,START)
    for user,amount in ((1,300),(4,280),(5,200)):
        credit(store,'Chicago',user,amount)
    for user,amount in ((2,300),(6,300)):
        credit(store,'New York',user,amount)
    with store.connect() as c:
        c.execute('UPDATE world_sieges SET hp=0,cleared_at_utc=? '
                  'WHERE season_key=? AND day=1 AND city=?', (START.isoformat(),KEY,'Chicago'))
    rows=WorldEngine(store).standings(KEY,START+timedelta(hours=1))
    chi=next(r for r in rows if r.city=='Chicago')
    ny=next(r for r in rows if r.city=='New York')
    assert chi.todays_score_x100 == 18100  # 780 / 5 + 25
    assert chi.qualifying_today
    assert ny.todays_score_x100==0 and not ny.qualifying_today
    assert chi.provisional


def test_city_participation_bonus_capped_at_forty(tmp_path):
    db=Store(tmp_path/'big.sqlite3')
    db.initialize()
    db.ensure_season(KEY,START)
    for i in range(1,21):
        db.register(KEY,i,f'user_{i}','Chicago',START-timedelta(days=1))
    db.transition(KEY,800,'start',START,'test')
    WorldEngine(db).tick(KEY,START)
    for i in range(1,21):
        credit(db,'Chicago',i,300)
    with db.connect() as c:
        c.execute("UPDATE world_sieges SET hp=0,cleared_at_utc=? WHERE season_key=? AND day=1 "
                  "AND city='Chicago'",(START.isoformat(),KEY))
    chi=WorldEngine(db).standings(KEY,START)[0]
    assert chi.score_x100==36500
    assert snapshot(db,1,'Chicago')['initial_hp']==240


def test_rollover_freezes_score_day_and_does_not_double_lock(store):
    WorldEngine(store).tick(KEY,START)
    for user in (1,4,5):
        credit(store,'Chicago',user,150)
    score=WorldEngine(store).standings(KEY,START)[0].todays_score_x100
    res=WorldEngine(store).tick(KEY,START+timedelta(days=1))
    assert res[0]==2 and res[1]==[2] and set(res[2])=={1}
    assert WorldEngine(store).tick(KEY,START+timedelta(days=1,minutes=2))==(2,[],[])
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM city_day_snapshots WHERE day=1').fetchone()[0]==6
        assert c.execute("SELECT score_x100 FROM city_day_snapshots WHERE day=1 AND city='Chicago'").fetchone()[0]==score
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):
            c.execute("UPDATE city_day_snapshots SET score_x100=999 WHERE city='Chicago'")
    assert WorldEngine(store).standings(KEY,START+timedelta(days=1))[0].score_x100==score


def test_prior_day_active_count_drives_day_two_boss(tmp_path):
    db=Store(tmp_path/'active.sqlite3')
    db.initialize()
    db.ensure_season(KEY,START)
    for i in range(1,9):
        db.register(KEY,i,f'player{i}',CITIES[i%6],START-timedelta(days=1))
    db.transition(KEY,800,'start',START,'test')
    WorldEngine(db).tick(KEY,START)
    for i in range(1,9):
        credit(db,CITIES[i%6],i,8)
    WorldEngine(db).tick(KEY,START+timedelta(days=1))
    assert snapshot(db,2)['boss_initial_hp']==224
    assert snapshot(db,2)['theme']==THEMES[1]


def test_pve_pause_freezes_day_and_cooldown(store):
    attempt(store,1,n=0)
    store.transition(KEY,800,'pause',START+timedelta(seconds=10),'break')
    with pytest.raises(WorldError,match='LIVE'):
        attempt(store,1,n=4,t=START+timedelta(hours=4))
    assert WorldEngine(store).tick(KEY,START+timedelta(hours=4))[0]==1
    store.transition(KEY,800,'resume',START+timedelta(hours=4),'resume')
    with pytest.raises(WorldError,match='cooldown'):
        attempt(store,1,n=5,t=START+timedelta(hours=4,seconds=10))
    assert attempt(store,1,n=6,t=START+timedelta(hours=4,seconds=35)).hit


def test_pve_limit_and_zero_balls_never_spend_on_invalid(store):
    for n in range(6):
        attempt(store,1,n=n,t=START+timedelta(seconds=31*n))
    before=CombatEngine(store).snapshot(KEY,1,START+timedelta(minutes=4))
    with pytest.raises(WorldError,match='limit'):
        attempt(store,1,n=99,t=START+timedelta(minutes=4))
    after=CombatEngine(store).snapshot(KEY,1,START+timedelta(minutes=4))
    assert before.snowballs==after.snowballs


def test_shared_snowball_between_pvp_and_pve(store):
    with store.connect() as c:
        c.execute('UPDATE player_resources SET snowballs=1 WHERE season_key=? AND discord_user_id=?',
                  (KEY,1))
    CombatEngine(store).ready(KEY,2,START)
    first=attempt(store,1,n=0)
    assert first.hit
    with pytest.raises(WorldError,match='No snowballs'):
        attempt(store,1,'siege',n=1,t=START+timedelta(seconds=31))
    assert CombatEngine(store).snapshot(KEY,1,START+timedelta(seconds=31)).snowballs==0


def test_double_threaded_npc_attack_cannot_overspend(store):
    with store.connect() as c:
        c.execute('UPDATE player_resources SET snowballs=1 WHERE season_key=? AND discord_user_id=?',
                  (KEY,1))
    def run(n):
        try:
            return attempt(store,1,'boss',n=n,t=START).points
        except WorldError:
            return -1
    with ThreadPoolExecutor(max_workers=2) as e:
        scores=list(e.map(run,(1,2)))
    assert sorted(scores)==[-1,5]
    assert CombatEngine(store).snapshot(KEY,1,START).snowballs==0


def test_day_three_quest_theme_bonus_once(store):
    at=START+timedelta(days=2)
    EconomyEngine(store).guard(KEY,1,'on','d3-guard',at)
    claim=EconomyEngine(store).claim_quest(KEY,1,'community',at)
    assert 'Whiteout' in claim.text
    assert CombatEngine(store).ledger_total(KEY,1)==30
    repeated=EconomyEngine(store).claim_quest(KEY,1,'community',at)
    assert repeated.repeated and CombatEngine(store).ledger_total(KEY,1)==30


def test_day_five_and_six_theme_rewards_single_shot(store):
    five=START+timedelta(days=4)
    first=attempt(store,1,'boss',n=50,t=five,rng=.99)
    assert not first.hit and first.theme_points==10
    second=attempt(store,1,'boss',n=51,t=five+timedelta(seconds=31),rng=.99)
    assert second.theme_points==0
    six=START+timedelta(days=5)
    assert attempt(store,1,'siege',n=60,t=six,rng=0).theme_points==0
    assert attempt(store,1,'boss',n=61,t=six+timedelta(seconds=31),rng=.99).theme_points==20
    assert attempt(store,1,'boss',n=62,t=six+timedelta(seconds=62),rng=.99).theme_points==0
    with store.connect() as c:
        assert WorldEngine._sum(c,KEY,1,5,'theme')==10
        assert WorldEngine._sum(c,KEY,1,6,'theme')==20


def test_seven_days_close_and_snapshot_all(store):
    day, new, locked=WorldEngine(store).tick(KEY,START+timedelta(days=7))
    assert day==7 and new==list(range(1,8)) and set(locked)==set(range(1,8))
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM city_day_snapshots').fetchone()[0]==42
    with pytest.raises(WorldError,match='LIVE'):
        attempt(store,1,n=200,t=START+timedelta(days=7))


def test_disqualified_or_flagged_players_excluded_from_city_scores(store):
    WorldEngine(store).tick(KEY,START)
    for i in (1,4,5):
        credit(store,'Chicago',i,100)
    assert next(r for r in WorldEngine(store).standings(KEY,START) if r.city=='Chicago').qualifying_today
    store.review(KEY,800,5,'flagged','Duplicate identity allegation',START)
    assert not next(r for r in WorldEngine(store).standings(KEY,START) if r.city=='Chicago').qualifying_today


def test_restart_schema_and_immutable_pve_records(store):
    shot=attempt(store,1,n=0)
    reopened=Store(store.path)
    reopened.initialize()
    assert reopened.schema_version()==9
    assert WorldEngine(reopened).attack(KEY,1,'boss',shot.interaction_id,START).repeated
    with reopened.connect() as c:
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):
            c.execute('DELETE FROM pve_events')


def test_boss_host_configuration_audited_and_immutable_after_kickoff(tmp_path):
    db = Store(tmp_path / 'configured.sqlite3')
    db.initialize()
    db.ensure_season(KEY, START)
    engine = WorldEngine(db)
    engine.configure_boss(KEY, 800, True, 400, 'Kat selected 400 HP', START - timedelta(days=1))
    assert db.audit_entries(KEY)[-1]['action'] == 'world:boss_settings'
    with pytest.raises(WorldError, match='reason'):
        engine.configure_boss(KEY, 800, False, None, '', START - timedelta(hours=2))
    with pytest.raises(WorldError, match='HP'):
        engine.configure_boss(KEY, 800, True, 100, 'bad', START - timedelta(hours=2))
    db.register(KEY, 1, 'player1', 'Chicago', START - timedelta(hours=2))
    db.transition(KEY, 800, 'start', START, 'test')
    engine.tick(KEY, START)
    assert snapshot(db, 1)['boss_initial_hp'] == 400
    with pytest.raises(WorldError, match='locked'):
        engine.configure_boss(KEY, 800, False, None, 'after kickoff', START + timedelta(seconds=1))


def test_disabled_boss_rejects_actions_and_siege_still_works(tmp_path):
    db=Store(tmp_path/'disabled.sqlite3')
    db.initialize()
    db.ensure_season(KEY, START)
    db.register(KEY, 1, 'player1', 'Chicago', START - timedelta(days=1))
    WorldEngine(db).configure_boss(KEY, 800, False, None, 'No boss this event', START - timedelta(days=1))
    db.transition(KEY, 800, 'start', START, 'test')
    state=WorldEngine(db).status(KEY,1,START)
    assert not state.boss_enabled and state.boss_hp == 0
    with pytest.raises(WorldError,match='disabled'):
        WorldEngine(db).attack(KEY,1,'boss','disabled-boss',START)
    siege=WorldEngine(db,FixedRNG(0)).attack(KEY,1,'siege','open-siege',START)
    assert siege.hit and siege.points==8


def test_schema_v4_restarts_to_v5_without_rewriting_old_combat(store):
    CombatEngine(store).ready(KEY,2,START)
    old=CombatEngine(store,FixedRNG(0)).throw(KEY,1,2,'quick','v4-old-shot',START)
    with store.connect() as c:
        before=dict(c.execute("SELECT * FROM combat_events WHERE interaction_id='v4-old-shot'").fetchone())
        c.execute('DROP TABLE pve_events')
        c.execute('DROP TABLE city_day_snapshots')
        c.execute('DROP TABLE world_sieges')
        c.execute('DROP TABLE world_days')
        c.execute('DROP TABLE world_settings')
        c.execute('PRAGMA user_version=4')
    store.initialize()
    assert store.schema_version()==9
    with store.connect() as c:
        after=dict(c.execute("SELECT * FROM combat_events WHERE interaction_id='v4-old-shot'").fetchone())
        assert before==after
    assert CombatEngine(store).ledger_total(KEY,1)==old.points_awarded


def test_golden_city_credit_is_capped_to_ten(store):
    from snowfall.services.economy import EconomyEngine
    WorldEngine(store).tick(KEY,START)
    economy=EconomyEngine(store,FixedRNG(.999))
    economy.guard(KEY,1,'on','flag-guard',START)
    economy.claim_quest(KEY,1,'community',START)
    economy.present(KEY,1,'rare-gift',START)
    economy.guard(KEY,1,'off','un-guard',START)
    CombatEngine(store).ready(KEY,2,START)
    golden=CombatEngine(store,FixedRNG(0)).throw(KEY,1,2,'golden','gold-pvp',START)
    assert golden.city_credit==10 and golden.points_awarded>10
    credit(store,'Chicago',4,20)
    credit(store,'Chicago',5,20)
    row=next(r for r in WorldEngine(store).standings(KEY,START) if r.city=='Chicago')
    assert row.score_x100 == (30+20+20)*20  # quest 20 + golden 10 for P1, 20 + 20


def test_pve_does_not_award_during_finalized_and_after_pause(store):
    WorldEngine(store).tick(KEY,START)
    store.transition(KEY,800,'pause',START+timedelta(hours=1),'break')
    before=WorldEngine(store).status(KEY,1,START+timedelta(hours=4))
    assert before.day==1 and before.phase=='paused'
    with pytest.raises(WorldError,match='LIVE'):
        WorldEngine(store).attack(KEY,1,'siege','paused-siege',START+timedelta(hours=4))
    store.transition(KEY,800,'resume',START+timedelta(hours=4),'again')
    close=START+timedelta(days=7,hours=3)
    WorldEngine(store).tick(KEY,close)
    assert store.season(KEY).phase(close)=='closed'
    with pytest.raises(WorldError,match='LIVE'):
        WorldEngine(store).attack(KEY,1,'boss','too-late',close)
