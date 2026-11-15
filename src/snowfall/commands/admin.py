"""Restricted staff foundation commands; not a complete event administration console."""
from __future__ import annotations
import asyncio
import csv
from datetime import datetime, timezone
import io
import discord
from discord import app_commands
from snowfall.core.clock import phase


class SnowAdminGroup(app_commands.Group):
    def __init__(self, settings, store):
        super().__init__(name="snowadmin", description="Kat and authorised event staff")
        self.settings = settings
        self.store = store

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.settings.guild_id or interaction.user.id not in self.settings.admin_user_ids:
            await interaction.response.send_message("You are not authorised for event administration.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="status", description="Private staff event status")
    async def status(self, interaction: discord.Interaction):
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        audit_count = await asyncio.to_thread(self.store.audit_count, self.settings.season_key)
        await interaction.response.send_message(
            f"**{self.settings.event_name}**\nPhase: {phase(self.settings.starts_at_utc, datetime.now(timezone.utc))}\n"
            f"Registered: {len(players)}\nFlags: {sum(p.review_state == 'flagged' for p in players)}\n"
            f"Admin audit entries: {audit_count}\nIndividual prizes only; city title is honorary.\n"
            "Foundation preview; live gameplay/admin start/pause controls not yet implemented.",
            ephemeral=True,
        )

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
                                    interaction.user.id, player.id, state.value,
                                    reason, datetime.now(timezone.utc))
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(f"Review state updated: {state.value}. Audit entry recorded.",
                                        ephemeral=True)

    @app_commands.command(name="export-registrations", description="Export registrations (staff only)")
    async def export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        regs = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        buff = io.StringIO()
        writer = csv.writer(buff)
        writer.writerow(["discord_user_id", "mr_username", "city", "joined_at_utc", "review_state"])
        for p in regs:
            writer.writerow([p.discord_user_id, p.mr_username, p.city, p.joined_at_utc, p.review_state])
        file = discord.File(io.BytesIO(buff.getvalue().encode("utf-8-sig")), filename="registrations.csv")
        await interaction.followup.send("Private registration list (not a prize export).",
                                        file=file, ephemeral=True)
