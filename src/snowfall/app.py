"""Guild-only Discord application entry point for foundation v0.1.1."""
from __future__ import annotations

import logging
import discord
from discord import app_commands
from dotenv import load_dotenv

from snowfall.config import load_settings
from snowfall.core.permissions import permitted_guild
from snowfall.db.store import Store
from snowfall.commands.public import SnowGroup
from snowfall.commands.admin import SnowAdminGroup
from snowfall.ui.dashboard import Dashboard

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

    async def setup_hook(self):
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.add_command(SnowGroup(self.settings, self.store), guild=guild)
        self.tree.add_command(SnowAdminGroup(self.settings, self.store), guild=guild)
        # All buttons must have fixed custom_ids and timeout=None so old messages work.
        self.add_view(Dashboard(self.settings, self.store))
        await self.tree.sync(guild=guild)

    async def on_ready(self):
        log.info("Connected as %s in dedicated guild %s", self.user, self.settings.guild_id)


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
