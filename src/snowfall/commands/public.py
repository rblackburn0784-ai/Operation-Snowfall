"""User commands available only within the dedicated event Discord guild."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands

from snowfall.core.permissions import permitted_guild
from snowfall.db.store import CITIES
from snowfall.ui.dashboard import CityPicker, Dashboard, dashboard_embed, escape_name, rules_text


class SnowGroup(app_commands.Group):
    def __init__(self, settings, store):
        super().__init__(name="snow", description="Operation Snowfall player commands")
        self.settings, self.store = settings, store

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Use the dedicated Snowfall event server.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="dashboard", description="Open the Snowfall menu")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        now = datetime.now(timezone.utc)
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        await interaction.followup.send(embed=dashboard_embed(self.settings, season, now, len(players)),
                                        view=Dashboard(self.settings, self.store), ephemeral=True)

    @app_commands.command(name="join", description="Declare your MafiaReturns username and city")
    async def join(self, interaction: discord.Interaction):
        stage = self.store.season(self.settings.season_key).phase(datetime.now(timezone.utc))
        if stage not in ("registration", "ready", "live", "paused"):
            await interaction.response.send_message("Registration is not currently open.", ephemeral=True)
            return
        await interaction.response.send_message("Choose your city, then confirm your MR username:",
                                                view=CityPicker(self.settings, self.store), ephemeral=True)

    @app_commands.command(name="profile", description="Show your registration")
    async def profile(self, interaction: discord.Interaction):
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key, interaction.user.id)
        message = (f"**{escape_name(p.mr_username)}** — {p.city}\n"
                   f"Claim status: {p.review_state}\nCombat comes in milestone B.") if p else (
                   "You are not registered. Use `/snow join`.")
        await interaction.response.send_message(message, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="cities", description="Show registration counts, not prize rankings")
    async def cities(self, interaction: discord.Interaction):
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        counts = {c: 0 for c in CITIES}
        for player in players:
            if player.review_state != "disqualified":
                counts[player.city] += 1
        await interaction.response.send_message(
            "**City registrations** (honorary city contest, individual prizes only):\n" +
            "\n".join(f"{c}: **{n}**" for c, n in counts.items()), ephemeral=True)

    @app_commands.command(name="rules", description="Read event rules and identity policy")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(rules_text(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
