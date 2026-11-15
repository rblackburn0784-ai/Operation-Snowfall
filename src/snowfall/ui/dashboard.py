"""Small persistent classic-button dashboard. Components v2 art is a separate ticket."""
from __future__ import annotations
import asyncio
import discord
from snowfall.core.clock import phase
from snowfall.db.store import CITIES
from datetime import datetime, timezone


def escape_name(name: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(name))


class JoinModal(discord.ui.Modal, title="Operation Snowfall — Register"):
    mr_username = discord.ui.TextInput(label="Your MafiaReturns username", min_length=2, max_length=32)
    declaration = discord.ui.TextInput(label="Type I AGREE to self-declare", min_length=7, max_length=7)

    def __init__(self, settings, store, city: str):
        super().__init__(timeout=180)
        self.settings = settings
        self.store = store
        self.city = city

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != self.settings.guild_id:
            await interaction.response.send_message("This bot only works in the event server.", ephemeral=True)
            return
        if str(self.declaration.value).strip().upper() != "I AGREE":
            await interaction.response.send_message("Registration not completed: confirm by typing I AGREE.", ephemeral=True)
            return
        if phase(self.settings.starts_at_utc, datetime.now(timezone.utc)) not in ("registration", "live"):
            await interaction.response.send_message("Registration is not currently open.", ephemeral=True)
            return
        from snowfall.db.store import RegistrationError
        try:
            p = await asyncio.to_thread(self.store.register, self.settings.season_key,
                                        interaction.user.id, self.mr_username.value,
                                        self.city, datetime.now(timezone.utc))
        except RegistrationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"❄️ Registered **{escape_name(p.mr_username)}** for **{p.city}**! "
            "Your MR identity is self-declared; contact staff if another player disputes it.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class CityPicker(discord.ui.View):
    def __init__(self, settings, store):
        super().__init__(timeout=180)
        dropdown = discord.ui.Select(
            placeholder="Select your MafiaReturns city",
            options=[discord.SelectOption(label=name, value=name) for name in CITIES],
        )
        async def selected(interaction: discord.Interaction):
            if interaction.guild_id != settings.guild_id:
                await interaction.response.send_message("Wrong event server.", ephemeral=True)
                return
            await interaction.response.send_modal(JoinModal(settings, store, dropdown.values[0]))
        dropdown.callback = selected
        self.add_item(dropdown)


class Dashboard(discord.ui.View):
    def __init__(self, settings, store):
        super().__init__(timeout=None)
        self.settings = settings
        self.store = store

    @discord.ui.button(label="Join", style=discord.ButtonStyle.primary,
                       custom_id="snowfall:v1:join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != self.settings.guild_id:
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return
        if phase(self.settings.starts_at_utc, datetime.now(timezone.utc)) not in ("registration", "live"):
            await interaction.response.send_message("Registration is not open yet.", ephemeral=True)
            return
        await interaction.response.send_message("Choose your city to register:",
                                                ephemeral=True, view=CityPicker(self.settings, self.store))

    @discord.ui.button(label="My Profile", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:profile")
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != self.settings.guild_id:
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key,
                                    interaction.user.id)
        message = (f"❄️ **{escape_name(p.mr_username)}** — {p.city} ({p.review_state})\n"
                   "Combat/points: coming in the gameplay milestones.") if p else "Not registered; select Join first."
        await interaction.response.send_message(message, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:rules")
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != self.settings.guild_id:
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return
        await interaction.response.send_message(
            "❄️ **Operation Snowfall:** Seven-day Christmas snowball event, six city teams, "
            "individual prizes only; city title = bragging rights. Registration opens 7 days before kickoff. "
            "This build is a foundation preview: attacks and rewards are not yet available.",
            ephemeral=True,
        )
