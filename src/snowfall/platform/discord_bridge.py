"""Opt-in separate Discord TEST bot using canonical identities and shared PostgreSQL.

Never imported by the live /snow worker. Does not have a production token.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import discord
from discord import app_commands

from snowfall.db.postgres import PostgresStore
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityError, IdentityRepository
from snowfall.platform.staging import STAGING_ENVIRONMENT, STAGING_PROJECT, database_url

WEB_URL = "https://snowfall-web-qa-staging.up.railway.app"
ID_PATTERN = re.compile(r"[1-9][0-9]{0,18}\Z")


class DiscordBridgeGateway:
    """Only the verified interaction's Discord ID may select an actor."""

    def __init__(self, identity, game, *, verification=None):
        self.identity, self.game = identity, game
        self.verification = verification

    def principal(self, discord_id: int) -> int:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise IdentityError("Invalid Discord user ID")
        return self.identity.principal_for_discord(str(discord_id))

    def me(self, discord_id: int):
        return self.game.me(self.principal(discord_id))

    def register(self, discord_id: int, username: str, city: str):
        return self.game.register(self.principal(discord_id), username, city)

    def ready(self, discord_id: int):
        return self.game.ready(self.principal(discord_id))

    def targets(self, discord_id: int):
        return self.game.targets(self.principal(discord_id))

    def throw(self, discord_id: int, target: str, style: str, interaction_id: int):
        if not isinstance(target, str) or not ID_PATTERN.fullmatch(target):
            raise ValueError("Enter a player ID shown by /snowbridge targets")
        if int(target) >= 2**63:
            raise ValueError("Invalid player ID")
        return self.game.throw(self.principal(discord_id), int(target), style,
                               "discord-bridge:" + str(interaction_id))

    def boss(self, discord_id: int, interaction_id: int):
        return self.game.boss(self.principal(discord_id),
                              "discord-bridge:" + str(interaction_id))

    def siege(self, discord_id: int, interaction_id: int):
        return self.game.siege(self.principal(discord_id),
                               "discord-bridge:" + str(interaction_id))

    def inventory(self, discord_id: int):
        return self.game.inventory(self.principal(discord_id))

    def progress(self, discord_id: int):
        return self.game.progress(self.principal(discord_id))

    def craft(self, discord_id: int, item: str, interaction_id: int):
        """Crafting uses the official shared economy transaction and ID."""
        if item not in ("cocoa", "fort", "mittens", "bomb"):
            raise ValueError("Use cocoa, fort, mittens or bomb")
        return self.game.craft(self.principal(discord_id), item,
                               "discord-bridge:" + str(interaction_id))

    def verify(self, discord_id: int):
        """Proof requires an actual Discord interaction from this user."""
        if self.verification is None:
            raise ValueError("Verification is only available on the unified QA game worker")
        return self.verification.from_discord(discord_id)

    def leaderboard(self):
        return self.game.leaderboard(limit=10)


