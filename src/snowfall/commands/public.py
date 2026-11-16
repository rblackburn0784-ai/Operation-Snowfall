"""Player slash commands, restricted to the dedicated event server."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands

from snowfall.core.permissions import permitted_guild
from snowfall.services.combat import CombatEngine, CombatError
from snowfall.services.economy import EconomyEngine, EconomyError, ITEM_NAMES
from snowfall.services.world import WorldEngine
from snowfall.ui.world import send_world, city_board_text, individual_board_text
from snowfall.ui.combat import ThrowMenu, send_target_menu
from snowfall.ui.economy import send_inventory, send_quests
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
            "PvP rules: rivals only · 30s cooldown · two scoring hits per target per day.\n"
            "Use `/snow inventory`, `/snow quests` and `/snow present` for Christmas rewards.")


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
            await asyncio.to_thread(CombatEngine(self.store).ready,
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

    @app_commands.command(name="inventory", description="Browse your Christmas equipment and craft items")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_inventory(interaction, self.settings, self.store)

    @app_commands.command(name="craft", description="Craft an item using Snowflakes")
    @app_commands.choices(item=[app_commands.Choice(name=n, value=k)
                                for k, n in ITEM_NAMES.items() if k != "golden"])
    async def craft(self, interaction: discord.Interaction, item: str):
        await self._economy_action(interaction, "craft", item)

    @app_commands.command(name="use", description="Activate equipment in your inventory")
    @app_commands.choices(item=[app_commands.Choice(name=n, value=k)
                                for k, n in ITEM_NAMES.items() if k != "golden"])
    async def use(self, interaction: discord.Interaction, item: str):
        await self._economy_action(interaction, "use", item)

    @app_commands.command(name="guard", description="Raise or lower a defensive guard")
    @app_commands.choices(mode=[app_commands.Choice(name="Raise guard", value="on"),
                                app_commands.Choice(name="Lower guard", value="off")])
    async def guard(self, interaction: discord.Interaction, mode: str):
        await self._economy_action(interaction, "guard", mode)

    async def _economy_action(self, interaction: discord.Interaction, action: str, value: str):
        await interaction.response.defer(ephemeral=True)
        try:
            method = getattr(EconomyEngine(self.store), action)
            result = await asyncio.to_thread(method, self.settings.season_key,
                                             interaction.user.id, value, str(interaction.id), _now())
            await interaction.followup.send("✅ " + result.text, ephemeral=True)
        except EconomyError as exc:
            await interaction.followup.send("⚠️ " + str(exc), ephemeral=True)

    @app_commands.command(name="quests", description="See and claim today's three objectives")
    async def quests(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_quests(interaction, self.settings, self.store)

    @app_commands.command(name="claim", description="Claim a completed daily mission")
    @app_commands.choices(quest=[app_commands.Choice(name="Get your gloves on", value="throws"),
                                 app_commands.Choice(name="Spread the misery", value="rivals"),
                                 app_commands.Choice(name="Community effort", value="community")])
    async def claim(self, interaction: discord.Interaction, quest: str):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await asyncio.to_thread(EconomyEngine(self.store).claim_quest,
                                             self.settings.season_key, interaction.user.id,
                                             quest, _now())
            await interaction.followup.send("✅ " + result.text, ephemeral=True)
        except EconomyError as exc:
            await interaction.followup.send("⚠️ " + str(exc), ephemeral=True)

    @app_commands.command(name="present", description="Open your quest-earned daily mystery present")
    @app_commands.describe(bonus="Day 4: extra non-golden present after completing all 3 quests")
    async def present(self, interaction: discord.Interaction, bonus: bool = False):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await asyncio.to_thread(EconomyEngine(self.store).present,
                                             self.settings.season_key, interaction.user.id,
                                             str(interaction.id), _now(),
                                             "bonus" if bonus else "daily")
            label = ITEM_NAMES.get(result.actual_reward, result.actual_reward.title())
            msg = f"🎁 **+{result.amount} {label}** from your {'bonus' if bonus else 'daily'} gift!"
            if result.actual_reward != result.reward:
                msg += " (+5 Snowflakes replacement for capped/disallowed reward)"
            await interaction.followup.send(msg, ephemeral=True)
        except EconomyError as exc:
            await interaction.followup.send("⚠️ " + str(exc), ephemeral=True)

    @app_commands.command(name="world", description="Open the Snow Don, fortress and theme menu")
    async def world(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_world(interaction, self.settings, self.store)

    @app_commands.command(name="boss", description="Fight the daily Abominable Snow Don")
    async def boss(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_world(interaction, self.settings, self.store)

    @app_commands.command(name="siege", description="Attack your city's daily NPC fortress")
    async def siege(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_world(interaction, self.settings, self.store)

    @app_commands.command(name="leaderboard", description="Individual standings: prizes for people only")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                       self.settings.season_key, 10)
        await interaction.followup.send(individual_board_text(rows), ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="cities", description="Normalized city standings (no city prizes)")
    async def cities(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(WorldEngine(self.store).standings,
                                       self.settings.season_key, _now())
        await interaction.followup.send(city_board_text(rows), ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="rules", description="Read event rules and identity policy")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(rules_text(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
