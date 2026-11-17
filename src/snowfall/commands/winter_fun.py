"""Dedicated, private winter activities command group (the /snow group is full)."""
from __future__ import annotations

import discord
from discord import app_commands

from snowfall.core.permissions import permitted_guild
from snowfall.ui.winter_fun import send_activities


class SnowFunGroup(app_commands.Group):
    def __init__(self, settings, store, practice=None):
        super().__init__(name="snowfun", description="Christmas shop, encounters and extra modes")
        self.settings, self.store, self.practice = settings, store, practice

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.practice is not None:
            self.practice.for_interaction(interaction.channel_id)
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Use the dedicated Snowfall server.", ephemeral=True)
            return False
        return True

    async def _open(self, interaction: discord.Interaction, page: str) -> None:
        await interaction.response.defer(ephemeral=True)
        await send_activities(interaction, self.settings, self.store, page=page)

    @app_commands.command(name="menu", description="Open Winter Activities and arcade menu")
    async def menu(self, interaction: discord.Interaction):
        await self._open(interaction, "Activities")

    @app_commands.command(name="shop", description="Browse cosmetic outfits and specialist gear")
    async def shop(self, interaction: discord.Interaction):
        await self._open(interaction, "Shop")

    @app_commands.command(name="wardrobe", description="Equip unlocked frames, gear and trails")
    async def wardrobe(self, interaction: discord.Interaction):
        await self._open(interaction, "Wardrobe")

    @app_commands.command(name="encounter", description="Find today's special Christmas encounter")
    async def encounter(self, interaction: discord.Interaction):
        await self._open(interaction, "Encounter")

    @app_commands.command(name="arcade", description="Play no-prize winter mini-games")
    async def arcade(self, interaction: discord.Interaction):
        await self._open(interaction, "Arcade")

    @app_commands.command(name="rivalries", description="Private PvP records, hit streaks and revenge alerts")
    async def rivalries(self, interaction: discord.Interaction):
        from snowfall.ui.rivalries import send_rivalries
        await interaction.response.defer(ephemeral=True)
        await send_rivalries(interaction, self.settings, self.store)

    @app_commands.command(name="raid", description="Cooperative Snow Don raid, honours and victory replay")
    async def raid(self, interaction: discord.Interaction):
        from snowfall.ui.raid import send_raid
        await interaction.response.defer(ephemeral=True)
        await send_raid(interaction, self.settings, self.store)

    @app_commands.command(name="territory", description="Interactive six-city map, district control and daily wars")
    async def territory(self, interaction: discord.Interaction):
        from snowfall.ui.territory import show_territory
        await interaction.response.defer(ephemeral=True)
        await show_territory(interaction, self.settings, self.store,
                             interaction.user.id, deferred=True)

    @app_commands.command(name="mystery", description="Investigate Christmas cases and secret winter encounters")
    async def mystery(self, interaction: discord.Interaction):
        from snowfall.ui.mysteries import send_mystery
        await interaction.response.defer(ephemeral=True)
        await send_mystery(interaction, self.settings, self.store)

    @app_commands.command(name="showcase", description="Publish your illustrated player card in this channel")
    @app_commands.checks.cooldown(1, 600.0, key=lambda i: (i.guild_id, i.user.id))
    async def showcase(self, interaction: discord.Interaction):
        from snowfall.ui.showcase import publish_card
        await publish_card(interaction, self.settings, self.store)

    @showcase.error
    async def showcase_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            text = f"Your showcase cooldown is active. Try again in {int(error.retry_after) + 1}s."
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
            return
        raise error

