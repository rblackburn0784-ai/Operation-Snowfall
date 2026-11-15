"""Audit-backed staff reviews and host-only season lifecycle commands."""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import io

import discord
from discord import app_commands

from snowfall.core.permissions import is_host, is_staff, permitted_guild
from snowfall.db.store import LifecycleError, RegistrationError
from snowfall.ui.dashboard import Dashboard, dashboard_embed, rules_text


def _now():
    return datetime.now(timezone.utc)


class SnowAdminGroup(app_commands.Group):
    def __init__(self, settings, store):
        super().__init__(name="snowadmin", description="Operation Snowfall organisers and staff")
        self.settings, self.store = settings, store

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return False
        roles = frozenset(role.id for role in getattr(interaction.user, "roles", []))
        if not is_staff(interaction.user.id, self.settings.admin_user_ids,
                        self.settings.staff_role_ids, roles):
            await interaction.response.send_message("This command is restricted to event staff.", ephemeral=True)
            return False
        return True

    async def require_host(self, interaction: discord.Interaction) -> bool:
        if not is_host(interaction.user.id, self.settings.admin_user_ids):
            await interaction.response.send_message("Only Kat / configured hosts can do that.", ephemeral=True)
            return False
        return True

    async def perform(self, interaction: discord.Interaction, action: str,
                      confirmation: str, reason: str, new_start: datetime | None = None):
        if not await self.require_host(interaction):
            return
        if confirmation.strip().upper() != action.upper():
            await interaction.response.send_message(
                f"Not changed. To confirm, enter exactly `{action.upper()}`.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            season = await asyncio.to_thread(self.store.transition, self.settings.season_key,
                                             interaction.user.id, action, _now(), reason, new_start)
        except (LifecycleError, ValueError) as exc:
            await interaction.followup.send(f"No change: {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ **{action.title()}** recorded. Phase: **{season.phase(_now())}**. "
            "Audit entry saved.", ephemeral=True)

    @app_commands.command(name="status", description="Check staff event status and registration")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        audits = await asyncio.to_thread(self.store.audit_count, self.settings.season_key)
        now = _now()
        projected = season.projected_end(now)
        await interaction.followup.send(
            f"**{self.settings.event_name}**\n"
            f"Phase: **{season.phase(now)}** | Game day: **{season.day(now) or '—'}**\n"
            f"Registration: <t:{int(season.registration_opens().timestamp())}:F>\n"
            f"Scheduled start: <t:{int(season.planned_start.timestamp())}:F>\n"
            f"Projected end: {f'<t:{int(projected.timestamp())}:F>' if projected else 'after host start'}\n"
            f"Registered: {len(players)} | Flagged: {sum(p.review_state == 'flagged' for p in players)}\n"
            f"Audit entries: {audits}\nIndividual prizes only. Gameplay not yet available.",
            ephemeral=True)

    @app_commands.command(name="setup", description="Change future UTC kickoff before registration opens")
    @app_commands.describe(start_at_utc="ISO 8601 UTC, e.g. 2026-12-20T19:00:00+00:00",
                           confirmation="Type SETUP", reason="Why the schedule is being changed")
    async def setup(self, interaction: discord.Interaction, start_at_utc: str,
                    confirmation: str, reason: str):
        if not await self.require_host(interaction):
            return
        try:
            start = datetime.fromisoformat(start_at_utc)
            if start.tzinfo is None or start.utcoffset().total_seconds() != 0:
                raise ValueError("Start must be timezone-aware UTC")
        except (TypeError, ValueError):
            await interaction.response.send_message(
                "Use an ISO UTC time like 2026-12-20T19:00:00+00:00.", ephemeral=True)
            return
        await self.perform(interaction, "setup", confirmation, reason, start)

    @app_commands.command(name="start", description="Host: begin exactly 168 effective hours")
    async def start(self, interaction: discord.Interaction, confirmation: str,
                    reason: str = "Host opened the event"):
        await self.perform(interaction, "start", confirmation, reason)

    @app_commands.command(name="pause", description="Host: freeze the event clock")
    async def pause(self, interaction: discord.Interaction, confirmation: str, reason: str):
        await self.perform(interaction, "pause", confirmation, reason)

    @app_commands.command(name="resume", description="Host: resume and extend the effective window")
    async def resume(self, interaction: discord.Interaction, confirmation: str,
                     reason: str = "Host resumed the event"):
        await self.perform(interaction, "resume", confirmation, reason)

    @app_commands.command(name="finalize", description="Host: freeze results after all 7 effective days")
    async def finalize(self, interaction: discord.Interaction, confirmation: str,
                       reason: str = "Seven-day season completed"):
        await self.perform(interaction, "finalize", confirmation, reason)

    @app_commands.command(name="review", description="Flag, clear or disqualify a claimed MR identity")
    @app_commands.choices(state=[
        app_commands.Choice(name="Flag for review", value="flagged"),
        app_commands.Choice(name="Clear dispute", value="cleared"),
        app_commands.Choice(name="Disqualify", value="disqualified"),
    ])
    async def review(self, interaction: discord.Interaction, player: discord.User,
                     state: app_commands.Choice[str], reason: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(self.store.review, self.settings.season_key,
                                    interaction.user.id, player.id, state.value, reason, _now())
        except (RegistrationError, ValueError) as exc:
            await interaction.followup.send(f"No change: {exc}", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Review state: **{state.value}**; audit saved.",
                                        ephemeral=True)

    @app_commands.command(name="publish-dashboard", description="Host: create/update main welcome and rules card")
    async def publish_dashboard(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.require_host(interaction):
            return
        if channel.guild.id != self.settings.guild_id:
            await interaction.response.send_message("Channel must be in the event server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        now = _now()
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        embed = dashboard_embed(self.settings, season, now, len(players))
        embed.add_field(name="Welcome and Rules", value=rules_text()[:1024], inline=False)
        existing = await asyncio.to_thread(self.store.get_published,
                                           self.settings.season_key, "dashboard")
        message = None
        try:
            if existing and existing[0] == channel.id:
                try:
                    old = await channel.fetch_message(existing[1])
                    message = await old.edit(embed=embed, view=Dashboard(self.settings, self.store))
                except discord.NotFound:
                    pass
            if message is None:
                message = await channel.send(embed=embed, view=Dashboard(self.settings, self.store))
        except discord.Forbidden:
            await interaction.followup.send("Bot needs View Channel, Send Messages, Embed Links and "
                                            "Read Message History in that channel.", ephemeral=True)
            return
        await asyncio.to_thread(self.store.record_published, self.settings.season_key,
                                interaction.user.id, "dashboard", channel.id, message.id, now)
        await interaction.followup.send(
            f"✅ Dashboard saved: {message.jump_url}\nPin this message manually if desired.",
            ephemeral=True)

    @app_commands.command(name="export-registrations", description="Staff-only private CSV of claimed identities")
    async def export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["discord_user_id", "mr_username", "city", "joined_at_utc", "review_state"])
        for p in players:
            writer.writerow([p.discord_user_id, p.mr_username, p.city, p.joined_at_utc, p.review_state])
        blob = io.BytesIO(output.getvalue().encode("utf-8-sig"))
        await interaction.followup.send(
            "Private staff registration export — **not** a prize list.",
            file=discord.File(blob, filename="snowfall_registrations.csv"), ephemeral=True)
