"""Public, guild-restricted slash commands. Gameplay buttons follow later tickets."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import discord
from discord import app_commands
from snowfall.core.clock import phase, registration_opens, event_ends, game_day
from snowfall.db.store import CITIES
from snowfall.ui.dashboard import CityPicker, Dashboard, escape_name


class SnowGroup(app_commands.Group):
    def __init__(self, settings, store):
        super().__init__(name="snow", description="Operation Snowfall player commands")
        self.settings = settings
        self.store = store

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.settings.guild_id:
            await interaction.response.send_message("Use the dedicated Operation Snowfall Discord server.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="dashboard", description="Open the event dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        current_phase = phase(self.settings.starts_at_utc, now)
        description = (
            f"**Status:** {current_phase.replace('_', ' ').title()}\n"
            f"**Opens:** <t:{int(registration_opens(self.settings.starts_at_utc).timestamp())}:F>\n"
            f"**Start:** <t:{int(self.settings.starts_at_utc.timestamp())}:F>\n"
            f"**End:** <t:{int(event_ends(self.settings.starts_at_utc).timestamp())}:F>\n"
            f"**Day:** {game_day(self.settings.starts_at_utc, now) or '—'} / 7\n"
            "**Prizes:** Individual only. Cities compete for bragging rights.\n"
            "*Foundation preview: live gameplay is not installed yet.*"
        )
        embed = discord.Embed(title="❄️ Operation Snowfall", description=description)
        await interaction.response.send_message(embed=embed, view=Dashboard(self.settings, self.store),
                                                ephemeral=True)

    @app_commands.command(name="join", description="Self-declare MR name and city")
    async def join(self, interaction: discord.Interaction):
        if phase(self.settings.starts_at_utc, datetime.now(timezone.utc)) not in ("registration", "live"):
            await interaction.response.send_message("Registration is not open.", ephemeral=True)
            return
        await interaction.response.send_message("Select your city, then enter your MR username:",
                                                view=CityPicker(self.settings, self.store), ephemeral=True)

    @app_commands.command(name="profile", description="Show your registration details")
    async def profile(self, interaction: discord.Interaction):
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key, interaction.user.id)
        msg = (f"**{escape_name(p.mr_username)}** — {p.city}\n"
               f"Review: {p.review_state}\nNo combat scores yet (foundation preview).") if p else "You have not joined yet. Use `/snow join`."
        await interaction.response.send_message(msg, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="cities", description="Show registration counts by city (not the live leaderboard)")
    async def cities(self, interaction: discord.Interaction):
        regs = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        counts = {city: 0 for city in CITIES}
        for p in regs:
            if p.review_state != "disqualified":
                counts[p.city] += 1
        msg = "**Registered players by city** (NOT competition points):\n" + "\n".join(
            f"{city}: **{count}**" for city, count in counts.items())
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="rules", description="Read the approved v1.0 rules summary")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "**Operation Snowfall:** 7 full days; join by self-declaring your MR username and city. "
            "Registration opens exactly 7 days before launch; late entry allowed, no score backfill. "
            "Individual prizes only. City standings earn recognition, never MR credits or perks. "
            "No MR passwords. Staff handle impersonation disputes. Full gameplay is in development.",
            ephemeral=True,
        )
