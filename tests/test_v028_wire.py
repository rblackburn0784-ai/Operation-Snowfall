"""v0.2.8 The Snowfall Wire: verified facts, moderated stories and broadcasts."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
import sqlite3
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.services.wire import WireEngine, WireError, publication_text, story_caption
from snowfall.graphics.wire_cards import wire_front_card, wire_stories_card
from snowfall.services.world import WorldEngine

START=datetime(2026,12,20,19,tzinfo=timezone.utc)
KEY="snowfall-wire-v2"
HOSTS=frozenset({900})


@pytest.fixture
def game(tmp_path):
    db=Store(tmp_path/"wire.db")
    db.initialize()
    db.ensure_season(KEY,START)
    for uid,name,city in ((101,"ChicagoDude","Chicago"),
                          (102,"Jago","Chicago"),
                          (201,"NewYorkKid","New York")):
        db.register(KEY,uid,name,city,START-timedelta(days=1))
    db.transition(KEY,900,"start",START,"Start Christmas news")
    WorldEngine(db).tick(KEY,START)
    return db


def counts(db):
    with db.connect() as con:
        return tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("score_ledger","combat_events","pve_events",
                                   "prize_awards","player_resources","item_events",
                                   "cosmetic_unlocks","social_arcade_stamps",
                                   "wire_submissions","wire_decisions"))


def check_png(raw):
    assert raw[:8]==b"\x89PNG\r\n\x1a\n" and len(raw)<3_000_000
    with Image.open(BytesIO(raw)) as picture:
        assert picture.size==(960,540)


def submit(engine,uid=101,event="story-one",now=START,
           title="The Case of the Lost Christmas Rum",
           body="The mobsters gathered by the alley door to find the missing barrel."):
    return engine.submit(KEY,uid,event,title,body,now)


def test_newsroom_factual_headlines_and_no_invented_activity(game):
    wire=WireEngine(game)
    before=counts(game)
    snap=wire.newsroom(KEY,101,START)
    assert snap.day==1 and snap.last_completed==0 and snap.approved_stories==0
    assert snap.phase=="live" and len(snap.recent)==5
    assert "No eligible" in snap.recent[0].detail
    assert "0 throws" in snap.recent[1].detail
    check_png(wire_front_card(newsroom=snap))
    check_png(wire_stories_card(()))
    with pytest.raises(WireError,match="has not opened"):
        wire.edition(KEY,101,2,START)
    current=wire.edition(KEY,101,1,START)
    assert not current.complete and len(current.verified)==5
    assert "LIVE DISPATCH" in current.report_text
    check_png(wire_front_card(edition=current))
    with pytest.raises(WireError,match="Only completed"):
        publication_text(current)
    assert counts(game)==before


def test_private_submission_approval_and_public_read(game):
    wire=WireEngine(game)
    baseline=counts(game)
    sent=submit(wire)
    assert sent.status=="pending" and sent.day==1
    assert sent.title.startswith("The Case")
    assert wire.newsroom(KEY,101,START).pending_stories==1
    assert not wire.stories(KEY,201,START)
    assert not wire.public_stories(KEY,1)
    assert len(wire.pending(KEY,900,START,hosts=HOSTS))==1
    assert wire.newsroom(KEY,101,START).my_story.status=="pending"
    with pytest.raises(WireError,match="hosts"):
        wire.pending(KEY,201,START,hosts=HOSTS)
    with pytest.raises(WireError,match="hosts"):
        wire.decide(KEY,201,sent.id,"approved",START,hosts=HOSTS)
    approved=wire.decide(KEY,900,sent.id,"approved",START,hosts=HOSTS)
    assert approved.status=="approved"
    assert wire.decide(KEY,900,sent.id,"approved",START,hosts=HOSTS)==approved
    with pytest.raises(WireError,match="already"):
        wire.decide(KEY,900,sent.id,"rejected",START,hosts=HOSTS)
    assert [x.id for x in wire.stories(KEY,201,START)]==[sent.id]
    assert [x.id for x in wire.public_stories(KEY,1)]==[sent.id]
    assert "COMMUNITY ROLEPLAY" in story_caption(approved)
    assert "not a verified event" in story_caption(approved)
    assert wire.newsroom(KEY,101,START).approved_stories==1
    after=counts(game)
    assert after[:-2]==baseline[:-2]
    assert after[-2:]==(1,1)
    check_png(wire_stories_card(wire.stories(KEY,101,START)))


def test_rejected_and_reviewed_identity_never_public(game):
    wire=WireEngine(game)
    story=submit(wire)
    assert wire.decide(KEY,900,story.id,"rejected",START,hosts=HOSTS).status=="rejected"
    assert not wire.public_stories(KEY,1)
    with pytest.raises(WireError,match="already"):
        wire.decide(KEY,900,story.id,"approved",START,hosts=HOSTS)
    other=submit(wire,uid=201,event="other-story")
    wire.decide(KEY,900,other.id,"approved",START,hosts=HOSTS)
    assert len(wire.public_stories(KEY,1))==1
    game.review(KEY,900,201,"flagged","Account under review",START)
    assert wire.public_stories(KEY,1)==()
    with pytest.raises(WireError,match="identity review"):
        wire.submit(KEY,201,"flagged-story","The Snowfall Tale",
                    "The snow reached the windows of the shop.",START)
    with pytest.raises(WireError,match="identity review"):
        wire.newsroom(KEY,201,START)


def test_submission_idempotence_no_double_story_and_disallows_injection(game):
    wire=WireEngine(game)
    first=submit(wire)
    assert submit(wire)==first
    with pytest.raises(WireError,match="another submission"):
        submit(wire,event="story-one",uid=102)
    with pytest.raises(WireError,match="One submitted story"):
        submit(wire,event="new-interaction")
    with pytest.raises(WireError,match="6–80"):
        submit(wire,uid=102,event="tiny",title="x")
    with pytest.raises(WireError,match="external links"):
        submit(wire,uid=102,event="link",body="Find my very big news at https://example.org now!")
    cleaned=submit(wire,uid=102,event="escaped",title="@everyone *Special* Gutter Dispatch",
                   body="Here is some @here <@123> backalley news! Merry Christmas everybody.")
    assert "@" not in cleaned.title and "<@" not in cleaned.body
    assert "*" not in cleaned.title and "@here" not in cleaned.body
    assert len(wire.pending(KEY,900,START,hosts=HOSTS))==2
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM wire_submissions").fetchone()[0]==2


def test_concurrent_submissions_only_one_acceptance(game):
    wire=WireEngine(game)
    def attempt(i):
        try:
            return submit(wire,event=f"parallel-{i}")
        except WireError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,(1,2)))
    assert sum(isinstance(x,Exception) for x in results)==1
    assert len(wire.pending(KEY,900,START,hosts=HOSTS))==1


def test_schema_migration_is_immutable_idempotent_and_restart_safe(game):
    wire=WireEngine(game)
    story=submit(wire)
    wire.decide(KEY,900,story.id,"approved",START,hosts=HOSTS)
    reopened=Store(game.path)
    reopened.initialize()
    assert reopened.schema_version()==11
    assert WireEngine(reopened).public_stories(KEY,1)[0].id==story.id
    with reopened.connect() as con:
        for table in ("wire_submissions","wire_decisions"):
            with pytest.raises(sqlite3.IntegrityError,match="immutable"):
                con.execute(f"DELETE FROM {table}")
            with pytest.raises(sqlite3.IntegrityError,match="immutable"):
                con.execute(f"UPDATE {table} SET season_key='hacked'")
    with reopened.connect() as con:
        con.execute("DROP TABLE wire_decisions")
        con.execute("DROP TABLE wire_submissions")
        con.execute("PRAGMA user_version=10")
        player_count=con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    reopened.initialize()
    reopened.initialize()
    assert reopened.schema_version()==11
    with reopened.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0]==player_count
        assert con.execute("PRAGMA quick_check").fetchone()[0]=="ok"


def test_edition_completes_next_day_and_publication_is_bounded(game):
    wire=WireEngine(game)
    s=submit(wire)
    wire.decide(KEY,900,s.id,"approved",START,hosts=HOSTS)
    later=START+timedelta(days=1,minutes=2)
    final=wire.edition(KEY,101,1,later)
    assert final.complete and final.stories[0].id==s.id
    text=publication_text(final)
    assert "SNOWFALL WIRE 2.0" in text
    assert "APPROVED COMMUNITY FICTION" in text
    assert "ChicagoDude" in text
    assert len(text)<=1880 and "@everyone" not in text
    assert wire.newsroom(KEY,101,later).last_completed==1
    assert not wire.edition(KEY,101,2,later).complete
    with pytest.raises(WireError,match="Choose an edition"):
        wire.edition(KEY,101,8,later)
    # Existing daily recap remains readable and still authoritative.
    assert "DAY 1" in final.report_text
    check_png(wire_front_card(edition=final))


def test_submissions_pause_day_limit_and_closed_archive(game):
    wire=WireEngine(game)
    submit(wire)
    game.transition(KEY,900,"pause",START+timedelta(hours=1),"Maintenance")
    paused=START+timedelta(days=4)
    assert wire.newsroom(KEY,101,paused).day==1
    with pytest.raises(WireError,match="live"):
        submit(wire,uid=201,event="paused",now=paused)
    game.transition(KEY,900,"resume",paused,"Resume event")
    second=START+timedelta(days=5,minutes=1)
    new=submit(wire,uid=101,event="day2",now=second)
    assert new.day==2
    assert len(wire.pending(KEY,900,second,hosts=HOSTS))==2
    end=START+timedelta(days=12)
    assert wire.newsroom(KEY,101,end).phase=="closed"
    with pytest.raises(WireError,match="live"):
        submit(wire,uid=201,event="late",now=end)
    assert wire.edition(KEY,101,1,end).complete


def test_daily_stats_come_from_authoritative_ledgers_only(game):
    wire=WireEngine(game)
    with game.connect() as con:
        con.execute("""INSERT INTO score_ledger(
            season_key,day,player_id,city,category,points,source_key,created_at_utc)
            VALUES(?,1,101,'Chicago','quest',20,'test:ledger',?)""",
            (KEY,START.isoformat()))
    h=wire.headlines(KEY,1)
    assert "ChicagoDude" in h[0].title and "20" in h[0].detail
    assert "0" in h[2].detail
    assert "0 of six" in h[3].detail
    game.review(KEY,900,101,"flagged","Identity issue",START)
    assert "No eligible" in wire.headlines(KEY,1)[0].detail


def test_discord_menu_and_modal_are_owner_checked(game,monkeypatch):
    discord=pytest.importorskip("discord")
    from snowfall.ui.wire import (
        WireView,WireBackView,EditionView,StoryListView,
        ModerationListView,SubmitStory,show_wire,newsroom_text)
    from snowfall.ui.navigation import GameMenu,BroadcastMenu
    from snowfall.ui.winter_fun import WinterActivitiesView
    from snowfall.commands.winter_fun import SnowFunGroup
    settings=SimpleNamespace(guild_id=123,season_key=KEY,mode="production",
                             admin_user_ids=HOSTS)
    monkeypatch.setattr("snowfall.ui.wire._now",lambda:START)
    news=WireEngine(game).newsroom(KEY,101,START)
    edition=WireEngine(game).edition(KEY,101,1,START)
    views=(WireView(settings,game,101,news),WireBackView(settings,game,101),
           EditionView(settings,game,101,edition),StoryListView(settings,game,101,()),
           ModerationListView(settings,game,900,()))
    assert "wire" in {c.name for c in SnowFunGroup(settings,game).commands}
    assert "Snowfall Wire" in {c.label for c in GameMenu(settings,game,101).children}
    assert "Snowfall Wire" in {c.label for c in WinterActivitiesView(settings,game,101).children}
    assert "Publish Latest Wire" in {getattr(c,"label","") for c in
                                    BroadcastMenu(settings,game,900).children}
    assert "THE SNOWFALL WIRE" in newsroom_text(news)
    assert isinstance(SubmitStory(settings,game,101),discord.ui.Modal)
    for v in views:
        assert isinstance(v,discord.ui.View)
        assert len(v.children)<=25
        assert all(c.row is None or 0<=c.row<=4 for c in v.children)
    class Fake:
        def __init__(self):
            self.user=SimpleNamespace(id=101)
            self.guild_id=123
            self.channel_id=777
            self.client=SimpleNamespace(practice=None)
            self.response=SimpleNamespace(defer=self.defer)
            self.edits=[]
        async def defer(self,**kwargs):
            return None
        async def edit_original_response(self,**kwargs):
            self.edits.append(kwargs)
    async def test():
        interaction=Fake()
        await show_wire(interaction,settings,game,101)
        assert len(interaction.edits)==1
        assert interaction.edits[0]["attachments"]
        await show_wire(interaction,settings,game,101,page="edition",day=1)
        assert len(interaction.edits)==2
        assert "DAY 1/7" in interaction.edits[1]["content"]
    asyncio.run(test())


def test_automatic_wire_edition_and_manual_publish_do_not_double_post(game):
    from snowfall.ui.broadcast import BroadcastPublisher

    class FakeMessage:
        def __init__(self, channel, mid, content):
            self.channel,self.id,self.content=channel,mid,content
            self.author=SimpleNamespace(id=9999)
            self.embeds=[]
            self.jump_url=f"https://discord.test/{mid}"
        async def edit(self, *, content=None, embed=None, **kwargs):
            self.content=content
            return self

    class FakeChannel:
        def __init__(self):
            self.id=876543
            self.guild=SimpleNamespace(id=123)
            self.messages={}
            self.sends=0
        async def send(self,content=None,**kwargs):
            self.sends+=1
            m=FakeMessage(self,self.sends,content)
            self.messages[m.id]=m
            return m
        async def fetch_message(self,mid):
            if mid not in self.messages:
                import discord
                raise discord.NotFound(SimpleNamespace(status=404,reason="Not found"),"gone")
            return self.messages[mid]
        async def history(self,limit=100):
            for m in list(self.messages.values())[-limit:][::-1]:
                yield m

    channel=FakeChannel()
    bot=SimpleNamespace(
        user=SimpleNamespace(id=9999),
        get_channel=lambda cid:channel,
        fetch_channel=lambda cid:channel)
    settings=SimpleNamespace(
        season_key=KEY,guild_id=123,announcement_channel_id=channel.id,
        is_test=False)
    publisher=BroadcastPublisher(bot,settings,game)
    story=submit(WireEngine(game))
    WireEngine(game).decide(KEY,900,story.id,"approved",START,hosts=HOSTS)
    later=START+timedelta(days=1,minutes=2)

    async def scenario():
        first=await publisher.publish_wire_recaps(later)
        assert first is not None
        assert channel.sends==1 and "THE SNOWFALL WIRE 2.0" in first.content
        assert "APPROVED COMMUNITY FICTION" in first.content
        assert game.get_published(KEY,"wire_day_1")==(channel.id,first.id)
        assert await publisher.publish_wire_recaps(later) is None
        restarted=BroadcastPublisher(bot,settings,game)
        latest=await restarted.publish_wire_latest(later)
        assert latest.id==first.id and channel.sends==1
        assert game.get_published(KEY,"wire_day_1")==(channel.id,first.id)
        with game.connect() as con:
            con.execute("DELETE FROM published_messages WHERE season_key=? "
                        "AND message_kind='wire_day_1'",(KEY,))
        recovered=await restarted.publish_wire_latest(later)
        assert recovered.id==first.id and channel.sends==1
    asyncio.run(scenario())


def test_host_wire_publisher_refuses_practice_and_unfinished_day(game):
    from snowfall.ui.broadcast import BroadcastPublisher
    settings=SimpleNamespace(
        season_key=KEY,is_test=True,announcement_channel_id=123,
        guild_id=789)
    pub=BroadcastPublisher(SimpleNamespace(),settings,game)
    async def scenario():
        with pytest.raises(ValueError,match="Practice"):
            await pub.publish_wire_latest(START+timedelta(days=1))
        settings.is_test=False
        with pytest.raises(ValueError,match="fully completed"):
            await pub.publish_wire_latest(START)
    asyncio.run(scenario())
