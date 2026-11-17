"""Host-only editorial queue and review controls for Snowfall Wire."""
from __future__ import annotations

import asyncio
from datetime import datetime,timezone
import sqlite3

import discord

from snowfall.practice import pin
from snowfall.services.wire import WireEngine,WireError,clean_name
from snowfall.ui.navigation import MenuView,show_home,show_admin
from snowfall.ui.wire import show_wire


def _now():
    return datetime.now(timezone.utc)


def queue_text(rows, *, alert=""):
    parts=["🗞️ **SNOWFALL WIRE — PRIVATE EDITORIAL DESK**",
           "Only configured hosts can approve stories. Players must opt in "
           "before their own writing appears in a public edition.",
           f"**Pending submissions:** {len(rows)} shown (latest 30)."]
    if not rows:
        parts.append("No player dispatches need review.")
    for story in rows[:8]:
        parts.append(f"**#{story.id} · Day {story.day}/7 · "
                     f"{clean_name(story.headline,70)}**\n"
                     f"By {clean_name(story.byline)} ({clean_name(story.city)}) — "
                     f"{clean_name(story.story,120)}")
    parts.append("\n**PUBLICATION:** Preview with `/snowwireadmin preview`, "
                 "then type `/snowwireadmin publish` and confirmation "
                 "`PUBLISH`. Late-approved articles need `refresh_existing: true`.")
    if alert:
        parts.append(f"\n**{clean_name(alert,220)}**")
    return "\n".join(parts)[:1900]


async def _queue(store,season):
    return await asyncio.to_thread(WireEngine(store).queue,season)


async def show_wire_desk(interaction,settings,store,owner,*,deferred=False,alert=""):
    settings,store=pin(settings,store)
    if not deferred:
        await interaction.response.defer()
    if owner not in settings.admin_user_ids:
        await interaction.edit_original_response(
            content="Only configured hosts can access the Wire editorial desk.",
            embed=None,attachments=[],view=None)
        return
    try:
        rows=await _queue(store,settings.season_key)
        await interaction.edit_original_response(
            content=queue_text(rows,alert=alert),
            embed=None,attachments=[],
            view=WireDeskView(settings,store,owner,rows),
            allowed_mentions=discord.AllowedMentions.none())
    except (WireError,ValueError,sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ Editorial queue error: {clean_name(exc,150)}",
            embed=None,attachments=[],view=WireDeskView(settings,store,owner,()),
            allowed_mentions=discord.AllowedMentions.none())


async def send_wire_desk(interaction,settings,store,owner):
    settings,store=pin(settings,store)
    if owner not in settings.admin_user_ids:
        await interaction.followup.send("Host permission required.",ephemeral=True)
        return
    try:
        rows=await _queue(store,settings.season_key)
        await interaction.followup.send(
            content=queue_text(rows),view=WireDeskView(settings,store,owner,rows),
            ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    except (WireError,ValueError,sqlite3.Error) as exc:
        await interaction.followup.send(
            f"⚠️ {clean_name(exc)}",ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())


class WireDeskView(MenuView):
    def __init__(self,settings,store,owner,rows):
        super().__init__(settings,store,owner,host_only=True,admin_context=True)
        if rows:
            picker=discord.ui.Select(
                placeholder="Choose a pending story for editorial review",
                options=[discord.SelectOption(
                    label=f"#{story.id} · Day {story.day} · "+story.headline[:60],
                    value=str(story.id),
                    description=(clean_name(story.byline,40)+" — "+story.city)[:100])
                    for story in rows[:25]],row=0)
            async def selected(interaction):
                story=next((r for r in rows if r.id==int(picker.values[0])),None)
                if story is None:
                    await show_wire_desk(interaction,self.settings,self.store,self.owner_id,
                                         alert="This story is no longer in the queue.")
                    return
                body=(f"📝 **PRIVATE STORY REVIEW #{story.id}**\n"
                      f"Day {story.day}/7 · {clean_name(story.byline)} ({story.city})\n"
                      f"**{clean_name(story.headline,76)}**\n"
                      f"{clean_name(story.story,500)}\n"
                      "Confirm approve or reject; each submission is reviewed only once.")
                await interaction.response.edit_message(
                    content=body,embed=None,attachments=[],
                    view=WireReviewView(self.settings,self.store,self.owner_id,story.id),
                    allowed_mentions=discord.AllowedMentions.none())
            picker.callback=selected
            self.add_item(picker)

    @discord.ui.button(label="Refresh Queue",emoji="🔄",style=discord.ButtonStyle.primary,row=1)
    async def refresh(self,interaction,_):
        await show_wire_desk(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Preview Latest",emoji="🗞️",style=discord.ButtonStyle.primary,row=1)
    async def preview(self,interaction,_):
        await show_wire(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Publishing Guide",emoji="📣",style=discord.ButtonStyle.secondary,row=1)
    async def publish_help(self,interaction,_):
        await interaction.response.send_message(
            "**Publication requires an explicit host slash command:**\n"
            "`/snowwireadmin publish day:1 confirmation:PUBLISH`\n"
            "For an existing post, use `refresh_existing: true`. "
            "The bot uses your configured announcements channel and never "
            "posts to the disposable Test Centre.",
            ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Admin Panel",emoji="🛠️",style=discord.ButtonStyle.secondary,row=2)
    async def admin(self,interaction,_):
        await show_admin(interaction,self.owner_id)

    @discord.ui.button(label="Home",emoji="🏠",style=discord.ButtonStyle.secondary,row=2)
    async def home(self,interaction,_):
        await show_home(interaction,self.settings,self.store,self.owner_id)


class WireReviewView(MenuView):
    def __init__(self,settings,store,owner,story_id):
        super().__init__(settings,store,owner,host_only=True,admin_context=True)
        self.story_id=story_id

    async def _action(self,interaction,decision):
        await interaction.response.defer()
        try:
            story=await asyncio.to_thread(
                WireEngine(self.store).review,self.settings.season_key,
                self.story_id,decision,self.owner_id,self.settings.admin_user_ids,_now())
            result=f"✅ Story #{story.id} marked {story.status}. Existing public issues were not edited."
        except (WireError,ValueError,sqlite3.Error) as exc:
            result=f"⚠️ {exc}"
        await show_wire_desk(interaction,self.settings,self.store,self.owner_id,
                             deferred=True,alert=result)

    @discord.ui.button(label="Approve Story",emoji="✅",style=discord.ButtonStyle.success)
    async def approve(self,interaction,_):
        await self._action(interaction,"approved")

    @discord.ui.button(label="Reject Story",emoji="✖️",style=discord.ButtonStyle.danger)
    async def reject(self,interaction,_):
        await self._action(interaction,"rejected")

    @discord.ui.button(label="Back to Queue",emoji="↩️",style=discord.ButtonStyle.secondary)
    async def back(self,interaction,_):
        await show_wire_desk(interaction,self.settings,self.store,self.owner_id)
