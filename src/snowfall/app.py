"""One Discord application with channel-scoped, disposable test-day sessions."""
from __future__ import annotations

import logging
import asyncio
import os
import argparse
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from snowfall.config import load_settings
from snowfall.core.permissions import permitted_guild
from snowfall.db.postgres import PostgresStore, make_store
from snowfall.commands.public import SnowGroup
from snowfall.commands.admin import SnowAdminGroup
from snowfall.commands.winter_fun import SnowFunGroup
from snowfall.ui.dashboard import Dashboard
from snowfall.services.world import WorldEngine
from snowfall.ui.broadcast import BroadcastPublisher
from snowfall.ops import backup_sqlite, restore_sqlite
from snowfall.practice import PracticeManager, ScopedSettings, ScopedStore
from snowfall.platform.identity import IdentityError, IdentityRepository

log = logging.getLogger(__name__)


class GuildCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not permitted_guild(interaction.guild_id, self.client.settings.guild_id):
            await interaction.response.send_message(
                "Operation Snowfall only works in its dedicated event server.", ephemeral=True)
            return False
        if self.client.unified_identity is not None:
            command = getattr(interaction.command, "qualified_name", "")
            # Preserve public help, the account-link instructions and host
            # administration. Gameplay cannot create an unlinked second profile.
            public = {"snow privacy", "snow rules", "snow guide", "snowbridge link"}
            if command not in public and not command.startswith("snowadmin "):
                try:
                    await asyncio.to_thread(
                        self.client.unified_identity.principal_for_discord,
                        str(interaction.user.id))
                except IdentityError:
                    await interaction.response.send_message(
                        "🔗 Link your Discord account to your Underworld character "
                        "before playing. Use `/snowbridge link` for instructions.",
                        ephemeral=True)
                    return False
        return True


