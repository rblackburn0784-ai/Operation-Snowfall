"""Discord bot startup. No gameplay is claimed in this foundation build."""
from __future__ import annotations
import discord
from discord import app_commands
from dotenv import load_dotenv
from snowfall.config import load_settings
from snowfall.db.store import Store
from snowfall.commands.public import SnowGroup
from snowfall.commands.admin import SnowAdminGroup
from snowfall.ui.dashboard import Dashboard


class SnowfallBot(discord.Client):
    def __init__(self, settings, store):
        intents = discord.Intents.default()
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.store = store
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.add_command(SnowGroup(self.settings, self.store), guild=guild)
        self.tree.add_command(SnowAdminGroup(self.settings, self.store), guild=guild)
        self.add_view(Dashboard(self.settings, self.store))
        await self.tree.sync(guild=guild)

    async def on_ready(self):
        print(f"Operation Snowfall connected as {self.user}; dedicated guild {self.settings.guild_id}")


def main():
    load_dotenv()
    settings = load_settings()
    store = Store(settings.database_path)
    store.initialize()
    bot = SnowfallBot(settings, store)
    bot.run(settings.token)


if __name__ == "__main__":
    main()
