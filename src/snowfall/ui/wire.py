"""Private, owner-checked Snowfall Wire newsroom and host-moderated letters."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import sqlite3

import discord

from snowfall.graphics import delivery, wire_cards
from snowfall.practice import pin
from snowfall.services.wire import WireEngine, WireError, story_caption
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now():
    return datetime.now(timezone.utc)


def _safe(value, limit=200):
    return discord.utils.escape_markdown(str(value).replace("@","＠")[:limit])


def _hosts(settings):
    return getattr(settings,"admin_user_ids",frozenset())


def newsroom_text(info, alert=""):
    lines=["🗞️ **THE SNOWFALL WIRE 2.0 — NEWSROOM**",
           "*America's coldest underworld dispatch. Verified statistics and labelled player fiction.*",
           f"**Phase:** {info.phase.upper()} · **Day:** {info.day or '—'}/7 "
           f"· **Completed editions:** {info.last_completed}/7",
           f"**Approved player letters:** {info.approved_stories} "
           f"· **Awaiting editorial review:** {info.pending_stories}",
           "**LATEST VERIFIED DISPATCHES**"]
    for h in info.recent:
        lines.append(f"• **{_safe(h.title,90)}** — {_safe(h.detail,120)}")
    if info.my_story:
        lines.append(f"✉️ **Your last letter (Day {info.my_story.day}):** "
                     f"{_safe(info.my_story.title)} · **{info.my_story.status.upper()}**")
    else:
        lines.append("✉️ No letter submitted yet. You may submit one per live event day.")
    lines.append("Choose a day from the Archive, browse approved letters, or submit "
                 "a 1930s Christmas mob story for host review. No prizes or extra points.")
    if alert:
        lines.append(f"\n**{_safe(alert,350)}**")
    return "\n".join(lines)[:1940]


def edition_text(edition, alert=""):
    state="LOCKED RESULTS" if edition.complete else "LIVE — UNOFFICIAL FIGURES"
    lines=[f"🗞️ **THE SNOWFALL WIRE — DAY {edition.day}/7**",
           f"**{_safe(edition.theme)}** · {state}",
           "*Reported from actual game records. Live numbers may change.*"]
    for headline in edition.verified:
        lines.append(f"**{headline.category}: {_safe(headline.title,110)}** — "
                     f"{_safe(headline.detail,140)}")
    if edition.stories:
        lines.append("✉️ **APPROVED PLAYER ROLEPLAY**")
        for story in edition.stories[:3]:
            lines.append(f"• {_safe(story.title,80)} — {_safe(story.author,45)} "
                         f"({_safe(story.city,45)})")
    lines.append("Use **Read Full Recap** to see the existing end-of-day ledger report. "
                 "Official individual prizes are unchanged.")
    if alert:
        lines.append(f"\n**{_safe(alert)}**")
    return "\n".join(lines)[:1950]


def stories_text(stories):
    lines=["✉️ **LETTERS TO THE EDITOR**",
           "*Approved fictional community stories only — not verified results.*"]
    if not stories:
        lines.append("No approved submissions yet. Stories need a host's approval.")
    for story in stories[:8]:
        lines.append(f"**#{story.id} · Day {story.day}: {_safe(story.title,80)}** "
                     f"by {_safe(story.author,45)} · {_safe(story.city,45)}")
    lines.append("Select a letter to read it privately.")
    return "\n".join(lines)[:1900]


async def show_wire(interaction,settings,store,owner,*,page="home",day=None,
                    deferred=False,alert=""):
    settings,store=pin(settings,store)
    if not deferred:
        await interaction.response.defer()
    engine=WireEngine(store)
    try:
        if page=="home":
            news=await asyncio.to_thread(engine.newsroom,settings.season_key,owner,_now())
            msg=newsroom_text(news,alert)
            view=WireView(settings,store,owner,news)
            def art():
                return wire_cards.wire_front_card(newsroom=news)
        elif page=="edition":
            edition=await asyncio.to_thread(engine.edition,settings.season_key,
                                            owner,day,_now())
            msg=edition_text(edition,alert)
            view=EditionView(settings,store,owner,edition)
            def art():
                return wire_cards.wire_front_card(edition=edition)
        elif page=="stories":
            stories=await asyncio.to_thread(engine.stories,settings.season_key,
                                            owner,_now(),day=day)
            msg=stories_text(stories)
            view=StoryListView(settings,store,owner,stories)
            def art():
                return wire_cards.wire_stories_card(stories)
        elif page=="moderation":
            if owner not in _hosts(settings):
                raise WireError("Host access required.")
            stories=await asyncio.to_thread(engine.pending,settings.season_key,
                                            owner,_now(),hosts=_hosts(settings))
            msg=("📰 **EDITORIAL DESK — PENDING LETTERS**\n"
                 "Only configured hosts can approve these fictional submissions.\n"
                 + ("\n".join(f"**#{s.id}** · Day {s.day} · "
                              f"{_safe(s.author,40)}: {_safe(s.title,80)}"
                              for s in stories) if stories else
                    "No letters currently await review."))
            view=ModerationListView(settings,store,owner,stories)
            def art():
                return wire_cards.wire_stories_card(stories)
        else:
            raise WireError("Unknown newspaper page.")
        await delivery.edit_result(interaction,msg,view,art,
                                   alt="Illustrated 1930s Snowfall Wire Christmas newspaper")
    except (WireError,ValueError,sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}",embed=None,attachments=[],
            view=WireBackView(settings,store,owner),
            allowed_mentions=discord.AllowedMentions.none())


async def send_wire(interaction,settings,store):
    """Already-deferred ephemeral slash entry."""
    settings,store=pin(settings,store)
    try:
        news=await asyncio.to_thread(WireEngine(store).newsroom,
                                     settings.season_key,interaction.user.id,_now())
    except (WireError,ValueError,sqlite3.Error) as exc:
        await interaction.followup.send(f"⚠️ {_safe(exc)}",ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
        return
    msg=newsroom_text(news)
    view=WireView(settings,store,interaction.user.id,news)
    try:
        png=await asyncio.to_thread(wire_cards.wire_front_card,newsroom=news)
        embed=discord.Embed(colour=0xAA8B64)
        embed.set_image(url="attachment://snowfall-wire.png")
        await interaction.followup.send(
            content=msg,embed=embed,view=view,ephemeral=True,
            file=discord.File(BytesIO(png),filename="snowfall-wire.png",
                              description="Illustrated Snowfall Wire newsroom"),
            allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException,OSError,ValueError,MemoryError):
        await interaction.followup.send(content=msg,view=view,ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


class SubmitStory(discord.ui.Modal,title="Letter to The Snowfall Wire"):
    headline=discord.ui.TextInput(label="Your Christmas mob headline",
        placeholder="The Night the Gutter Froze Over",min_length=6,max_length=80,
        style=discord.TextStyle.short,required=True)
    story=discord.ui.TextInput(label="Write a short fictional newspaper story",
        placeholder="The alley outside the speakeasy was silent...",min_length=20,
        max_length=650,style=discord.TextStyle.paragraph,required=True)
    def __init__(self,settings,store,owner):
        super().__init__(timeout=300)
        self.settings,self.store=pin(settings,store)
        self.owner_id=owner

    async def on_submit(self,interaction):
        if interaction.user.id!=self.owner_id or interaction.guild_id!=self.settings.guild_id:
            await interaction.response.send_message("Not your newspaper submission.",
                                                    ephemeral=True)
            return
        from snowfall.platform.discord_security import check_linked_player
        if not await check_linked_player(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            story=await asyncio.to_thread(WireEngine(self.store).submit,
                self.settings.season_key,self.owner_id,str(interaction.id),
                str(self.headline.value),str(self.story.value),_now())
            msg=(f"✉️ Submitted **{_safe(story.title)}** for host review. "
                 "It is private until an editor approves it. "
                 "This cannot change scores, prizes or city rankings.")
        except (WireError,sqlite3.Error,ValueError) as exc:
            msg=f"⚠️ {_safe(exc)}"
        await interaction.followup.send(msg,ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


class WireView(MenuView):
    def __init__(self,settings,store,owner,news=None):
        super().__init__(settings,store,owner)
        select=discord.ui.Select(
            placeholder="📰 Choose a daily newspaper edition",
            options=[discord.SelectOption(
                label=f"Day {day}: {theme[:74]}",value=str(day),
                description="Final edition" if news and day<=news.last_completed
                            else "Live" if news and day==news.day else "Not yet open")
                     for day,theme in enumerate(__import__(
                         "snowfall.services.world",fromlist=["THEMES"]).THEMES,1)],
            row=0)
        async def selected(interaction):
            await show_wire(interaction,self.settings,self.store,self.owner_id,
                            page="edition",day=int(select.values[0]))
        select.callback=selected
        self.add_item(select)

    @discord.ui.button(label="Latest Edition",emoji="🗞️",
                       style=discord.ButtonStyle.primary,row=1)
    async def latest(self,interaction,_):
        news=await asyncio.to_thread(WireEngine(self.store).newsroom,
                                      self.settings.season_key,self.owner_id,_now())
        if not news.day and not news.last_completed:
            await show_wire(interaction,self.settings,self.store,self.owner_id)
        else:
            await show_wire(interaction,self.settings,self.store,self.owner_id,
                            page="edition",day=news.day or news.last_completed)

    @discord.ui.button(label="Player Stories",emoji="✉️",
                       style=discord.ButtonStyle.primary,row=1)
    async def stories(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id,page="stories")

    @discord.ui.button(label="Submit Story",emoji="✍️",
                       style=discord.ButtonStyle.success,row=1)
    async def submit(self,interaction,_):
        await interaction.response.send_modal(
            SubmitStory(self.settings,self.store,self.owner_id))

    @discord.ui.button(label="Editorial Desk",emoji="📰",
                       style=discord.ButtonStyle.secondary,row=1)
    async def moderate(self,interaction,_):
        if self.owner_id not in _hosts(self.settings):
            await interaction.response.send_message("Host access required.",ephemeral=True)
            return
        await show_wire(interaction,self.settings,self.store,self.owner_id,page="moderation")

    @discord.ui.button(label="Refresh Wire",emoji="🔄",
                       style=discord.ButtonStyle.secondary,row=2)
    async def refresh(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Game Menus",emoji="🎮",
                       style=discord.ButtonStyle.secondary,row=2)
    async def games(self,interaction,_):
        await show_game(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Home",emoji="🏠",
                       style=discord.ButtonStyle.secondary,row=2)
    async def home(self,interaction,_):
        await show_home(interaction,self.settings,self.store,self.owner_id)


class WireBackView(MenuView):
    @discord.ui.button(label="Newsroom",emoji="🗞️",
                       style=discord.ButtonStyle.primary)
    async def newsroom(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Game Menus",emoji="🎮",
                       style=discord.ButtonStyle.secondary)
    async def games(self,interaction,_):
        await show_game(interaction,self.settings,self.store,self.owner_id)


class EditionView(WireBackView):
    def __init__(self,settings,store,owner,edition):
        super().__init__(settings,store,owner)
        self.edition=edition

    @discord.ui.button(label="Read Full Recap",emoji="📜",
                       style=discord.ButtonStyle.primary,row=1)
    async def recap(self,interaction,_):
        if not self.edition.complete:
            await interaction.response.send_message(
                "Final daily recap is available only after the day closes.",ephemeral=True)
            return
        await interaction.response.edit_message(
            content=self.edition.report_text[:1900],
            embed=None,attachments=[],
            view=EditionView(self.settings,self.store,self.owner_id,self.edition),
            allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Approved Letters",emoji="✉️",
                       style=discord.ButtonStyle.secondary,row=1)
    async def letters(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id,
                        page="stories",day=self.edition.day)


class StoryListView(WireBackView):
    def __init__(self,settings,store,owner,stories):
        super().__init__(settings,store,owner)
        if stories:
            select=discord.ui.Select(placeholder="Read an approved player letter",
                options=[discord.SelectOption(
                    label=f"Day {s.day}: {s.title[:65]}",value=str(s.id))
                    for s in stories[:25]],row=1)
            async def selected(interaction):
                chosen=next((s for s in stories if str(s.id)==select.values[0]),None)
                if chosen is None:
                    await interaction.response.send_message("Letter not found.",ephemeral=True)
                    return
                await interaction.response.edit_message(
                    content=story_caption(chosen),embed=None,attachments=[],
                    view=WireBackView(self.settings,self.store,self.owner_id),
                    allowed_mentions=discord.AllowedMentions.none())
            select.callback=selected
            self.add_item(select)


class ModerationListView(WireBackView):
    def __init__(self,settings,store,owner,stories):
        super().__init__(settings,store,owner,host_only=True)
        if stories:
            select=discord.ui.Select(placeholder="Review a pending letter",
                options=[discord.SelectOption(
                    label=f"#{s.id} · {s.title[:65]}",value=str(s.id))
                    for s in stories[:25]],row=1)
            async def selected(interaction):
                chosen=next((s for s in stories if str(s.id)==select.values[0]),None)
                if chosen:
                    await interaction.response.edit_message(
                        content=story_caption(chosen)
                                + "\n\n**Editorial status: PENDING HOST REVIEW**",
                        embed=None,attachments=[],
                        view=ModerationConfirm(self.settings,self.store,self.owner_id,chosen),
                        allowed_mentions=discord.AllowedMentions.none())
            select.callback=selected
            self.add_item(select)


class ModerationConfirm(WireBackView):
    def __init__(self,settings,store,owner,story):
        super().__init__(settings,store,owner,host_only=True)
        self.story=story

    async def decision(self,interaction,verdict):
        await interaction.response.defer()
        try:
            result=await asyncio.to_thread(WireEngine(self.store).decide,
                self.settings.season_key,self.owner_id,self.story.id,verdict,_now(),
                hosts=_hosts(self.settings))
            msg=f"Editorial decision saved: #{result.id} — {result.status.upper()}."
        except (WireError,sqlite3.Error,ValueError) as exc:
            msg=f"⚠️ {_safe(exc)}"
        await show_wire(interaction,self.settings,self.store,self.owner_id,
                        page="moderation",deferred=True,alert=msg)

    @discord.ui.button(label="Approve Story",emoji="✅",
                       style=discord.ButtonStyle.success,row=1)
    async def approve(self,interaction,_):
        await self.decision(interaction,"approved")

    @discord.ui.button(label="Reject Story",emoji="❌",
                       style=discord.ButtonStyle.danger,row=1)
    async def reject(self,interaction,_):
        await self.decision(interaction,"rejected")
