"""Host-only Wire editorial slash group; separate because /snowadmin is full."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import sqlite3

import discord
from discord import app_commands

from snowfall.core.permissions import permitted_guild, is_host
from snowfall.graphics.wire_cards import edition_card
from snowfall.practice import pin
from snowfall.services.wire import WireEngine, WireError, clean_name, edition_text
from snowfall.ui.broadcast import BroadcastPublisher


def _now():
    return datetime.now(timezone.utc)


class SnowWireAdminGroup(app_commands.Group):
    def __init__(self, settings, store, practice=None):
        super().__init__(name="snowwireadmin",description="Host-only newspaper editorial desk")
        self.settings,self.store,self.practice=settings,store,practice

    async def interaction_check(self,interaction: discord.Interaction)->bool:
        if self.practice is not None:
            self.practice.for_interaction(interaction.channel_id)
        if not permitted_guild(interaction.guild_id,self.settings.guild_id):
            await interaction.response.send_message("Wrong Snowfall server.",ephemeral=True)
            return False
        if not is_host(interaction.user.id,self.settings.admin_user_ids):
            await interaction.response.send_message(
                "Only configured Snowfall hosts may edit or publish the newspaper.",
                ephemeral=True)
            return False
        return True

    @app_commands.command(name="desk",description="Open the private Wire editorial queue")
    async def desk(self,interaction:discord.Interaction):
        from snowfall.ui.wire_admin import send_wire_desk
        await interaction.response.defer(ephemeral=True)
        settings,store=pin(self.settings,self.store)
        await send_wire_desk(interaction,settings,store,interaction.user.id)

    @app_commands.command(name="queue",description="List unapproved player dispatches (private)")
    async def queue(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings,store=pin(self.settings,self.store)
        from snowfall.ui.wire_admin import send_wire_desk
        await send_wire_desk(interaction,settings,store,interaction.user.id)

    @app_commands.command(name="review",description="Approve or reject an opt-in player dispatch by ID")
    @app_commands.choices(decision=[
        app_commands.Choice(name="Approve",value="approved"),
        app_commands.Choice(name="Reject",value="rejected")])
    async def review(self,interaction:discord.Interaction,story_id:int,
                     decision:app_commands.Choice[str]):
        settings,store=pin(self.settings,self.store)
        await interaction.response.defer(ephemeral=True)
        try:
            result=await asyncio.to_thread(
                WireEngine(store).review,settings.season_key,story_id,decision.value,
                interaction.user.id,settings.admin_user_ids,_now())
            await interaction.followup.send(
                f"✅ Editorial decision saved: **Story #{result.id}** "
                f"({_safe(result.headline)}) — **{result.status}**. "
                "An existing published issue will not change until explicitly refreshed.",
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except (WireError,ValueError,sqlite3.Error) as exc:
            await interaction.followup.send(f"⚠️ {_safe(exc)}",ephemeral=True)

    @app_commands.command(name="preview",description="Privately preview a live or archived Wire edition")
    async def preview(self,interaction:discord.Interaction,day:int):
        settings,store=pin(self.settings,self.store)
        await interaction.response.defer(ephemeral=True)
        try:
            issue=await asyncio.to_thread(
                WireEngine(store).edition,settings.season_key,day,_now())
            text=edition_text(issue,practice=settings.is_test)
            image=await asyncio.to_thread(edition_card,issue)
            embed=discord.Embed(colour=discord.Colour.from_rgb(190,163,117))
            embed.set_image(url="attachment://wire-preview.png")
            await interaction.followup.send(
                content="🔒 **EDITORIAL PREVIEW — NOT PUBLISHED**\n"+text,
                embed=embed,file=discord.File(BytesIO(image),filename="wire-preview.png"),
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except (WireError,ValueError,sqlite3.Error,OSError,MemoryError,discord.HTTPException) as exc:
            await interaction.followup.send(
                f"⚠️ Preview unavailable: {_safe(exc)}",ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="publish",description="Post or refresh a Wire issue in the announcement channel")
    async def publish(self,interaction:discord.Interaction,day:int,
                      confirmation:str,refresh_existing:bool=False):
        if confirmation.strip()!="PUBLISH":
            await interaction.response.send_message(
                "Not published. Type exactly `PUBLISH` to authorise a public post.",
                ephemeral=True)
            return
        settings,store=pin(self.settings,self.store)
        if settings.is_test:
            await interaction.response.send_message(
                "Public news publishing is disabled in the disposable Test Centre.",
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            publisher=getattr(interaction.client,"broadcast",None)
            if publisher is None:
                publisher=BroadcastPublisher(interaction.client,settings,store)
            message=await publisher.publish_wire_issue(
                _now(),day,refresh_existing=refresh_existing)
            await interaction.followup.send(
                f"✅ **Wire Day {day}** published or confirmed. "
                f"Message: {message.jump_url if hasattr(message,'jump_url') else message.id}. "
                + ("Existing post refreshed." if refresh_existing else
                   "Existing posts were left unchanged."),
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except (WireError,ValueError,sqlite3.Error,discord.HTTPException) as exc:
            await interaction.followup.send(
                f"⚠️ Publication failed: {_safe(exc)}",ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="flash",description="Check whether a factual community newsflash is ready")
    async def flash(self,interaction:discord.Interaction):
        settings,store=pin(self.settings,self.store)
        await interaction.response.defer(ephemeral=True)
        try:
            event=await asyncio.to_thread(
                WireEngine(store).flash,settings.season_key,_now())
            body=(event[1] if event else
                  "No eligible newsflash milestone yet. The first day with "
                  "10 logged throws or 12 completed arcade runs unlocks one bulletin.")
            await interaction.followup.send(
                "📡 **Wire newsflash status (no new post sent)**\n"+body,
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except (WireError,ValueError,sqlite3.Error) as exc:
            await interaction.followup.send(f"⚠️ {_safe(exc)}",ephemeral=True)


def _safe(value):
    return clean_name(str(value),80)
