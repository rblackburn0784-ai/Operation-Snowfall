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
from snowfall.ui.dashboard import CityPicker, escape_name, rules_text
from snowfall.graphics.delivery import send_profile, send_champions
from snowfall.ui.navigation import send_main_menu


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
    def __init__(self, settings, store, practice=None):
        super().__init__(name="snow", description="Operation Snowfall player commands")
        self.settings, self.store, self.practice = settings, store, practice

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.practice is not None:
            self.practice.for_interaction(interaction.channel_id)
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Use the dedicated Snowfall event server.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="privacy", description="Read privacy, dispute and data-retention rules")
    async def privacy(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "**Operation Snowfall — Privacy & Fair Play**\n"
            "This is an unofficial MR community game. We collect your declared MR username, "
            "Discord user ID, city, action logs and scores for moderation and rankings. "
            "Other players can see names, cities and points; only staff can access exports "
            "and the full audit trail.\n"
            "You can dispute impersonation and request a data copy or deletion from Kat/staff. "
            "Data is held through the event and appeal/payout window; see the posted "
            "retention policy and organiser for the scheduled deletion date. "
            "No MR passwords or payment data are requested.", ephemeral=True)

    @app_commands.command(name="dashboard", description="Open the new Snowfall main menu")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_main_menu(interaction, self.settings, self.store)

    @app_commands.command(name="menu", description="Open Main Menu → Game Menus → Admin/Test (hosts)")
    async def menu(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_main_menu(interaction, self.settings, self.store)

    @app_commands.command(name="hq", description="Your personal Headquarters, timers and daily progress")
    async def hq(self, interaction: discord.Interaction):
        from snowfall.ui.headquarters import send_headquarters
        await interaction.response.defer(ephemeral=True)
        await send_headquarters(interaction, self.settings, self.store)

    @app_commands.command(name="trophies", description="Your Trophy Cabinet, records and earned titles")
    async def trophies(self, interaction: discord.Interaction):
        from snowfall.ui.trophies import send_cabinet
        await interaction.response.defer(ephemeral=True)
        await send_cabinet(interaction, self.settings, self.store)

    @app_commands.command(name="guide", description="First-time guide to registration and the game")
    async def guide(self, interaction: discord.Interaction):
        from snowfall.ui.headquarters import STEPS, WelcomeTour
        from snowfall.practice import pin
        settings, store = pin(self.settings, self.store)
        first = STEPS[0]
        embed = discord.Embed(title=f"📖 Getting Started — {first[0]} (1/3)",
                              description=first[1], colour=0x6AB3DB)
        await interaction.response.send_message(embed=embed, ephemeral=True,
            view=WelcomeTour(settings, store, interaction.user.id, 0))

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
        await send_profile(
            interaction, _profile(p.mr_username, p.city, p.review_state, resources, total),
            p.mr_username, p.city, resources, total, review=p.review_state,
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

    @app_commands.command(name="champions", description="View provisional individual podium and honorary city leader")
    async def champions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        player_rows = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                              self.settings.season_key, 10)
        city_rows = await asyncio.to_thread(WorldEngine(self.store).standings,
                                            self.settings.season_key, _now())
        final = season.phase(_now()) in ("closed", "finalized")
        label = ("Competition complete; awards require staff verification."
                 if final else "Provisional preview, not an award or prize declaration.")
        winners = individual_board_text(player_rows[:3]) + "\n\n" + city_board_text(city_rows[:3])
        await send_champions(interaction, label + "\n" + winners,
                             player_rows, city_rows, final=final)

    @app_commands.command(name="rules", description="Read event rules and identity policy")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(rules_text(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