class SnowfallBot(discord.Client):
    def __init__(self, settings, store):
        intents = discord.Intents.default()
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.store = store
        self.practice = PracticeManager(settings, store)
        self.practice.clean_orphans()
        self.tree = GuildCommandTree(self)
        self.broadcast = BroadcastPublisher(self, settings, store)
        self.unified_identity = None
        self.unified_gateway = None
        if getattr(store, "unified_discord", False):
            # No second bot is started: these commands are registered on the
            # existing Discord Client using the already configured guild/token.
            from snowfall.platform.discord_bridge import DiscordBridgeGateway
            from snowfall.platform.game import SharedGame
            from snowfall.platform.staging import StagingGame
            self.unified_identity = IdentityRepository(store.dsn)
            self.unified_identity.check()
            raw = PostgresStore(store.dsn, practice_root=store.path.parent)
            self.unified_gateway = DiscordBridgeGateway(
                self.unified_identity, StagingGame(SharedGame(raw, settings.season_key)))

    async def setup_hook(self):
        guild = discord.Object(id=self.settings.guild_id)
        routes = (ScopedSettings(self.practice), ScopedStore(self.practice))
        self.tree.add_command(SnowGroup(*routes, practice=self.practice), guild=guild)
        self.tree.add_command(SnowAdminGroup(*routes, practice=self.practice), guild=guild)
        self.tree.add_command(SnowFunGroup(*routes, practice=self.practice), guild=guild)
        if self.unified_gateway is not None:
            from snowfall.platform.discord_bridge import SnowBridgeGroup
            self.tree.add_command(SnowBridgeGroup(
                self.unified_gateway, self.settings.guild_id), guild=guild)

        # /snow already has 25 commands, so this separate shortcut preserves all aliases.
        @app_commands.command(name="cityhq", description="Your city HQ, co-op mission, rivalries and Snowfall Wire")
        async def cityhq(interaction: discord.Interaction):
            from snowfall.ui.community import send_city
            self.practice.for_interaction(interaction.channel_id)
            settings, store = self.practice.selected()
            await interaction.response.defer(ephemeral=True)
            await send_city(interaction, settings, store)

        self.tree.add_command(cityhq, guild=guild)
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
        log.info("[%s] Connected as %s in guild %s, season %s, database %s",
                 self.settings.mode.upper(), self.user, self.settings.guild_id,
                 self.settings.season_key, "PostgreSQL" if getattr(self.store, "backend", "sqlite") == "postgres"
        else self.settings.database_path)
        if not self.refresh_world.is_running():
            self.refresh_world.start()
        if not self.refresh_leaderboard.is_running():
            self.refresh_leaderboard.start()
        if (getattr(self.store, "backend", "sqlite") == "sqlite"
                and not self.backup_loop.is_running()):
            self.backup_loop.start()

    @tasks.loop(minutes=1)
    async def refresh_world(self):
        now = datetime.now(timezone.utc)
        try:
            await asyncio.to_thread(WorldEngine(self.store).tick, self.settings.season_key, now)
            await self.broadcast.ensure_announcements(now)
            await self.broadcast.publish_wire_recaps(now)
        except Exception as exc:
            # SQLite/disk failures must not permanently kill the one-minute loop.
            log.exception("Daily broadcast scheduler issue: %s", exc)

    @refresh_world.before_loop
    async def before_refresh_world(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def refresh_leaderboard(self):
        try:
            await self.broadcast.update_leaderboard(datetime.now(timezone.utc))
        except Exception as exc:
            # Keep retrying after unexpected database or render failures.
            log.exception("Five-minute leaderboard refresh failed: %s", exc)

    @refresh_leaderboard.before_loop
    async def before_refresh_leaderboard(self):
        await self.wait_until_ready()


    @tasks.loop(hours=24)
    async def backup_loop(self):
        try:
            saved = await asyncio.to_thread(backup_sqlite, self.store.path,
                                             self.settings.backup_dir)
            log.info("[%s] Daily backup stored: %s", self.settings.mode, saved)
        except Exception as exc:
            # Preserve the loop if SQLite raises a database-specific exception.
            log.exception("Daily SQLite backup failed: %s", exc)

    @backup_loop.before_loop
    async def before_backup_loop(self):
        await self.wait_until_ready()


def main(argv: list[str] | None = None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Operation Snowfall v0.2.8")
    parser.add_argument("--test", action="store_true", help="Obsolete: use /snowadmin test-start in the main bot")
    parser.add_argument("--backup-now", action="store_true", help="Create a verified backup then exit")
    parser.add_argument("--restore", metavar="BACKUP", help="Offline restore from a verified backup")
    parser.add_argument("--confirm-restore", default="", help="Explicitly type RESTORE")
    parser.add_argument("--simulate", action="store_true", help="Run disposable seven-day simulation")
    args = parser.parse_args(argv)
    if args.test:
        parser.error("Separate test applications are obsolete. Run python bot.py, then "
                     "use /snowadmin test-start in your event server.")
    if args.simulate:
        from snowfall.simulate import run_simulation
        print(run_simulation())
        return
    load_dotenv()
    settings = load_settings()
    store = make_store(settings.database_path)
    mode = os.getenv("SNOWFALL_SHARED_MODE", "").strip().lower()
    if mode:
        from snowfall.platform.unified_discord import (
            UnifiedDiscordStore, validate_unified_environment, verify_qa_database,
        )
        # Direct python bot.py invocations must obey the same safety gates
        # as the Railway entry point.
        dsn = validate_unified_environment(os.environ)
        verify_qa_database(dsn, season=settings.season_key)
        store = UnifiedDiscordStore(dsn, practice_root=settings.database_path.parent)
    if getattr(store, "backend", "sqlite") == "postgres" and (args.restore or args.backup_now):
        parser.error("SQLite backup/restore flags are unavailable for PostgreSQL; use managed PG backups")
    if args.restore:
        restored = restore_sqlite(args.restore, settings.database_path,
                                  confirmation=args.confirm_restore)
        print(f"Restored checked database: {restored}")
        return
    if args.backup_now:
        # Must run BEFORE migrations to preserve the original schema as-is.
        print("Backup:", backup_sqlite(settings.database_path, settings.backup_dir))
        return
    if getattr(store, "backend", "sqlite") == "sqlite" and store.path.is_file():
        import sqlite3
        from contextlib import closing
        from snowfall.db.store import DB_VERSION
        with closing(sqlite3.connect(store.path)) as con:
            old_version = con.execute("PRAGMA user_version").fetchone()[0]
        if old_version < DB_VERSION:
            saved = backup_sqlite(store.path, settings.backup_dir)
            log.info("Pre-migration v%s backup: %s", old_version, saved)
    store.initialize()
    store.ensure_season(settings.season_key, settings.starts_at_utc)
    SnowfallBot(settings, store).run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
