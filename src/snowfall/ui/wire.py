"""Snowfall Wire reader, opt-in story modal and private host editorial desk.

All ordinary navigation edits one owner-checked ephemeral message; submissions
require explicit player consent and must be approved before public publication.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import sqlite3

import discord

from snowfall.graphics import delivery, wire_cards
from snowfall.practice import pin, practice_expired
from snowfall.services.wire import WireEngine, WireError, edition_text
from snowfall.ui.navigation import MenuView, show_home, show_game


def _now():
    return datetime.now(timezone.utc)


def _safe(value, limit=220):
    value=str(value).replace("\n"," ")
    return discord.utils.escape_markdown(value[:limit]).replace("@","＠")


async def show_wire(interaction, settings, store, owner: int, *,
                    day: int | None = None, page="edition", deferred=False, alert=""):
    settings,store=pin(settings,store)
    if not deferred:
        await interaction.response.defer()
    try:
        engine=WireEngine(store)
        latest=await asyncio.to_thread(engine.latest_day,settings.season_key,_now())
        if page=="story":
            story=await asyncio.to_thread(engine.my_story,settings.season_key,owner,_now())
            if story is None:
                body=("📝 **MY PLAYER DISPATCH**\nNo submission on record yet. "
                      "Open **Submit Dispatch** to suggest a story. An organiser "
                      "must approve it before any public use.")
            else:
                body=(f"📝 **MY PLAYER DISPATCH — #{story.id}**\n"
                      f"**Day {story.day}/7 · {_safe(story.status)}**\n"
                      f"**{_safe(story.headline)}**\n{_safe(story.story,500)}\n"
                      "*Host approval is required before public display. "
                      "Once an edition is posted it is not automatically changed.*")
            if alert:
                body+="\n"+_safe(alert)
            await interaction.edit_original_response(
                content=body[:1900],embed=None,attachments=[],
                view=WireReaderView(settings,store,owner,day=day or latest,latest=latest),
                allowed_mentions=discord.AllowedMentions.none())
            return
        if latest==0:
            await interaction.edit_original_response(
                content="🗞️ **THE SNOWFALL WIRE**\nThe inaugural edition opens when "
                        "the host starts the seven-day event.",
                embed=None,attachments=[],
                view=WireReaderView(settings,store,owner,day=0,latest=0),
                allowed_mentions=discord.AllowedMentions.none())
            return
        current=day or latest
        issue=await asyncio.to_thread(engine.edition,settings.season_key,current,_now())
        body=edition_text(issue,practice=getattr(settings,"is_test",False))
        if alert:
            body+="\n"+_safe(alert)
        await delivery.edit_result(
            interaction,body[:1930],WireReaderView(settings,store,owner,
                                                   day=current,latest=latest),
            lambda:wire_cards.edition_card(issue),
            alt=f"Snowfall Wire Day {current}/7 newspaper front page")
    except (WireError,ValueError,sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}",embed=None,attachments=[],
            view=WireReaderView(settings,store,owner,day=day or 0,latest=0),
            allowed_mentions=discord.AllowedMentions.none())


async def send_wire(interaction, settings, store):
    settings,store=pin(settings,store)
    try:
        engine=WireEngine(store)
        latest=await asyncio.to_thread(engine.latest_day,settings.season_key,_now())
        view=WireReaderView(settings,store,interaction.user.id,day=latest,latest=latest)
        if latest==0:
            await interaction.followup.send(
                "🗞️ **The Snowfall Wire** opens after the host starts the event. "
                "Submit an original in-world dispatch after the kickoff.",
                view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
            return
        issue=await asyncio.to_thread(engine.edition,settings.season_key,latest,_now())
        body=edition_text(issue,practice=getattr(settings,"is_test",False))
        try:
            image=await asyncio.to_thread(wire_cards.edition_card,issue)
            embed=discord.Embed(colour=discord.Colour.from_rgb(194,163,111))
            embed.set_image(url="attachment://snowfall-wire.png")
            await interaction.followup.send(
                content=body,file=discord.File(BytesIO(image),filename="snowfall-wire.png",
                    description=f"Day {latest} Snowfall Wire newspaper front page"),
                embed=embed,view=view,ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException,ValueError,OSError,MemoryError):
            await interaction.followup.send(
                content=body,view=view,ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
    except (WireError,sqlite3.Error,ValueError) as exc:
        await interaction.followup.send(f"⚠️ {_safe(exc)}",ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


class StoryModal(discord.ui.Modal,title="Write for the Snowfall Wire"):
    headline=discord.ui.TextInput(
        label="Newspaper headline (8–76 characters)",
        placeholder="The Great Christmas Cookie Caper",
        required=True,min_length=8,max_length=76)
    story=discord.ui.TextInput(
        label="Original MafiaReturns winter dispatch",
        placeholder="Tell a short, fictional, in-world story for readers across the six cities.",
        style=discord.TextStyle.paragraph,required=True,
        min_length=40,max_length=500)
    def __init__(self, settings, store, owner):
        super().__init__(timeout=300)
        self.settings,self.store=pin(settings,store)
        self.owner=owner

    async def interaction_check(self, interaction):
        if (interaction.user.id != self.owner or
            interaction.guild_id != self.settings.guild_id or
            practice_expired(self.settings,self.store)):
            await interaction.response.send_message(
                "This story draft belongs to a different player, server or expired test.",
                ephemeral=True)
            return False
        manager=getattr(interaction.client,"practice",None)
        if manager is not None and self.settings.is_test:
            session=manager.session
            if (session is None or session.id!=self.settings.session_id
                or session.channel_id!=interaction.channel_id):
                await interaction.response.send_message(
                    "That test day ended. Open the latest Wire menu.",
                    ephemeral=True)
                return False
        return True

    async def on_submit(self,interaction):
        try:
            result=await asyncio.to_thread(
                WireEngine(self.store).submit,self.settings.season_key,
                self.owner,str(self.headline.value),str(self.story.value),_now())
            await interaction.response.send_message(
                f"🗞️ **Dispatch #{result.id} submitted** for Day {result.day}. "
                "**Pending host review.** The public Wire will not print it "
                "until a configured host approves it. Your story grants no prizes.",
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except (WireError,ValueError,sqlite3.Error) as exc:
            await interaction.response.send_message(
                f"⚠️ {_safe(exc)}",ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())


class WireReaderView(MenuView):
    def __init__(self,settings,store,owner,*,day=0,latest=0):
        super().__init__(settings,store,owner)
        self.day,self.latest=day,latest
        options=[discord.SelectOption(label=f"Day {i}/7 — Wire Edition",value=str(i),
                    default=i==day) for i in range(1,latest+1)]
        if options:
            select=discord.ui.Select(placeholder="Browse past Wire editions",
                                     options=options,row=0)
            async def choose(interaction):
                await show_wire(interaction,self.settings,self.store,
                                self.owner_id,day=int(select.values[0]))
            select.callback=choose
            self.add_item(select)

    @discord.ui.button(label="Latest Wire",emoji="🗞️",style=discord.ButtonStyle.primary,row=1)
    async def latest_issue(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Previous Day",emoji="◀️",style=discord.ButtonStyle.secondary,row=1)
    async def previous(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id,
                        day=max(1,self.day-1))

    @discord.ui.button(label="Next Day",emoji="▶️",style=discord.ButtonStyle.secondary,row=1)
    async def next(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id,
                        day=min(max(1,self.latest),self.day+1))

    @discord.ui.button(label="Submit Dispatch",emoji="✍️",style=discord.ButtonStyle.success,row=2)
    async def submit(self,interaction,_):
        await interaction.response.send_modal(
            StoryModal(self.settings,self.store,self.owner_id))

    @discord.ui.button(label="My Story",emoji="📜",style=discord.ButtonStyle.secondary,row=2)
    async def my_story(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id,
                        day=self.day,page="story")

    @discord.ui.button(label="City HQ",emoji="🏙️",style=discord.ButtonStyle.secondary,row=2)
    async def city(self,interaction,_):
        from snowfall.ui.community import show_city
        await show_city(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Game Menus",emoji="🎮",style=discord.ButtonStyle.secondary,row=3)
    async def game(self,interaction,_):
        await show_game(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Home",emoji="🏠",style=discord.ButtonStyle.secondary,row=3)
    async def home(self,interaction,_):
        await show_home(interaction,self.settings,self.store,self.owner_id)
