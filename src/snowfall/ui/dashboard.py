"""Persistent main menu and self-declared registration interface."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.core.permissions import permitted_guild
from snowfall.db.store import CITIES, RegistrationError


def escape_name(name: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(name))


def rules_text() -> str:
    return (
        "**❄️ Operation Snowfall — Community Christmas Event**\n"
        "Seven full days of snowball battles across six MafiaReturns city teams.\n"
        "• **Entry:** Self-declare your MR username and city. No MR password or account linking.\n"
        "• **Registration:** Opens 168 hours before scheduled kickoff; late entry is allowed.\n"
        "• **Prizes:** Only individual awards receive prizes. City titles are for bragging rights.\n"
        "• **Fair play:** One MR name per Discord account; impersonation reports go to staff.\n"
        "• **Privacy:** MR usernames, Discord IDs and city choices are stored; staff can review disputes.\n"
        "• **Status:** v0.1.1 foundation only — throwing, points and rewards are not live yet.\n"
        "This is a fan-community game, not a direct MafiaReturns account integration."
    )


def dashboard_embed(settings, season, now: datetime, registered: int) -> discord.Embed:
    stage = season.phase(now)
    opens = int(season.registration_opens().timestamp())
    starts = int(season.planned_start.timestamp())
    ending = season.projected_end(now)
    embed = discord.Embed(
        title="❄️ Operation Snowfall — Event Headquarters",
        description=(
            f"**Phase:** {stage.replace('_', ' ').title()}\n"
            f"**Registration:** <t:{opens}:F>\n"
            f"**Scheduled kickoff:** <t:{starts}:F>\n"
            f"**Projected end:** {f'<t:{int(ending.timestamp())}:F>' if ending else 'After host starts'}\n"
            f"**Current day:** {season.day(now) or '—'} / 7\n"
            f"**Registered players:** {registered}\n"
            "**Prizes:** Individual only. City standings = bragging rights."
        ),
        color=0x78B9EA,
    )
    embed.set_footer(text="Registration and staff controls available. Combat comes in milestone B.")
    return embed


class JoinModal(discord.ui.Modal, title="Operation Snowfall — Register"):
    mr_username = discord.ui.TextInput(label="MafiaReturns username", min_length=2, max_length=32)
    declaration = discord.ui.TextInput(label="Type I AGREE to self-declare", min_length=7, max_length=7)

    def __init__(self, settings, store, city: str):
        super().__init__(timeout=180)
        self.settings, self.store, self.city = settings, store, city

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return
        if self.declaration.value.strip().upper() != "I AGREE":
            await interaction.response.send_message("Type I AGREE to confirm your own MR identity.", ephemeral=True)
            return
        # The database re-checks the time inside the write transaction.
        await interaction.response.defer(ephemeral=True)
        try:
            p = await asyncio.to_thread(
                self.store.register, self.settings.season_key, interaction.user.id,
                str(self.mr_username.value), self.city, datetime.now(timezone.utc))
        except RegistrationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ **{escape_name(p.mr_username)}** registered for **{p.city}**. "
            "Your claim is self-declared; staff may review identity disputes.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


class CityPicker(discord.ui.View):
    def __init__(self, settings, store):
        super().__init__(timeout=180)
        picker = discord.ui.Select(
            placeholder="Choose your MafiaReturns city",
            options=[discord.SelectOption(label=c, value=c) for c in CITIES])

        async def selected(interaction: discord.Interaction):
            if not permitted_guild(interaction.guild_id, settings.guild_id):
                await interaction.response.send_message("Wrong event server.", ephemeral=True)
                return
            if store.season(settings.season_key).phase(datetime.now(timezone.utc)) not in (
                    "registration", "ready", "live", "paused"):
                await interaction.response.send_message("Registration is not open.", ephemeral=True)
                return
            await interaction.response.send_modal(JoinModal(settings, store, picker.values[0]))

        picker.callback = selected
        self.add_item(picker)


class Dashboard(discord.ui.View):
    def __init__(self, settings, store):
        super().__init__(timeout=None)
        self.settings, self.store = settings, store

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Join", emoji="❄️", style=discord.ButtonStyle.primary,
                       custom_id="snowfall:v1:join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        stage = self.store.season(self.settings.season_key).phase(datetime.now(timezone.utc))
        if stage not in ("registration", "ready", "live", "paused"):
            await interaction.response.send_message("Registration has not opened yet or has closed.", ephemeral=True)
            return
        await interaction.response.send_message("Select your city and declare your MR username:",
                                                view=CityPicker(self.settings, self.store), ephemeral=True)

    @discord.ui.button(label="My Profile", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:profile")
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key, interaction.user.id)
        msg = (f"**{escape_name(p.mr_username)}** — {p.city}\n"
               f"**Claim status:** {p.review_state}\n"
               "Gameplay scores are coming in milestone B.") if p else "Not registered. Click Join."
        await interaction.response.send_message(msg, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:rules")
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(rules_text(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        now = datetime.now(timezone.utc)
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        await interaction.followup.send(embed=dashboard_embed(self.settings, season, now, len(players)),
                                        ephemeral=True)
