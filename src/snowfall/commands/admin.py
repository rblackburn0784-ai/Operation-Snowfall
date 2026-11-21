"""Audit-backed staff reviews and host-only season lifecycle commands."""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import io
import sqlite3

import discord
from discord import app_commands

from snowfall.core.permissions import is_host, is_staff, permitted_guild
from snowfall.db.store import LifecycleError, RegistrationError
from snowfall.ui.dashboard import Dashboard, dashboard_embed, rules_text
from snowfall.services.world import WorldEngine, WorldError
from snowfall.practice import PracticeError
from snowfall.ui.navigation import send_admin_panel
from snowfall.services.broadcast import DAY_DETAILS
from snowfall.services.world import THEMES
from snowfall.ops import (
    OperationsError, approve_launch, is_approved, check_health, backup_sqlite,
    adjust_personal_score, reconcile, capture_final_awards, mark_prize, award_csv,
    safe_csv_cell,
)


def _now():
    return datetime.now(timezone.utc)


class SnowAdminGroup(app_commands.Group):
    def __init__(self, settings, store, practice=None):
        super().__init__(name="snowadmin", description="Operation Snowfall organisers and staff")
        self.settings, self.store, self.practice = settings, store, practice

    @staticmethod
    def _shared_qa(interaction) -> bool:
        store = getattr(getattr(interaction, "client", None), "store", None)
        return bool(getattr(store, "unified_discord", False))

    async def _qa_forbidden(self, interaction, action: str) -> bool:
        if not self._shared_qa(interaction):
            return False
        await interaction.response.send_message(
            f"🧪 `{action}` is disabled in shared QA. "
            "No prize, official launch or public-broadcast state was changed.",
            ephemeral=True)
        return True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.practice is not None:
            self.practice.for_interaction(interaction.channel_id)
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return False
        roles = frozenset(role.id for role in getattr(interaction.user, "roles", []))
        if not is_staff(interaction.user.id, self.settings.admin_user_ids,
                        self.settings.staff_role_ids, roles):
            await interaction.response.send_message("This command is restricted to event staff.", ephemeral=True)
            return False
        # QA exposes read-only diagnostics only. The old host UI includes
        # test-day resets, event dates, player reviews and score adjustments,
        # all of which must stay unavailable to the shared canonical season.
        command = getattr(getattr(interaction, "command", None), "name", "")
        if self._shared_qa(interaction) and command not in {
            "status", "test-status", "launch-check",
        }:
            await interaction.response.send_message(
                "🧪 This host operation is disabled in shared QA. "
                "Use /snowadmin launch-check or /snowadmin status for "
                "read-only checks; no scores, event dates or prizes were changed.",
                ephemeral=True)
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
        if action == "finalize" and await self._qa_forbidden(interaction, action):
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

    @app_commands.command(name="panel", description="Open private host Main/Admin/Test control panel")
    async def panel(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await send_admin_panel(interaction)

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
            f" {'🧪 SHARED QA — NO REAL PRIZES' if self._shared_qa(interaction) else '🧪 TEST INSTANCE — NO REAL PRIZES' if self.settings.is_test else 'PRODUCTION'}\n"
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
        if (self.settings.mode == "practice" and self.practice is not None and
                self.practice.session is not None and
                channel.id != self.practice.session.channel_id):
            await interaction.response.send_message(
                "Practice dashboards may only be posted in the active TEST channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        now = _now()
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        embed = dashboard_embed(self.settings, season, now, len(players))
        embed.add_field(name="Welcome and Rules", value=rules_text(self.settings)[:1024], inline=False)
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
        if await self._qa_forbidden(interaction, "publish-leaderboards"):
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
        if await self._qa_forbidden(interaction, "announce-day"):
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
            writer.writerow([p.discord_user_id, safe_csv_cell(p.mr_username),
                             p.city, p.joined_at_utc, p.review_state])
        blob = io.BytesIO(output.getvalue().encode("utf-8-sig"))
        await interaction.followup.send(
            "Private staff registration export — **not** a prize list.",
            file=discord.File(blob, filename="snowfall_registrations.csv"), ephemeral=True)

    @app_commands.command(name="test-start", description="Host: start one disposable Day 1–7 rehearsal in a test channel")
    @app_commands.describe(day="Choose Day 1 to Day 7", channel="Dedicated TEST text channel",
                           confirmation="Type TEST")
    async def test_start(self, interaction: discord.Interaction, day: int,
                         channel: discord.TextChannel, confirmation: str):
        if not await self.require_host(interaction):
            return
        if self.practice is None:
            await interaction.response.send_message("Test sessions unavailable.", ephemeral=True)
            return
        if confirmation != "TEST" or channel.guild.id != self.settings.guild_id:
            await interaction.response.send_message("Type TEST and select a channel in this server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            session = await asyncio.to_thread(self.practice.start, day, channel.id,
                                              interaction.user.id, _now())
            await channel.send(f"🧪 **OPERATION SNOWFALL — TEST DAY {day}/7**\n"
                               f"**{THEMES[day - 1]}** — {DAY_DETAILS[day - 1][0]}\n"
                               f"{DAY_DETAILS[day - 1][1]}\n\n"
                               "**PRACTICE ONLY — NO REAL SCORES OR PRIZES.**\n"
                               "Use `/snow join`, `/snow ready`, `/snow throw`, `/snow boss`, "
                               "`/snow siege`, `/snow inventory`, `/snow quests`, "
                               "`/snow present` and `/snow leaderboard` **in this channel**. "
                               "The real #leaderboard and #Announcements stay untouched.",
                               allowed_mentions=discord.AllowedMentions.none())
        except (PracticeError, ValueError, discord.HTTPException) as exc:
            # A Discord posting failure should not secretly terminate a started test.
            await interaction.followup.send(f"⚠️ Test setup: {exc}\n"
                                            "Use /snowadmin test-status to inspect its state.", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ **TEST DAY {day}** running in {channel.mention}. "
            f"Session `{session.id[:8]}`. Stop using `/snowadmin test-end`.", ephemeral=True)

    @app_commands.command(name="test-day", description="Host: reset practice scores and switch to another event day")
    async def test_day(self, interaction: discord.Interaction, day: int,
                       confirmation: str):
        if not await self.require_host(interaction):
            return
        if self.practice is None or confirmation != "RESET_TEST_DAY":
            await interaction.response.send_message("Type RESET_TEST_DAY to discard the previous "
                                                    "practice day and select Day 1–7.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            session = await asyncio.to_thread(self.practice.change_day, day,
                                              interaction.user.id, _now())
            channel = interaction.client.get_channel(session.channel_id)
            if channel is not None:
                await channel.send(f"🧪 **NEW TEST DAY {day}/7 — ALL PREVIOUS TEST SCORES RESET**\n"
                                   f"**{THEMES[day - 1]}**\n{DAY_DETAILS[day - 1][1]}\n"
                                   "Use `/snow dashboard` to open new practice controls.",
                                   allowed_mentions=discord.AllowedMentions.none())
        except (PracticeError, ValueError, discord.HTTPException) as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Now testing **Day {day}**. "
                                        "MR registrations were carried over; practice points/items reset.",
                                        ephemeral=True)

    @app_commands.command(name="test-status", description="Host: show active practice day and its daily bonuses")
    async def test_status(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        state = self.practice.snapshot(_now()) if self.practice else {"active": False}
        if not state["active"]:
            await interaction.response.send_message(
                "No practice session is active. Use `/snowadmin test-start`.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🧪 **TEST DAY {state['day']}/7 — {state['theme']}**\n"
            f"Test channel: <#{state['channel_id']}> | Test players: {state['players']}\n"
            f"**Today's special feature:** {state['bonus']}\n"
            "All combat, inventory, quest, gift, boss and siege actions in the test channel "
            "are disposable. Outside it, the production event is unchanged.\n"
            "`/snowadmin test-day` selects another day and resets practice scores.\n"
            "`/snowadmin test-end` deletes or archives practice data.", ephemeral=True)

    @app_commands.command(name="test-end", description="Host: stop the test day and delete/archive only practice data")
    @app_commands.describe(archive="Keep a local SQLite archive for review, otherwise erase test data")
    async def test_end(self, interaction: discord.Interaction, confirmation: str,
                       archive: bool = False):
        if not await self.require_host(interaction):
            return
        if confirmation != "END_TEST" or self.practice is None:
            await interaction.response.send_message("Type END_TEST to finish the practice day. "
                                                    "Production will be unaffected.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            old = self.practice.session
            saved = await asyncio.to_thread(self.practice.end, archive=archive)
            if old is not None:
                channel = interaction.client.get_channel(old.channel_id)
                if channel is not None:
                    await channel.send("✅ **TEST COMPLETE — PRACTICE DATA "
                                       + ("ARCHIVED" if saved else "DELETED") + "**\n"
                                       "Normal production commands remain available. "
                                       "Old practice menus are disabled.",
                                       allowed_mentions=discord.AllowedMentions.none())
        except (PracticeError, OSError, sqlite3.Error, discord.HTTPException) as exc:
            await interaction.followup.send(f"⚠️ Test end: {exc}", ephemeral=True)
            return
        await interaction.followup.send("✅ Practice ended. " +
                                        (f"Archive: `{saved.name}` (local, not prize data)."
                                         if saved else "Disposable database erased.") +
                                        " The LIVE bot remains online and unchanged.", ephemeral=True)

    @app_commands.command(name="test-stop", description="Alias: end a test day (does NOT stop the Discord bot)")
    async def test_stop(self, interaction: discord.Interaction, confirmation: str):
        await self.test_end.callback(self, interaction, confirmation, False)

    @app_commands.command(name="launch-check", description="Host: inspect launch and data integrity")
    async def launch_check(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        if self._shared_qa(interaction):
            # Production's SQLite-only checks do not apply in shared QA.
            from snowfall.platform.launch_audit import audit_qa_database
            try:
                report = await asyncio.to_thread(
                    audit_qa_database, interaction.client.store.dsn)
            except Exception:
                await interaction.followup.send(
                    "⚠️ Shared QA audit unavailable. No game state was changed.",
                    ephemeral=True)
                return
            await interaction.followup.send(
                "**🧪 Shared QA PostgreSQL launch audit — NO REAL PRIZES**\n"
                f"Status: **{report['status']}**\n"
                f"Registered linked players: {report['linked_registered_players']}\n"
                f"Fictional/unlinked players: {report['unlinked_or_fixture_players']}\n"
                f"Orphan resources: {report['orphan_resources']} · "
                f"Bad resource values: {report['bad_resources']}\n"
                f"QA prize awards (MUST BE ZERO): {report['prize_awards']}\n"
                "Blockers: " + (", ".join(report["blockers"]) or "none") +
                "\nWarnings: " + (", ".join(report["warnings"]) or "none") +
                "\nOfficial prize launch is disabled in this QA season.",
                ephemeral=True)
            return
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
        if await self._qa_forbidden(interaction, "approve-launch"):
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
            f"Quest over cap: {result['quest_over_cap_count']} • "
            f"Unbacked quest credits: {result['quest_unbacked_count']} • "
            f"Missing quest credits: {result['quest_missing_count']} • "
            f"Defense mismatches: {result['defense_mismatch_count']}", ephemeral=True)

    @app_commands.command(name="backup", description="Host: create an immediate verified database backup")
    async def backup(self, interaction: discord.Interaction):
        if not await self.require_host(interaction):
            return
        if await self._qa_forbidden(interaction, "backup (use managed PostgreSQL backups)"):
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
        if await self._qa_forbidden(interaction, "export-prizes"):
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
        if await self._qa_forbidden(interaction, "prize-status"):
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
