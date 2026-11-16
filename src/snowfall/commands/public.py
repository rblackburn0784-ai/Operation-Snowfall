"""Player slash commands, restricted to the dedicated event server."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands

from snowfall.core.permissions import permitted_guild
from snowfall.db.store import CITIES
from snowfall.services.combat import CombatEngine, CombatError
from snowfall.ui.combat import ThrowMenu, send_target_menu
from snowfall.ui.dashboard import CityPicker, Dashboard, dashboard_embed, escape_name, rules_text


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _profile(name, city, state, resource, total) -> str:
    ko = f" • 🥶 KO until <t:{int(resource.knockout_until.timestamp())}:R>" if resource.knockout_until else ""
    return (f"**❄️ {escape_name(name)}** — {city}\n"
            f"Identity: {state}\n"
            f"**Snowballs:** {resource.snowballs}/12 • **Warmth:** {resource.warmth}/100"
            f" • **Snowflakes:** {resource.snowflakes}{ko}\n"
            f"**Day {resource.day or '—'} PvP:** {resource.today_pvp}/300"
            f" • **Season points:** {total}\n"
            "Use `/snow ready` to volunteer as a target for the next 36 effective hours.\n"
            "PvP rules: rivals only · 30s cooldown · two scoring hits per target per day.")


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
        now = _now()
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        await interaction.followup.send(
            embed=dashboard_embed(self.settings, season, now, len(players)),
            view=Dashboard(self.settings, self.store), ephemeral=True,
        )

    @app_commands.command(name="join", description="Declare your MafiaReturns username and city")
    async def join(self, interaction: discord.Interaction):
        stage = self.store.season(self.settings.season_key).phase(_now())
        if stage not in ("registration", "ready", "live", "paused"):
            await interaction.response.send_message("Registration is not currently open.", ephemeral=True)
            return
        await interaction.response.send_message("Choose your city, then confirm your MR username:",
                                                view=CityPicker(self.settings, self.store), ephemeral=True)

    @app_commands.command(name="profile", description="Check your warmth, snowballs and PvP points")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key, interaction.user.id)
        if p is None:
            await interaction.followup.send("You are not registered. Use `/snow join`.", ephemeral=True)
            return
        try:
            engine = CombatEngine(self.store)
            resources = await asyncio.to_thread(engine.snapshot, self.settings.season_key,
                                                interaction.user.id, _now())
            total = await asyncio.to_thread(engine.ledger_total, self.settings.season_key,
                                            interaction.user.id)
        except CombatError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(
            _profile(p.mr_username, p.city, p.review_state, resources, total),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="ready", description="Enter the arena and allow rival attacks for 36h")
    async def ready(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            expires = await asyncio.to_thread(CombatEngine(self.store).ready,
                                              self.settings.season_key, interaction.user.id, _now())
        except CombatError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(
            "✅ You've entered the arena! Rivals may now target you for the next "
            "36 hours of **active event time**. No points were awarded.", ephemeral=True,
        )

    @app_commands.command(name="targets", description="Find available rival-city targets")
    async def targets(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_target_menu(interaction, self.settings, self.store)

    @app_commands.command(name="throw", description="Challenge a rival to a snowball fight")
    @app_commands.describe(target="Optional Discord member to challenge; omit to see eligible targets")
    async def throw(self, interaction: discord.Interaction, target: discord.User | None = None):
        await interaction.response.defer(ephemeral=True)
        if target is None:
            await send_target_menu(interaction, self.settings, self.store)
            return
        # A target's live eligibility is re-checked on confirmation inside the engine.
        player = await asyncio.to_thread(self.store.get_player, self.settings.season_key, target.id)
        if player is None:
            await interaction.followup.send("Target has not registered for Snowfall.", ephemeral=True)
            return
        await interaction.followup.send(
            f"🎯 **Target:** {escape_name(player.mr_username)} ({player.city}). Pick a throw:",
            view=ThrowMenu(self.settings, self.store, interaction.user.id,
                           target.id, player.mr_username), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="leaderboard", description="Top individual snowball scorers")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                       self.settings.season_key, 10)
        board = "\n".join(
            f"**{i}.** {escape_name(name)} ({city}): **{score}**"
            for i, (name, city, _uid, score) in enumerate(rows, 1)
        ) or "No registered competitors yet."
        await interaction.followup.send(
            "🏆 **Individual Scoreboard** — personal prizes only\n" + board
            + "\n*City rankings are honorary; boss and siege scores arrive later.*",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="cities", description="Show city registration counts (no city prizes)")
    async def cities(self, interaction: discord.Interaction):
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        counts = {c: 0 for c in CITIES}
        for player in players:
            if player.review_state != "disqualified":
                counts[player.city] += 1
        await interaction.response.send_message(
            "**City registrations** (honorary city contest, individual prizes only):\n"
            + "\n".join(f"{c}: **{n}**" for c, n in counts.items()), ephemeral=True,
        )

    @app_commands.command(name="rules", description="Read event rules and identity policy")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(rules_text(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
