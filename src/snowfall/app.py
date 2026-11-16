"""Guild-only Discord application entry point for v0.1.4 group gameplay."""
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
from snowfall.services.world import WorldEngine, THEMES
from snowfall.services.combat import CombatEngine
from snowfall.ui.world import individual_board_text, city_board_text

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
        self._board_updated_at = None

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

    async def _edit_saved_board(self, kind: str, content: str):
        stored = await asyncio.to_thread(self.store.get_published, self.settings.season_key, kind)
        if not stored:
            return
        channel = self.get_channel(stored[0])
        if channel is None:
            channel = await self.fetch_channel(stored[0])
        message = await channel.fetch_message(stored[1])
        await message.edit(content=content, allowed_mentions=discord.AllowedMentions.none())

    @tasks.loop(minutes=1)
    async def refresh_world(self):
        now = datetime.now(timezone.utc)
        try:
            day, _, _ = await asyncio.to_thread(WorldEngine(self.store).tick,
                                                self.settings.season_key, now)
            if self._board_updated_at is None or (
                    now - self._board_updated_at).total_seconds() >= 300:
                players = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                                  self.settings.season_key, 10)
                cities = await asyncio.to_thread(WorldEngine(self.store).standings,
                                                 self.settings.season_key, now)
                for kind, content in (("individual_board",individual_board_text(players)),
                                      ("city_board",city_board_text(cities))):
                    try:
                        await self._edit_saved_board(kind, content)
                    except (discord.HTTPException, ValueError) as exc:
                        log.warning("Could not refresh %s: %s", kind, exc)
                self._board_updated_at = now
            channel_id = self.settings.announcement_channel_id
            state = await asyncio.to_thread(self.store.season, self.settings.season_key)
            if day and channel_id and state.phase(now) in ("live", "paused"):
                key = f"theme_day_{day}"
                if not await asyncio.to_thread(self.store.get_published,
                                               self.settings.season_key, key):
                    channel = self.get_channel(channel_id)
                    if channel is None:
                        channel = await self.fetch_channel(channel_id)
                    if channel.guild.id != self.settings.guild_id:
                        raise ValueError('Announcement channel is outside the dedicated event guild.')
                    msg = await channel.send(
                        f"❄️ **Snowfall Day {day}/7 — {THEMES[day-1]}**\n"
                        "Today's boss and each city's fortress are ready! "
                        "Use `/snow world` for the full challenge.",
                        allowed_mentions=discord.AllowedMentions.none())
                    await asyncio.to_thread(self.store.record_published,
                                            self.settings.season_key, 0, key,
                                            channel_id, msg.id, now)
        except (discord.HTTPException, ValueError, RuntimeError) as exc:
            log.exception("World scheduler issue: %s", exc)

    @refresh_world.before_loop
    async def before_refresh_world(self):
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
