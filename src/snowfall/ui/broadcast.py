"""Single-post leaderboard and restart-safe stage announcements for two channels."""
from __future__ import annotations

import asyncio
from datetime import datetime

import discord

from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine, THEMES
from snowfall.services.boss_personality import phase_announcement, reached_phases
from snowfall.services.broadcast import (
    daily_announcement, registration_announcement, waiting_announcement,
    completed_announcement, boss_defeated_announcement, boss_is_defeated,
    world_snapshot,
)
from snowfall.ui.world import city_board_text, individual_board_text


class BroadcastPublisher:
    """Only one publisher per Discord client; both scheduler and admin share its lock."""

    def __init__(self, bot, settings, store):
        self.bot, self.settings, self.store = bot, settings, store
        self._lock = asyncio.Lock()

    async def _get_channel(self, channel_id: int):
        if not channel_id:
            raise ValueError("The broadcast channel ID is not configured.")
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)
        if getattr(getattr(channel, "guild", None), "id", None) != self.settings.guild_id:
            raise ValueError("Broadcast channel is not in the configured event server.")
        if not hasattr(channel, "send") or not hasattr(channel, "fetch_message"):
            raise ValueError("Broadcast target must be a channel where messages can be sent.")
        return channel

    async def _fetch_existing(self, channel, kind):
        saved = await asyncio.to_thread(self.store.get_published,
                                        self.settings.season_key, kind)
        if not saved or saved[0] != channel.id:
            return None
        try:
            return await channel.fetch_message(saved[1])
        except discord.NotFound:
            return None

    async def _recover_existing(self, channel, marker):
        """Recover a sent notice after process death before the message ID was saved."""
        try:
            async for message in channel.history(limit=100):
                if message.author.id != self.bot.user.id:
                    continue
                if marker in (message.content or ""):
                    return message
                if any(marker in (e.footer.text or "") for e in message.embeds):
                    return message
        except (discord.Forbidden, AttributeError):
            # Missing Read Message History does not prevent fresh delivery.
            return None
        return None

    @staticmethod
    def _leaderboard_embed(settings, state, now, players, cities, boss_text, forts_text):
        phase = state.phase(now)
        day = state.day(now)
        if phase in ("closed", "finalized"):
            stage = "Seven-day competition complete — final standings pending review"
        elif day:
            stage = f"Day **{day}/7** — **{THEMES[day-1]}**"
        elif phase == "registration":
            stage = "Registration is open"
        elif phase == "ready":
            stage = "Awaiting host kickoff"
        else:
            stage = "Registration opens seven days before kickoff"
        description = (f"{stage} • Phase: **{phase.upper()}**\n"
                       "Individual rankings determine prizes. City standings are honorary only.")
        embed = discord.Embed(title=("🧪 TEST / NO PRIZES • LEADERBOARD" if settings.is_test else
                                     "❄️ OPERATION SNOWFALL • LEADERBOARD"),
                              description=description, colour=discord.Colour.from_rgb(91, 169, 214),
                              timestamp=now)
        indiv = individual_board_text(players).split("\n", 1)
        embed.add_field(name="🏆 Top 10 — Individual Championship",
                        value=indiv[1] if len(indiv)>1 else "No scoring players yet.",
                        inline=False)
        # Both fields fit in the Discord embed 1024-character field limit.
        city = city_board_text(cities).split("\n", 2)
        embed.add_field(name="🏙️ City Standings — No City Prizes",
                        value=city[2] if len(city)>2 else "No city rankings yet.",
                        inline=False)
        embed.add_field(name="☃️ Today's Snow Don", value=boss_text, inline=True)
        embed.add_field(name="🏰 Siege Progress", value=forts_text, inline=True)
        embed.set_footer(text=f"Auto-refresh every 5 minutes • {settings.season_key} • "
                         f"Snowfall marker:leaderboard:{settings.season_key}")
        return embed

    async def update_leaderboard(self, now: datetime):
        """Edit one saved message; create only if none exists or it was deleted."""
        if not self.settings.leaderboard_channel_id:
            return None
        async with self._lock:
            channel = await self._get_channel(self.settings.leaderboard_channel_id)
            state = await asyncio.to_thread(self.store.season, self.settings.season_key)
            players = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                              self.settings.season_key, 10)
            cities = await asyncio.to_thread(WorldEngine(self.store).standings,
                                             self.settings.season_key, now)
            day = state.day(now)
            if day is None and state.phase(now) in ("closed", "finalized"):
                day = 7
            # WorldEngine tick and city standings may have seeded the day's state.
            boss, forts = await asyncio.to_thread(world_snapshot, self.store,
                                                  self.settings.season_key, day)
            embed = self._leaderboard_embed(self.settings, state, now, players, cities,
                                            boss, forts)
            existing = await self._fetch_existing(channel, "leaderboard")
            if existing is None:
                existing = await self._fetch_existing(channel, "individual_board")
            if existing is None:
                marker = f"Snowfall marker:leaderboard:{self.settings.season_key}"
                existing = await self._recover_existing(channel, marker)
            if existing is not None:
                message = await existing.edit(content=None, embed=embed,
                                              allowed_mentions=discord.AllowedMentions.none())
            else:
                message = await channel.send(embed=embed,
                                             allowed_mentions=discord.AllowedMentions.none())
            saved = await asyncio.to_thread(self.store.get_published,
                                            self.settings.season_key, "leaderboard")
            if saved != (channel.id, message.id):
                await asyncio.to_thread(self.store.record_published,
                                        self.settings.season_key, 0, "leaderboard",
                                        channel.id, message.id, now)
            # Retire the obsolete second board, if it was posted in this channel.
            city_board = await asyncio.to_thread(self.store.get_published,
                                                 self.settings.season_key, "city_board")
            if city_board and city_board[0] == channel.id and city_board[1] != message.id:
                try:
                    obsolete = await channel.fetch_message(city_board[1])
                    await obsolete.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
            return message

    async def _notice(self, kind: str, content: str, now: datetime,
                      *, refresh_existing: bool = False):
        """At-most-once normal delivery; recover an orphaned message after a crash."""
        channel = await self._get_channel(self.settings.announcement_channel_id)
        marker = f"Snowfall marker:{self.settings.season_key}:{kind}"
        content = f"{content}\n\n-# {marker}"
        existing = await self._fetch_existing(channel, kind)
        if existing is None:
            existing = await self._recover_existing(channel, marker)
        if existing is not None and not refresh_existing:
            saved = await asyncio.to_thread(self.store.get_published,
                                            self.settings.season_key, kind)
            if saved != (channel.id, existing.id):
                await asyncio.to_thread(self.store.record_published,
                                        self.settings.season_key, 0, kind,
                                        channel.id, existing.id, now)
            return existing
        if existing is None:
            message = await channel.send(content,
                                         allowed_mentions=discord.AllowedMentions.none())
        else:
            message = await existing.edit(content=content,
                                          allowed_mentions=discord.AllowedMentions.none())
        await asyncio.to_thread(self.store.record_published,
                                self.settings.season_key, 0, kind,
                                channel.id, message.id, now)
        return message

    async def publish_current_day(self, now: datetime, *, refresh_existing=False):
        if not self.settings.announcement_channel_id:
            return None
        async with self._lock:
            state = await asyncio.to_thread(self.store.season, self.settings.season_key)
            if state.phase(now) not in ("live", "paused"):
                raise ValueError("The event must be live or paused to announce a day.")
            day = state.day(now)
            if day is None:
                raise ValueError("No active event day exists.")
            return await self._notice(f"theme_day_{day}",
                                      daily_announcement(day, paused=state.phase(now)=="paused"),
                                      now, refresh_existing=refresh_existing)

    async def ensure_announcements(self, now: datetime):
        """One registration, seven daily, one boss-defeat/day, one closing post."""
        if not self.settings.announcement_channel_id:
            return
        async with self._lock:
            state = await asyncio.to_thread(self.store.season, self.settings.season_key)
            phase = state.phase(now)
            if phase == "registration":
                await self._notice("registration_open",
                                   registration_announcement(state.planned_start,
                                                             self.settings.event_name), now)
            elif phase == "ready":
                await self._notice("host_kickoff_pending",
                                   waiting_announcement(self.settings.event_name), now)
            elif phase in ("live", "paused"):
                day = state.day(now)
                if day is not None:
                    await self._notice(f"theme_day_{day}",
                                       daily_announcement(day, paused=phase=="paused"), now)
                    # Avoid a burst of all threshold notices if the boss falls
                    # between scheduler ticks. The defeat announcement wins.
                    defeated = await asyncio.to_thread(boss_is_defeated, self.store,
                                                        self.settings.season_key, day)
                    if defeated:
                        await self._notice(f"boss_defeated_day_{day}",
                                           boss_defeated_announcement(day), now)
                    else:
                        phases = await asyncio.to_thread(reached_phases, self.store,
                                                         self.settings.season_key, day)
                        for phase_threshold in phases:
                            await self._notice(f"boss_phase_{day}_{phase_threshold}",
                                               phase_announcement(day, phase_threshold), now)
            elif phase in ("closed", "finalized"):
                await self._notice("season_concluded",
                                   completed_announcement(self.settings.event_name), now)
