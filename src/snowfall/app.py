"""Guild-only Discord application entry point for v0.1.5 graphical presentation."""
from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from snowfall.config import load_settings
from snowfall.core.permissions import permitted_guild
from snowfall.db.store import Store
from snowfall.commands.public import SnowGroup
from snowfall.commands.admin import SnowAdminGroup
from snowfall.ui.dashboard import Dashboard
from snowfall.services.world import WorldEngine
from snowfall.ui.broadcast import BroadcastPublisher

log = logging.getLogger(__name__)


class GuildCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not permitted_guild(interaction.guild_id, self.client.settings.guild_id):
            await interaction.response.send_message(
                "Operation Snowfall only works in its dedicated event server.", ephemeral=True)
            return False
        return True


class SnowfallBot(discord.Client):
    def __init__(self, settings, store):
        intents = discord.Intents.default()
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.store = store
        self.tree = GuildCommandTree(self)
        self.broadcast = BroadcastPublisher(self, settings, store)

    async def setup_hook(self):
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.add_command(SnowGroup(self.settings, self.store), guild=guild)
        self.tree.add_command(SnowAdminGroup(self.settings, self.store), guild=guild)
        # All buttons must have fixed custom_ids and timeout=None so old messages work.
        self.add_view(Dashboard(self.settings, self.store))
        try:
            await self.tree.sync(guild=guild)
        except discord.Forbidden:
            log.error("Discord refused slash-command sync (403 Missing Access) for guild %s. "
                      "Confirm config.toml guild_id is the exact event server ID, "
                      "and that the token's application is installed in that guild "
                      "with bot + applications.commands scopes.", self.settings.guild_id)
            raise

    async def on_ready(self):
        log.info("Connected as %s in dedicated guild %s", self.user, self.settings.guild_id)
        if not self.refresh_world.is_running():
            self.refresh_world.start()
        if not self.refresh_leaderboard.is_running():
            self.refresh_leaderboard.start()

    @tasks.loop(minutes=1)
    async def refresh_world(self):
        now = datetime.now(timezone.utc)
        try:
            await asyncio.to_thread(WorldEngine(self.store).tick, self.settings.season_key, now)
            await self.broadcast.ensure_announcements(now)
        except (discord.HTTPException, ValueError, RuntimeError) as exc:
            log.exception("Daily broadcast scheduler issue: %s", exc)

    @refresh_world.before_loop
    async def before_refresh_world(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def refresh_leaderboard(self):
        try:
            await self.broadcast.update_leaderboard(datetime.now(timezone.utc))
        except (discord.HTTPException, ValueError, RuntimeError) as exc:
            log.exception("Five-minute leaderboard refresh failed: %s", exc)

    @refresh_leaderboard.before_loop
    async def before_refresh_leaderboard(self):
        await self.wait_until_ready()


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    settings = load_settings()
    store = Store(settings.database_path)
    store.initialize()
    store.ensure_season(settings.season_key, settings.starts_at_utc)
    SnowfallBot(settings, store).run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
