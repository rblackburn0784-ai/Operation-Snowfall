"""v0.2.8 newsroom: opt-in, approval, factual reports and restart-safe broadcast."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import sqlite3
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.services.wire import (
    WireEngine, WireError, HEADLINES, MAX_STORIES, clean_name, edition_text,
)
from snowfall.graphics.wire_cards import edition_card, flash_card
from snowfall.services.world import WorldEngine

START=datetime(2026,12,20,19,tzinfo=timezone.utc)
SEASON="snowfall-wire-v028"
HOSTS=frozenset({900})


@pytest.fixture
def game(tmp_path):
    db=Store(tmp_path/"wire.db")
    db.initialize()
    db.ensure_season(SEASON,START)
    for uid,name,city in ((101,"TheDude","Chicago"),
                          (102,"FrostFox","Chicago"),
                          (201,"Blizzard Joe","New York"),
                          (301,"YuleAce","Detroit")):
        db.register(SEASON,uid,name,city,START-timedelta(days=1))
    db.transition(SEASON,900,"start",START,"wire event start")
    WorldEngine(db).tick(SEASON,START)
    return db


def _official(db):
    with db.connect() as con:
        names=("score_ledger","combat_events","pve_events","quest_claims",
               "mystery_gifts","prize_awards","player_resources","item_events",
               "social_arcade_runs","social_arcade_stamps")
        return tuple(con.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]
                     for table in names)


def _image(payload):
    assert payload.startswith(b"\x89PNG") and len(payload)<2_500_000
    with Image.open(BytesIO(payload)) as im:
        assert im.size==(960,540)


def _story(engine,uid,now=START):
    return engine.submit(
        SEASON,uid,f"Festive dispatch from player {uid}",
        "An icy city night has sent the snowball crews down to the old speakeasy, "
        "where the street lamps flicker and the Christmas bell chimes.",
        now)


def _throws(db,qty=10):
    with db.connect() as con:
        for i in range(qty):
            con.execute("""INSERT INTO combat_events(
                interaction_id,season_key,day,attacker_id,target_id,target_city,style,
                happened_at_utc,effective_at_utc,hit,critical,hit_roll,
                armour_damage,warmth_damage,knocked_out,points_awarded,
                bonus_city,bonus_ko,defense_points)
                VALUES (?,?,1,101,201,'New York','quick',?,?,0,0,0.9,
                    0,0,0,0,0,0,0)""",
                (f"wire-throw-{i}",SEASON,START.isoformat(),START.isoformat()))


def test_seven_distinct_pages_factual_copy_and_no_hidden_future(game):
    engine=WireEngine(game)
    assert len(HEADLINES)==7 and len(set(HEADLINES))==7
    assert engine.latest_day(SEASON,START-timedelta(days=1))==0
    with pytest.raises(WireError,match="not opened"):
        engine.edition(SEASON,1,START-timedelta(days=1))
    with pytest.raises(WireError,match="not opened"):
        engine.edition(SEASON,2,START)
    first=engine.edition(SEASON,1,START)
    assert not first.completed and first.phase=="live"
    assert first.throws==first.hits==first.arcade_runs==0
    assert first.top_player is None and first.busy_city is None
    assert "No city qualified" in edition_text(first)
    assert "DAY 1/7" in edition_text(first)
    assert "individual only" in edition_text(first)
    _image(edition_card(first))
    _image(flash_card(1,"STREETS ARE BUZZING",10))
    assert engine.latest_day(SEASON,START+timedelta(days=7))==7
    for day in range(1,8):
        now=START+timedelta(days=day)
        issue=engine.edition(SEASON,day,now)
        assert issue.day==day and issue.completed
        assert HEADLINES[day-1] in edition_text(issue)
        _image(edition_card(issue))


def test_submission_requires_opt_in_and_never_exposes_pending(game):
    engine=WireEngine(game)
    before=_official(game)
    pending=_story(engine,101)
    assert pending.status=="pending" and pending.id>0
    assert engine.my_story(SEASON,101,START)==pending
    assert engine.edition(SEASON,1,START).stories==()
    assert len(engine.queue(SEASON))==1
    assert engine.queue(SEASON)[0].id==pending.id
    assert _story(engine,101).id==pending.id
    with pytest.raises(WireError,match="already been"):
        engine.submit(SEASON,101,"Totally different headline",
                      "Another draft that is long enough to meet the minimum length.",
                      START)
    with pytest.raises(WireError,match="8"):
        engine.submit(SEASON,201,"x","A"*55,START)
    with pytest.raises(WireError,match="40"):
        engine.submit(SEASON,201,"A good headline","too short",START)
    with pytest.raises(WireError,match="No links"):
        engine.submit(SEASON,201,"A good headline","Our winter dispatch "
                      "saw the crowds at https://spam.example/somewhere "
                      "around the clock.",START)
    with pytest.raises(WireError,match="No links"):
        engine.submit(SEASON,201,"A good headline",
                      "Our winter dispatch warned @everyone about "
                      "the continuing snowball rivalries.",START)
    assert _official(game)==before


def test_editor_only_review_one_way_and_public_edition(game):
    engine=WireEngine(game)
    prior=_official(game)
    story=_story(engine,101)
    with pytest.raises(WireError,match="configured"):
        engine.review(SEASON,story.id,"approved",101,HOSTS,START)
    with pytest.raises(WireError,match="Choose"):
        engine.review(SEASON,story.id,"pending",900,HOSTS,START)
    with pytest.raises(WireError,match="not found"):
        engine.review(SEASON,99999,"approved",900,HOSTS,START)
    approved=engine.review(SEASON,story.id,"approved",900,HOSTS,START)
    assert approved.status=="approved"
    with pytest.raises(WireError,match="already"):
        engine.review(SEASON,story.id,"rejected",900,HOSTS,START)
    published=engine.edition(SEASON,1,START)
    assert len(published.stories)==1 and published.stories[0].byline=="TheDude"
    body=edition_text(published)
    assert "PLAYER DISPATCH" in body and "opt-in" in body
    assert "Festive dispatch" in body
    assert len(body)<2000
    other=_story(engine,201)
    rejected=engine.review(SEASON,other.id,"rejected",900,HOSTS,START)
    assert rejected.status=="rejected"
    assert len(engine.edition(SEASON,1,START).stories)==1
    assert _official(game)==prior
    with game.connect() as con:
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            con.execute("DELETE FROM wire_submissions")
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            con.execute("UPDATE wire_submissions SET story='hacked' WHERE id=?",
                        (approved.id,))


def test_approved_story_visibility_is_limited_and_review_flag_hides(game):
    engine=WireEngine(game)
    for uid in (101,102,201,301):
        item=_story(engine,uid)
        engine.review(SEASON,item.id,"approved",900,HOSTS,START)
    assert len(engine.edition(SEASON,1,START).stories)==MAX_STORIES==2
    game.review(SEASON,900,101,"flagged","Identity check",START)
    edition=engine.edition(SEASON,1,START)
    assert "TheDude" not in [x.byline for x in edition.stories]
    assert "TheDude" not in edition_text(edition)
    with pytest.raises(WireError,match="identity review"):
        engine.submit(SEASON,101,"New winter mystery headline",
                      "A new winter mystery is unfolding by the old clock tower tonight.",START)
    with pytest.raises(WireError,match="identity review"):
        engine.my_story(SEASON,101,START)


def test_parallel_duplicate_submits_one_story_per_user_day(game):
    engine=WireEngine(game)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=list(pool.map(lambda _: _story(engine,101),(1,2)))
    assert a.id==b.id and a.status==b.status=="pending"
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM wire_submissions").fetchone()[0]==1


def test_paused_clock_rejects_submission_and_days_archive(game):
    engine=WireEngine(game)
    _story(engine,101)
    game.transition(SEASON,900,"pause",START+timedelta(hours=2),"Weather break")
    now=START+timedelta(days=4)
    assert engine.latest_day(SEASON,now)==1
    assert engine.edition(SEASON,1,now).phase=="paused"
    with pytest.raises(WireError,match="only during live"):
        _story(engine,201,now)
    with pytest.raises(WireError,match="not opened"):
        engine.edition(SEASON,2,now)
    game.transition(SEASON,900,"resume",now,"Restart the event")
    day2=START+timedelta(days=5,minutes=2)
    s=_story(engine,101,day2)
    assert s.day==2
    assert engine.edition(SEASON,1,day2).completed
    assert engine.edition(SEASON,2,day2).day==2
    with pytest.raises(WireError,match="only during live"):
        _story(engine,201,START+timedelta(days=12))
    assert engine.edition(SEASON,1,START+timedelta(days=12)).completed


def test_read_only_reports_reflect_logged_activity_but_are_not_prize_scores(game):
    engine=WireEngine(game)
    before=_official(game)
    no=engine.flash(SEASON,START)
    assert no is None
    _throws(game,10)
    report=engine.edition(SEASON,1,START)
    assert report.throws==10 and report.hits==0
    flash=engine.flash(SEASON,START)
    assert flash and flash[0]==1 and "10 throws" in flash[1]
    assert engine.flash(SEASON,START+timedelta(days=7)) is None
    assert _official(game)[1]==before[1]+10
    assert _official(game)[0]==before[0]  # No official points added by the Wire.


def test_v10_forward_migration_preserves_legacy_rows(game):
    old=game.get_player(SEASON,101)
    with game.connect() as con:
        con.execute("DROP TABLE wire_submissions")
        con.execute("PRAGMA user_version=10")
    game.initialize()
    game.initialize()
    assert game.schema_version()==11
    assert game.get_player(SEASON,101)==old
    with game.connect() as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0]=="ok"
    assert _story(WireEngine(game),101).id


def test_session_and_user_season_isolation(game,tmp_path):
    engine=WireEngine(game)
    first=_story(engine,101)
    game.ensure_season("separate",START)
    game.register("separate",101,"AltDude","Detroit",START-timedelta(days=1))
    game.transition("separate",900,"start",START,"New event")
    assert engine.queue("separate")==()
    practice=Store(tmp_path/"testday.db")
    practice.initialize()
    practice.ensure_season(SEASON,START)
    practice.register(SEASON,101,"TheDude","Chicago",START-timedelta(days=1))
    practice.transition(SEASON,900,"start",START,"Practice")
    assert WireEngine(practice).queue(SEASON)==()
    assert first.id==engine.queue(SEASON)[0].id


def test_names_and_user_copy_dont_emit_mentions(game):
    engine=WireEngine(game)
    submitted=engine.submit(SEASON,101,"A *winter* _headline_",
                    "A quiet morning saw a visitor named @someone walk into the old "
                    "Chicago speakeasy and leave an unsigned Christmas note.",START)
    engine.review(SEASON,submitted.id,"approved",900,HOSTS,START)
    body=edition_text(engine.edition(SEASON,1,START))
    assert "@someone" not in body
    assert "*winter*" not in body
    assert "＠someone" in body
    assert clean_name("@everyone")== "＠everyone"


def test_discord_reader_permissions_and_host_editor_contract(game):
    discord=pytest.importorskip("discord")
    from snowfall.ui.wire import WireReaderView,StoryModal
    from snowfall.ui.wire_admin import WireDeskView,WireReviewView
    from snowfall.ui.navigation import GameMenu,AdminPanel
    from snowfall.ui.winter_fun import WinterActivitiesView
    from snowfall.commands.wire_admin import SnowWireAdminGroup
    from snowfall.commands.winter_fun import SnowFunGroup
    settings=SimpleNamespace(guild_id=123,season_key=SEASON,mode="production",
                             admin_user_ids=HOSTS,staff_role_ids=frozenset())
    assert "wire" in {c.name for c in SnowFunGroup(settings,game).commands}
    editor=SnowWireAdminGroup(settings,game)
    assert {c.name for c in editor.commands} == {
        "desk","queue","review","preview","publish","flash"}
    assert "Snowfall Wire" in {getattr(c,"label","") for c in GameMenu(settings,game,101).children}
    assert "Snowfall Wire" in {getattr(c,"label","")
                               for c in WinterActivitiesView(settings,game,101).children}
    assert "Wire Editorial" in {getattr(c,"label","")
                                for c in AdminPanel(settings,game,900).children}
    reader=WireReaderView(settings,game,101,day=1,latest=7)
    assert reader.owner_id==101
    assert isinstance(StoryModal(settings,game,101),discord.ui.Modal)
    pending=_story(WireEngine(game),101)
    desk=WireDeskView(settings,game,900,(pending,))
    review=WireReviewView(settings,game,900,pending.id)
    assert review.host_only and desk.host_only
    for view in (reader,desk,review):
        assert len(view.children)<=25
        assert all(child.row is None or 0<=child.row<=4 for child in view.children)
        counts={}
        for child in view.children:
            if child.row is not None:
                counts[child.row]=counts.get(child.row,0)+1
        assert all(n<=5 for n in counts.values())


def test_gateway_fake_no_duplicate_day_issues_and_explicit_refresh(game,tmp_path):
    from snowfall.config import Settings
    from snowfall.ui.broadcast import BroadcastPublisher

    class Msg:
        def __init__(self,channel,index,content):
            self.channel,self.id,self.content=channel,index,content
            self.author=SimpleNamespace(id=9999)
            self.embeds=[]
            self.edits=0
            self.jump_url=f"https://example.invalid/{index}"
        async def edit(self,content=None,**kwargs):
            self.content=content
            self.edits+=1
            return self

    class Channel:
        id=77772
        guild=SimpleNamespace(id=123)
        def __init__(self):
            self.messages={}
            self.sends=0
        async def send(self,content=None,**kwargs):
            self.sends+=1
            m=Msg(self,100+self.sends,content)
            self.messages[m.id]=m
            return m
        async def fetch_message(self,id):
            return self.messages[id]
        async def history(self,limit=100):
            for msg in list(self.messages.values())[::-1]:
                yield msg

    class Bot:
        user=SimpleNamespace(id=9999)
        def __init__(self,channel):
            self.channel=channel
        def get_channel(self,id):
            return self.channel if id==self.channel.id else None

    settings=Settings("FAKE",123,HOSTS,SEASON,
                      "Operation Snowfall",START,game.path,
                      announcement_channel_id=77772)
    channel=Channel()
    bot=Bot(channel)
    publisher=BroadcastPublisher(bot,settings,game)

    async def scenario():
        assert await publisher.publish_wire_recaps(START+timedelta(hours=23)) is None
        issue=await publisher.publish_wire_recaps(START+timedelta(days=1))
        assert channel.sends==1 and "DAY 1/7" in issue.content
        assert "Snowfall marker:" in issue.content
        # The player must submit on a live day; already closed Day 1 is immutable.
        # The fixture's event clock remains live at START for controlled approval.
        story=_story(WireEngine(game),101)
        WireEngine(game).review(SEASON,story.id,"approved",900,HOSTS,START)
        existing=await publisher.publish_wire_issue(START+timedelta(days=1),1)
        assert existing.id==issue.id and channel.sends==1 and issue.edits==0
        changed=await publisher.publish_wire_issue(START+timedelta(days=1),1,
                                                   refresh_existing=True)
        assert changed.id==issue.id and issue.edits==1
        assert "PLAYER DISPATCH" in changed.content
        restarted=BroadcastPublisher(bot,settings,game)
        assert await restarted.publish_wire_recaps(START+timedelta(days=1)) is None
        assert channel.sends==1
        assert await publisher.publish_wire_flash(START) is None
        _throws(game,10)
        flash=await publisher.publish_wire_flash(START)
        assert flash is not None and channel.sends==2
        assert await publisher.publish_wire_flash(START) is None
        assert await restarted.publish_wire_flash(START) is None
        assert channel.sends==2
        assert await publisher.publish_wire_recaps(START+timedelta(days=2)) is not None
        assert channel.sends==3
        test_settings=replace(settings,mode="practice")
        private=BroadcastPublisher(bot,test_settings,game)
        with pytest.raises(ValueError,match="disabled"):
            await private.publish_wire_issue(START,1)
        assert await private.publish_wire_flash(START) is None
        assert await private.publish_wire_recaps(START+timedelta(days=1)) is None
    asyncio.run(scenario())
