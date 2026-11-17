"""v0.2.7 social arcade: real game turns, fairness, isolation and Discord UI."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import random
import sqlite3
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.services.social_arcade import (
    GAMES, STAMPS, DAILY_GAME_CAP, SocialArcadeEngine, SocialArcadeError,
    _generate,
)
from snowfall.graphics.social_arcade_cards import (
    lobby_card, game_card, passport_card, scoreboard_card,
)

START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
SEASON = "social-arcade-2026"


@pytest.fixture
def game(tmp_path):
    db = Store(tmp_path / "arcade.sqlite3")
    db.initialize()
    db.ensure_season(SEASON, START)
    for uid, name, city in ((101, "TheDude", "Chicago"),
                             (102, "Jago", "Chicago"),
                             (201, "SantaFox", "New York"),
                             (301, "DetroitAce", "Detroit")):
        db.register(SEASON, uid, name, city, START - timedelta(days=1))
    db.transition(SEASON, 900, "start", START, "Social arcade launch")
    return db


def assert_png(blob):
    assert blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) < 2_500_000
    with Image.open(BytesIO(blob)) as img:
        assert img.size == (960, 540) and img.mode == "RGB"


def official_state(db):
    with db.connect() as con:
        return (
            con.execute("SELECT COUNT(*),COALESCE(SUM(points),0) FROM score_ledger").fetchone()[:],
            con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM combat_events").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM pve_events").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM item_events").fetchone()[0],
            con.execute("SELECT COUNT(*),COALESCE(SUM(snowflakes),0),"
                        "COALESCE(SUM(snowballs),0) FROM player_resources").fetchone()[:],
        )


def solve(engine, db, mode, uid=101, now=START, *, perfect=True):
    run = engine.begin(SEASON, uid, mode, now)
    with db.connect() as con:
        answers = json.loads(con.execute(
            "SELECT puzzles_json FROM social_arcade_runs WHERE session_id=?",
            (run.session_id,)).fetchone()[0])
    events = []
    for i, puzzle in enumerate(answers):
        answer = puzzle["answer"] if perfect or i else next(
            option for option in puzzle["choices"] if option != puzzle["answer"])
        result = engine.move(
            SEASON, uid, run.session_id, i, answer,
            f"arcade:{run.session_id}:{i}", now+timedelta(seconds=i+1))
        events.append(result)
    assert events[-1].session.finished
    return run, events


def test_game_definitions_have_five_distinct_interactive_puzzle_types():
    assert set(GAMES) == {"gallery","safe","snowman","catch","trivia"}
    assert len(GAMES) == 5 and len(STAMPS) == 11
    assert GAMES["safe"].rounds == 3
    assert GAMES["snowman"].rounds == 4
    assert all(GAMES[key].rounds == 5 for key in ("gallery","catch","trivia"))
    assert DAILY_GAME_CAP == 3
    for mode in GAMES:
        puzzles = _generate(mode,random.Random(123))
        assert len(puzzles) == GAMES[mode].rounds
        for puzzle in puzzles:
            assert puzzle["answer"] in puzzle["choices"]
            assert len(puzzle["choices"]) == len(set(puzzle["choices"])) == 3
            assert puzzle["prompt"] and puzzle["explanation"]
    assert _generate("trivia",random.Random(0)) != _generate("trivia",random.Random(1))
    with pytest.raises(SocialArcadeError, match="Unknown"):
        _generate("hack",random.Random(1))


def test_five_games_perfect_records_mastery_stamps_social_honours_only(game):
    engine=SocialArcadeEngine(game,random.Random(12))
    before=official_state(game)
    lobby=engine.lobby(SEASON,101,START)
    assert lobby.day==1 and lobby.phase=="live" and lobby.completed==0
    assert len(lobby.records)==5 and len(lobby.stamps)==0
    assert_png(lobby_card(lobby))
    assert_png(passport_card(lobby))
    for mode in GAMES:
        initial,turns=solve(engine,game,mode)
        assert initial.step==0 and initial.current.index==1
        assert initial.attempt==1 and initial.score==0
        assert turns[-1].session.score==100
        assert all(t.right and not t.repeated for t in turns)
        if mode=="safe":
            assert turns[-1].delta==40
        snap=engine.lobby(SEASON,101,START)
        assert snap.record(mode).personal_best==100
        assert snap.record(mode).attempts_today==1
        assert snap.record(mode).games_played==1
        assert_png(game_card(turns[-1].session))
        assert_png(passport_card(snap))
    final=engine.lobby(SEASON,101,START)
    assert final.completed==5 and final.bests_total==500
    assert set(final.stamps)==set(STAMPS)
    assert "all_five" in final.stamps
    assert official_state(game)==before
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM social_arcade_stamps").fetchone()[0]==11
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0]==5
        assert con.execute("SELECT COUNT(*) FROM social_arcade_turns").fetchone()[0]==22


def test_wrong_choices_replay_validation_and_three_daily_starts(game):
    engine=SocialArcadeEngine(game,random.Random(44))
    first=engine.begin(SEASON,101,"gallery",START)
    resumed=engine.begin(SEASON,101,"gallery",START)
    assert first.session_id==resumed.session_id and first.attempt==1
    assert len(resumed.current.choices)==3
    with game.connect() as con:
        answer=json.loads(con.execute("SELECT puzzles_json FROM social_arcade_runs "
            "WHERE session_id=?",(first.session_id,)).fetchone()[0])[0]["answer"]
    wrong=next(x for x in first.current.choices if x!=answer)
    with pytest.raises(SocialArcadeError,match="offered"):
        engine.move(SEASON,101,first.session_id,0,"not-an-option","fake",START)
    with pytest.raises(SocialArcadeError,match="out of date"):
        engine.move(SEASON,101,first.session_id,2,wrong,"stale",START)
    applied=engine.move(SEASON,101,first.session_id,0,wrong,"first-move",START)
    assert not applied.right and applied.delta==0 and applied.session.step==1
    replay=engine.move(SEASON,101,first.session_id,0,wrong,"first-move",START)
    assert replay.repeated and not replay.right and replay.session.step==1
    with pytest.raises(SocialArcadeError,match="different arcade"):
        engine.move(SEASON,101,first.session_id,0,answer,"first-move",START)
    with pytest.raises(SocialArcadeError,match="out of date"):
        engine.move(SEASON,101,first.session_id,0,wrong,"stale-move",START)
    with pytest.raises(SocialArcadeError,match="belongs to another player"):
        engine.session(SEASON,201,first.session_id,START)
    # Finish first imperfect run. Two more are allowed, fourth is not.
    with game.connect() as con:
        rows=json.loads(con.execute("SELECT puzzles_json FROM social_arcade_runs "
                "WHERE session_id=?",(first.session_id,)).fetchone()[0])
    for i in range(1,len(rows)):
        engine.move(SEASON,101,first.session_id,i,rows[i]["answer"],f"first:{i}",START)
    assert engine.session(SEASON,101,first.session_id,START).score==80
    assert engine.lobby(SEASON,101,START).record("gallery").attempts_today==1
    _,events=solve(engine,game,"gallery")
    assert events[-1].session.attempt==2
    _,events=solve(engine,game,"gallery")
    assert events[-1].session.attempt==3
    with pytest.raises(SocialArcadeError,match="all three daily"):
        engine.begin(SEASON,101,"gallery",START)
    assert engine.lobby(SEASON,101,START).record("gallery").personal_best==100
    assert engine.begin(SEASON,101,"catch",START).attempt==1


def test_concurrent_choices_and_interaction_ids_are_authoritative(game):
    engine=SocialArcadeEngine(game,random.Random(7))
    session=engine.begin(SEASON,101,"catch",START)
    choices=session.current.choices
    def submit(i):
        try:
            return engine.move(SEASON,101,session.session_id,0,
                               choices[i],f"click-{i}",START)
        except SocialArcadeError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,(0,1)))
    assert sum(not isinstance(x,SocialArcadeError) for x in results)==1
    assert any("out of date" in str(x) for x in results if isinstance(x,SocialArcadeError))
    assert engine.session(SEASON,101,session.session_id,START).step==1
    with game.connect() as con:
        entry=con.execute("SELECT interaction_id,choice FROM social_arcade_turns "
                          "WHERE session_id=?",(session.session_id,)).fetchone()
        assert con.execute("SELECT COUNT(*) FROM social_arcade_turns").fetchone()[0]==1
    with pytest.raises(SocialArcadeError,match="different arcade choice"):
        engine.move(SEASON,201,session.session_id,0,entry[1],entry[0],START)
    repeated=engine.move(SEASON,101,session.session_id,0,entry[1],entry[0],START)
    assert repeated.repeated


def test_quiz_and_safecracker_results_cannot_be_submitted_by_guessing_outside_options(game):
    engine=SocialArcadeEngine(game,random.Random(55))
    for mode in ("trivia","safe"):
        start=engine.begin(SEASON,101,mode,START)
        with pytest.raises(SocialArcadeError,match="offered"):
            engine.move(SEASON,101,start.session_id,0,"arbitrary-answer",f"bad-{mode}",START)
        assert engine.session(SEASON,101,start.session_id,START).step==0
        assert engine.begin(SEASON,101,mode,START).session_id==start.session_id
    assert official_state(game)[0]==(0,0)


def test_persistence_after_restart_and_migration_from_v9(game):
    engine=SocialArcadeEngine(game,random.Random(6))
    before=official_state(game)
    begun=engine.begin(SEASON,101,"snowman",START)
    choice=begun.current.choices[0]
    moved=engine.move(SEASON,101,begun.session_id,0,choice,"restart-move",START)
    assert moved.session.step==1
    reopened=Store(game.path)
    reopened.initialize()
    assert reopened.schema_version()==10
    again=SocialArcadeEngine(reopened).begin(SEASON,101,"snowman",START)
    assert again.session_id==begun.session_id and again.step==1
    assert SocialArcadeEngine(reopened).move(
        SEASON,101,begun.session_id,0,choice,"restart-move",START).repeated
    assert official_state(game)==before

    with game.connect() as con:
        for table in ("social_arcade_turns","social_arcade_stamps","social_arcade_runs"):
            con.execute(f"DROP TABLE {table}")
        con.execute("PRAGMA user_version=9")
        players_before=con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    reopened.initialize()
    reopened.initialize()
    assert reopened.schema_version()==10
    with reopened.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0]==players_before
        assert con.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        assert all(con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                               "AND name=?",(n,)).fetchone()
                   for n in ("social_arcade_turns","social_arcade_stamps","social_arcade_runs"))


def test_stamps_turns_are_immutable_and_session_identity_protected(game):
    engine=SocialArcadeEngine(game,random.Random(71))
    run,turns=solve(engine,game,"safe")
    assert turns[-1].session.score==100
    with game.connect() as con:
        for table in ("social_arcade_turns","social_arcade_stamps"):
            with pytest.raises(sqlite3.IntegrityError,match="immutable"):
                con.execute(f"DELETE FROM {table}")
            with pytest.raises(sqlite3.IntegrityError,match="immutable"):
                con.execute(f"UPDATE {table} SET season_key='hacked'")
        with pytest.raises(sqlite3.IntegrityError,match="integrity"):
            con.execute("UPDATE social_arcade_runs SET score=0 WHERE session_id=?",
                        (run.session_id,))
        with pytest.raises(sqlite3.IntegrityError,match="cannot be deleted"):
            con.execute("DELETE FROM social_arcade_runs WHERE session_id=?",
                        (run.session_id,))


def test_pauses_day_rollover_and_closed_event_keep_records_but_block_play(game):
    engine=SocialArcadeEngine(game,random.Random(34))
    session=engine.begin(SEASON,101,"trivia",START)
    game.transition(SEASON,900,"pause",START+timedelta(hours=1),"Freeze game clock")
    paused=engine.lobby(SEASON,101,START+timedelta(days=4))
    assert paused.phase=="paused" and paused.day==1
    assert paused.record("trivia").active_id==session.session_id
    with pytest.raises(SocialArcadeError,match="live"):
        engine.begin(SEASON,101,"gallery",START+timedelta(days=4))
    with pytest.raises(SocialArcadeError,match="live"):
        engine.move(SEASON,101,session.session_id,0,
                    session.current.choices[0],"paused-move",START+timedelta(days=4))
    game.transition(SEASON,900,"resume",START+timedelta(days=4),"Resume")
    day2=START+timedelta(days=5,minutes=1)
    new=engine.begin(SEASON,101,"trivia",day2)
    assert new.day==2 and new.attempt==1 and new.session_id!=session.session_id
    with pytest.raises(SocialArcadeError,match="previous"):
        engine.session(SEASON,101,session.session_id,day2)
    with pytest.raises(SocialArcadeError,match="previous"):
        engine.move(SEASON,101,session.session_id,0,
                    session.current.choices[0],"old-day-move",day2)
    expired=START+timedelta(days=12)
    assert engine.lobby(SEASON,101,expired).phase=="closed"
    with pytest.raises(SocialArcadeError,match="live"):
        engine.begin(SEASON,101,"gallery",expired)


def test_leaderboards_city_cup_and_anti_review_filters(game):
    e=SocialArcadeEngine(game,random.Random(77))
    solve(e,game,"gallery",uid=101)
    solve(e,game,"gallery",uid=201,perfect=False)
    solve(e,game,"snowman",uid=201)
    today=e.leaderboard(SEASON,101,"gallery",START,daily=True)
    season=e.leaderboard(SEASON,101,"gallery",START)
    assert [r.user_id for r in today]==[101,201]
    assert [r.best for r in season]==[100,80]
    assert today[0].games==1
    city=e.city_table(SEASON,101,START)
    assert city[0].city=="New York" and city[0].score==180
    assert city[1].city=="Chicago" and city[1].score==100
    assert_png(scoreboard_card("Top Players",season))
    assert_png(scoreboard_card("City Cup",city))
    game.review(SEASON,900,201,"flagged","Review suspect bot",START)
    assert [r.user_id for r in e.leaderboard(SEASON,101,"gallery",START)]==[101]
    assert [r.city for r in e.city_table(SEASON,101,START)]==["Chicago"]
    with pytest.raises(SocialArcadeError,match="identity review"):
        e.begin(SEASON,201,"catch",START)


def test_per_user_season_and_practice_databases_isolated(game,tmp_path):
    e=SocialArcadeEngine(game,random.Random(3))
    solve(e,game,"catch")
    game.ensure_season("alternate",START)
    game.register("alternate",101,"AltDude","Las Vegas",START-timedelta(days=1))
    game.transition("alternate",900,"start",START,"isolated")
    assert SocialArcadeEngine(game).lobby("alternate",101,START).completed==0
    assert e.lobby(SEASON,201,START).completed==0
    practice=Store(tmp_path/"practice.sqlite3")
    practice.initialize()
    practice.ensure_season(SEASON,START)
    practice.register(SEASON,101,"TheDude","Chicago",START-timedelta(days=1))
    practice.transition(SEASON,900,"start",START,"practice")
    assert SocialArcadeEngine(practice).lobby(SEASON,101,START).completed==0


def test_profile_showcase_displays_cosmetic_passport_not_paid_item(game):
    from snowfall.services.showcase import showcase
    from snowfall.ui.showcase import card_text
    from snowfall.graphics.cards import profile_card
    e=SocialArcadeEngine(game,random.Random(33))
    solve(e,game,"gallery")
    display=showcase(game,SEASON,101,START)
    assert len(display.arcade_stamps)==2
    assert "Winter Arcade" in card_text(display)
    assert_png(profile_card(display.player.mr_username,display.player.city,
                            display.resources,display.points,showcase=display))
    assert official_state(game)[0]==(0,0)


def test_discord_arcade_buttons_dropdowns_and_one_message_updates(game,monkeypatch):
    discord=pytest.importorskip("discord")
    from snowfall.ui.social_arcade import (
        ArcadeHubView,ArcadePlayView,ArcadeBoardView,show_arcade,
        show_arcade_session,hub_text,game_text,
    )
    from snowfall.ui.winter_fun import WinterActivitiesView
    from snowfall.ui.navigation import GameMenu
    from snowfall.commands.winter_fun import SnowFunGroup
    from snowfall.ui.today import TodayView

    settings=SimpleNamespace(guild_id=123,season_key=SEASON,mode="production",
                             admin_user_ids=frozenset())
    monkeypatch.setattr("snowfall.ui.social_arcade._now",lambda:START)
    engine=SocialArcadeEngine(game,random.Random(13))
    lobby=engine.lobby(SEASON,101,START)
    assert len(ArcadeHubView(settings,game,101).children)<=25
    assert "Winter Arcade" in {getattr(x,"label","")
                                for x in GameMenu(settings,game,101).children}
    assert "Winter Arcade" in {getattr(x,"label","")
                                for x in WinterActivitiesView(settings,game,101).children}
    assert "arcade" in {c.name for c in SnowFunGroup(settings,game).commands}
    assert "Winter Arcade" in {getattr(x,"label","")
                                for x in TodayView(settings,game,101).children}
    assert "Casual" in hub_text(lobby)
    first=engine.begin(SEASON,101,"gallery",START)
    view=ArcadePlayView(settings,game,101,first)
    options={getattr(x,"label",None) for x in view.children}
    assert len(options.intersection(first.current.choices))==3
    assert "Snowballs" in game_text(first)
    boards=ArcadeBoardView(settings,game,101)
    for v in (view,boards,ArcadeHubView(settings,game,101)):
        assert isinstance(v,discord.ui.View)
        assert all(child.row is None or 0<=child.row<=4 for child in v.children)
        assert len(v.children)<=25

    class FakeInteraction:
        def __init__(self, id=10001):
            self.id=id
            self.user=SimpleNamespace(id=101)
            self.guild_id=123
            self.channel_id=777
            self.client=SimpleNamespace(practice=None)
            self.response=SimpleNamespace(defer=self.defer,send_message=self.send_message)
            self.edits=[]
        async def defer(self,**kwargs):
            pass
        async def send_message(self,*args,**kwargs):
            pass
        async def edit_original_response(self,**kwargs):
            self.edits.append(kwargs)

    async def scenario():
        event=FakeInteraction()
        await show_arcade(event,settings,game,101)
        assert len(event.edits)==1 and event.edits[-1]["attachments"]
        play=FakeInteraction(10002)
        await show_arcade_session(play,settings,game,101,first.session_id)
        assert len(play.edits)==1
        choice_view=play.edits[-1]["view"]
        choose=next(b for b in choice_view.children if getattr(b,"label",None)
                    in first.current.choices)
        await choose.callback(FakeInteraction(10003))
        assert engine.session(SEASON,101,first.session_id,START).step==1
        records=FakeInteraction(10004)
        await show_arcade(records,settings,game,101,screen="passport")
        assert len(records.edits)==1
        board=FakeInteraction(10005)
        await show_arcade(board,settings,game,101,screen="board")
        assert len(board.edits)==1
        assert engine.begin(SEASON,101,"gallery",START).session_id==first.session_id
    asyncio.run(scenario())
