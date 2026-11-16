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
from snowfall.services.world import WorldEngine, WorldError
from snowfall.ops import (
    OperationsError, approve_launch, is_approved, check_health, backup_sqlite,
    adjust_personal_score, reconcile, capture_final_awards, mark_prize, award_csv,
)


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
        if action == "start" and not self.settings.is_test:
            if not await asyncio.to_thread(is_approved, self.store, self.settings.season_key):
                await interaction.response.send_message(
                    "Launch not approved. Kat must run `/snowadmin approve-launch` "
                    "after the checklist before starting production.", ephemeral=True)
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
        if action in ("start", "pause", "resume", "finalize"):
            await asyncio.to_thread(WorldEngine(self.store).tick,
                                    self.settings.season_key, _now())
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
            f"**{self.settings.event_name}**"
            f" {'🧪 TEST INSTANCE — NO REAL PRIZES' if self.settings.is_test else 'PRODUCTION'}\n"
            f"Phase: **{season.phase(now)}** | Game day: **{season.day(now) or '—'}**\n"
            f"Registration: <t:{int(season.registration_opens().timestamp())}:F>\n"
            f"Scheduled start: <t:{int(season.planned_start.timestamp())}:F>\n"
            f"Projected end: {f'<t:{int(projected.timestamp())}:F>' if projected else 'after host start'}\n"
            f"Registered: {len(players)} | Flagged: {sum(p.review_state == 'flagged' for p in players)}\n"
            f"Audit entries: {audits}\nIndividual prizes only. Snowball PvP is active when LIVE.",
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

    @app_commands.command(name="boss-settings",
                          description="Host: configure Snow Don before the seven-day event starts")
    @app_commands.describe(hp_override="0 = automatic scaling; otherwise 150-100000 HP")
    async def boss_settings(self, interaction: discord.Interaction, enabled: bool,
                            hp_override: int, reason: str):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(WorldEngine(self.store).configure_boss,
                                    self.settings.season_key, interaction.user.id,
                                    enabled, hp_override or None, reason, _now())
        except (ValueError, WorldError) as exc:
            await interaction.followup.send(f'⚠️ No change: {exc}', ephemeral=True)
            return
        await interaction.followup.send(
            f'✅ Snow Don is {"enabled" if enabled else "disabled"}. '
            f'HP: {hp_override or "automatic"}. Audit entry recorded.', ephemeral=True)

    @app_commands.command(name="publish-leaderboards",
                          description="Host: create or refresh the single five-minute leaderboard")
    async def publish_boards(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        if not self.settings.leaderboard_channel_id:
            await interaction.response.send_message(
                "Configure leaderboard_channel_id first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            message = await interaction.client.broadcast.update_leaderboard(_now())
        except (discord.HTTPException, ValueError) as exc:
            await interaction.followup.send(f"⚠️ Leaderboard update failed: {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ Combined individual + city leaderboard: {message.jump_url}\n"
            "This exact message is edited every five minutes, including after restarts.",
            ephemeral=True)

    @app_commands.command(name="announce-day",
                          description="Host: publish/update today's announcement in #Announcements")
    async def announce_day(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        if not self.settings.announcement_channel_id:
            await interaction.response.send_message(
                "Configure announcement_channel_id first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(WorldEngine(self.store).tick,
                                    self.settings.season_key, _now())
            message = await interaction.client.broadcast.publish_current_day(
                _now(), refresh_existing=True)
        except (discord.HTTPException, ValueError) as exc:
            await interaction.followup.send(f"⚠️ Announcement failed: {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ The current event-day announcement was published/updated: {message.jump_url}",
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

    @app_commands.command(name="test-stop", description="Host: gracefully stop ONLY the test bot")
    async def test_stop(self, interaction: discord.Interaction, confirmation: str):
        if not await self.require_host(interaction):
            return
        if not self.settings.is_test:
            await interaction.response.send_message(
                "Refused: this is the PRODUCTION bot. Test-stop cannot shut it down.",
                ephemeral=True)
            return
        if confirmation != "STOP_TEST":
            await interaction.response.send_message("Type STOP_TEST to shut down the sandbox bot.",
                                                    ephemeral=True)
            return
        await interaction.response.send_message(
            "🧪 Test bot closing. No production event state or awards were touched.",
            ephemeral=True)
        await interaction.client.close()

    @app_commands.command(name="launch-check", description="Host: inspect launch and data integrity")
    async def launch_check(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        state = await asyncio.to_thread(self.store.season, self.settings.season_key)
        health = await asyncio.to_thread(check_health, self.store, self.settings.season_key,
                                         self.settings.backup_dir)
        checked = await asyncio.to_thread(reconcile, self.store, self.settings.season_key)
        approved = await asyncio.to_thread(is_approved, self.store, self.settings.season_key)
        phase = state.phase(_now())
        await interaction.followup.send(
            f"**Launch check — {'TEST' if self.settings.is_test else 'PRODUCTION'}**\n"
            f"Phase: `{phase}` • SQLite `{health['sqlite_check']}` • Schema {health['schema_version']}\n"
            f"Season: `{self.settings.season_key}` • Participants: {health['players']}\n"
            f"Ledger check: {'PASS' if checked['ok'] else 'FAIL'} "
            f"({checked['combat_events']} PvP events)\n"
            f"Backup: {health['latest_backup'] or 'NONE (create one before launch)'}\n"
            f"Kat approval: {'YES' if approved else 'NO'}\n"
            "Live gateway permissions and all seven-day dry-run steps must also be checked.",
            ephemeral=True)

    @app_commands.command(name="approve-launch", description="Host: record approval after Kat's dry run")
    async def approve(self, interaction: discord.Interaction, confirmation: str, reason: str):
        if not await self.require_host(interaction):
            return
        if confirmation != "APPROVE":
            await interaction.response.send_message("Type APPROVE to confirm.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(approve_launch, self.store, self.settings.season_key,
                                    interaction.user.id, reason, _now())
        except OperationsError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.followup.send("✅ Launch approval recorded and audited. "
                                        "The host can now start at kickoff.", ephemeral=True)

    @app_commands.command(name="adjust-score", description="Host: append a reasoned score correction")
    async def adjust_score(self, interaction: discord.Interaction, player: discord.User,
                           day: int, delta: int, reason: str):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(adjust_personal_score, self.store, self.settings.season_key,
                                    interaction.user.id, player.id, day, delta, reason,
                                    str(interaction.id), _now())
        except (OperationsError, RegistrationError) as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ {delta:+d} points recorded for {player.mention}, day {day}. "
            "Original scoring rows remain immutable. Audit saved.", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="reconcile", description="Host: check PvP, caps and scoring history")
    async def check_ledger(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        result = await asyncio.to_thread(reconcile, self.store, self.settings.season_key)
        await interaction.followup.send(
            f"**Scoring verification: {'PASS' if result['ok'] else 'FAIL'}**\n"
            f"PvP events: {result['combat_events']} • Ledger entries: {result['ledger_entries']}\n"
            f"Mismatched events: {result['mismatched_combat_ids']}\n"
            f"PvP over cap: {result['pvp_over_cap']}\n"
            f"Quest over cap: {result['quest_over_cap_count']}", ephemeral=True)

    @app_commands.command(name="backup", description="Host: create an immediate verified database backup")
    async def backup(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            path = await asyncio.to_thread(backup_sqlite, self.store.path,
                                           self.settings.backup_dir)
        except (OperationsError, OSError, RuntimeError) as exc:
            await interaction.followup.send(f"Backup failed: {exc}", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Backup and SHA256 manifest saved: `{path.name}`. "
                                        "Keep private and off-site copies.", ephemeral=True)

    @app_commands.command(name="export-prizes", description="Host: export finalized individual awards (CSV)")
    async def export_prizes(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await asyncio.to_thread(capture_final_awards, self.store,
                                           self.settings.season_key, interaction.user.id, _now())
        except OperationsError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            "Private **individual-only** award snapshot. No prizes were sent automatically.",
            file=discord.File(io.BytesIO(award_csv(rows)), filename="snowfall_individual_prizes.csv"),
            ephemeral=True)

    @app_commands.command(name="prize-status", description="Host: record an individual reward payout")
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Paid (manual MR delivery)", value="paid"),
    ])
    async def prize_status(self, interaction: discord.Interaction, place: int, reward: str,
                           status: app_commands.Choice[str], reason: str):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(mark_prize, self.store, self.settings.season_key,
                                    interaction.user.id, place, reward, status.value,
                                    reason, _now())
        except OperationsError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.followup.send("✅ Individual prize status updated; audit saved. "
                                        "No MR API payout was attempted.", ephemeral=True)