class SnowBridgeGroup(app_commands.Group):
    def __init__(self, gateway, guild_id: int):
        super().__init__(name="snowbridge", description="Linked web and Discord staging game")
        self.gateway, self.guild_id = gateway, guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "Use the dedicated Snowfall QA server.", ephemeral=True)
            return False
        return True

    async def _action(self, interaction: discord.Interaction, method, *args):
        await interaction.response.defer(ephemeral=True)
        try:
            return await asyncio.to_thread(method, interaction.user.id, *args)
        except ValueError as exc:
            await interaction.followup.send("⚠️ " + str(exc), ephemeral=True)
        except Exception:
            logging.getLogger(__name__).error(
                "Canonical Discord gameplay unavailable; refusing action")
            await interaction.followup.send(
                "⚠️ Shared game temporarily unavailable. No new action was recorded. "
                "Please check your progress before retrying.", ephemeral=True)
        return None

    @app_commands.command(name="link", description="How to link Discord and Underworld")
    async def link(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Open " + WEB_URL +
            " and sign in through Underworld, then select Link Discord account. "
            "Discord will verify you through OAuth. Never share passwords or tokens.",
            ephemeral=True)

    @app_commands.command(name="profile", description="View your shared Snowfall score")
    async def profile(self, interaction: discord.Interaction):
        p = await self._action(interaction, self.gateway.me)
        if p is None:
            return
        if not p["registered"]:
            await interaction.followup.send(
                "Register using /snowbridge register or on the website.", ephemeral=True)
            return
        msg = (discord.utils.escape_markdown(p["mr_username"]) + " (" + p["city"] +
               ")\nPoints: " + str(p["score"]) +
               " | Snowballs: " + str(p["resources"]["snowballs"]) +
               " | Snowflakes: " + str(p["resources"]["snowflakes"]))
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="register", description="Register an official linked game player")
    @app_commands.choices(city=[
        app_commands.Choice(name=name, value=name)
        for name in ("Chicago", "New York", "Detroit", "Philadelphia",
                     "Las Vegas", "Los Angeles")
    ])
    async def register(self, interaction: discord.Interaction, username: str, city: str):
        result = await self._action(interaction, self.gateway.register, username, city)
        if result is not None:
            await interaction.followup.send("Registered " +
                discord.utils.escape_markdown(result["mr_username"]) + " in " +
                result["city"], ephemeral=True)

    @app_commands.command(name="ready", description="Make yourself eligible for rival attacks")
    async def ready(self, interaction: discord.Interaction):
        if await self._action(interaction, self.gateway.ready) is not None:
            await interaction.followup.send("Ready for rivals.", ephemeral=True)

    @app_commands.command(name="targets", description="List opponents and their player IDs")
    async def targets(self, interaction: discord.Interaction):
        rivals = await self._action(interaction, self.gateway.targets)
        if rivals is None:
            return
        lines = [discord.utils.escape_markdown(r["mr_username"]) + " (" + r["city"] +
                 ") player ID " + r["player_id"] for r in rivals[:15]]
        await interaction.followup.send("\n".join(lines) or "No targets are eligible.",
                                        ephemeral=True)

    @app_commands.command(name="throw", description="Throw at a player ID from /snowbridge targets")
    @app_commands.choices(style=[
        app_commands.Choice(name=n, value=n)
        for n in ("quick", "standard", "power", "golden")
    ])
    async def throw(self, interaction: discord.Interaction, target_id: str, style: str):
        r = await self._action(interaction, self.gateway.throw, target_id, style,
                               interaction.id)
        if r is not None:
            await interaction.followup.send(
                ("Hit! " if r["hit"] else "Missed! ") +
                str(r["points_awarded"]) + " points." +
                (" Duplicate replay." if r["repeated"] else ""), ephemeral=True)

    @app_commands.command(name="boss", description="Damage the shared Snow Don")
    async def boss(self, interaction: discord.Interaction):
        r = await self._action(interaction, self.gateway.boss, interaction.id)
        if r is not None:
            await interaction.followup.send("Snow Don damage: " +
                str(r["damage"]) + ".", ephemeral=True)

    @app_commands.command(name="siege", description="Contribute to your shared city siege")
    async def siege(self, interaction: discord.Interaction):
        r = await self._action(interaction, self.gateway.siege, interaction.id)
        if r is not None:
            await interaction.followup.send("Siege damage: " +
                str(r["damage"]) + ".", ephemeral=True)

    @app_commands.command(name="progress", description="Compare your official web and Discord progress")
    async def progress(self, interaction: discord.Interaction):
        result = await self._action(interaction, self.gateway.progress)
        if result is None:
            return
        if not result["registered"]:
            await interaction.followup.send(
                "Link your account and register your Snowfall character first.",
                ephemeral=True)
            return
        name = discord.utils.escape_markdown(result["mr_username"])
        await interaction.followup.send(
            "❄️ **Shared progress — " + name + "**\n" +
            "Canonical player: `" + result["player_id"] + "`\n" +
            "Score: **" + str(result["score"]) + "** · " +
            "Snowballs: **" + str(result["snowballs"]) + "** · " +
            "Snowflakes: **" + str(result["snowflakes"]) + "**\n" +
            "Snow Don: **" + str(result["boss_hp"]) + "/" +
            str(result["boss_max_hp"]) + " HP**\n" +
            "These figures use the same database as " + WEB_URL,
            ephemeral=True)

    @app_commands.command(name="verify", description="Prove your Discord and web progress use the same character")
    async def verify(self, interaction: discord.Interaction):
        result = await self._action(interaction, self.gateway.verify)
        if result is None:
            return
        current = result.get("current", {})
        await interaction.followup.send(
            "✅ **Verified Discord ↔ Web character**\n" +
            "Canonical player: `" + result["player_id"] + "`\n" +
            "Points: **" + str(current.get("score", 0)) +
            "** · Snowflakes: **" + str(current.get("snowflakes", 0)) +
            "** · Snowballs: **" + str(current.get("snowballs", 0)) +
            "**\nSnow Don: **" + str(current.get("boss_hp", 0)) + "/" +
            str(current.get("boss_max_hp", 0)) + "** HP\n" +
            "Discord gameplay events in this check: **" +
            str(result["discord_action_count"]) + "**.\n" +
            ("Website activity has also been read by Discord.\n"
             if result["web_gameplay_seen_by_discord"] else "") +
            "Return to Snowfall Web and press **Check shared progress**. "
            "Only actual game actions will count as gameplay proof.",
            ephemeral=True)

    @app_commands.command(name="craft", description="Craft equipment in the shared winter economy")
    @app_commands.choices(item=[
        app_commands.Choice(name=name, value=name)
        for name in ("cocoa", "fort", "mittens", "bomb")
    ])
    async def craft(self, interaction: discord.Interaction, item: str):
        result = await self._action(interaction, self.gateway.craft, item, interaction.id)
        if result is not None:
            await interaction.followup.send(
                "⚒️ " + str(result["text"]) +
                (" (replayed)" if result["repeated"] else ""),
                ephemeral=True)

    @app_commands.command(name="inventory", description="Inspect shared game equipment")
    async def inventory(self, interaction: discord.Interaction):
        r = await self._action(interaction, self.gateway.inventory)
        if r is not None:
            await interaction.followup.send(
                "Inventory: " + ", ".join(k + "=" + str(v) for k,v in r.items()
                    if k in ("snowflakes","cocoa","fort","mittens","bomb","golden"))
                , ephemeral=True)

    @app_commands.command(name="leaderboard", description="View shared seasonal leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await asyncio.to_thread(self.gateway.leaderboard)
        except Exception:
            await interaction.followup.send("Leaderboard unavailable.", ephemeral=True)
            return
        lines = [str(i+1) + ". " +
                 discord.utils.escape_markdown(p["mr_username"]) + " — " +
                 str(p["score"]) + " points" for i,p in enumerate(rows)]
        await interaction.followup.send("\n".join(lines) or "No scores yet.",
                                        ephemeral=True)


def validate_bridge_environment(env=None) -> tuple[str, int, str]:
    """Must never run in the production Discord guild or Railway environment."""
    env = os.environ if env is None else env
    if env.get("SNOWFALL_DISCORD_BRIDGE_ENABLED") != "1":
        raise ValueError("Discord bridge is disabled")
    if (env.get("RAILWAY_PROJECT_ID") != STAGING_PROJECT or
            env.get("RAILWAY_ENVIRONMENT_ID") != STAGING_ENVIRONMENT or
            env.get("RAILWAY_ENVIRONMENT_NAME") != "staging"):
        raise ValueError("Bridge refuses non-staging Railway environment")
    token = env.get("SNOWFALL_DISCORD_BRIDGE_TOKEN", "")
    if not token or token == env.get("DISCORD_TOKEN", ""):
        raise ValueError("A distinct Discord QA bot token is required")
    guild_id = int(env.get("SNOWFALL_DISCORD_BRIDGE_GUILD_ID", "0"))
    if guild_id <= 0 or str(guild_id) == env.get("SNOWFALL_PRODUCTION_GUILD_ID"):
        raise ValueError("A separate QA Discord guild is required")
    if env.get("SNOWFALL_API_SEASON_KEY") != "web-qa-2026":
        raise ValueError("Requires web-qa-2026 season")
    return token, guild_id, database_url(env.get("SNOWFALL_DATABASE_URL", ""))


class DiscordBridgeBot(discord.Client):
    def __init__(self, gateway: DiscordBridgeGateway, guild_id: int):
        super().__init__(intents=discord.Intents.default(),
                         allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        self.gateway, self.guild_id = gateway, guild_id

    async def setup_hook(self):
        guild = discord.Object(id=self.guild_id)
        self.tree.add_command(SnowBridgeGroup(self.gateway, self.guild_id), guild=guild)
        await self.tree.sync(guild=guild)


def main():
    token, guild_id, dsn = validate_bridge_environment()
    identity = IdentityRepository(dsn)
    identity.check()
    store = PostgresStore(dsn)
    store.initialize()
    store.season("web-qa-2026")
    # Both QA entry points must apply identical starter-resource and
    # fictional-target behaviour, not accidentally diverge by platform.
    from snowfall.platform.staging import StagingGame
    shared = StagingGame(SharedGame(store, "web-qa-2026"))
    DiscordBridgeBot(DiscordBridgeGateway(
        identity, shared), guild_id).run(
            token, log_handler=None)


if __name__ == "__main__":
    main()
