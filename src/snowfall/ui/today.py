"""v0.2.7 personal daily hub and safe, read-only next-step navigation.

All buttons edit the same owner-checked ephemeral message. Quick Play only
opens an existing action menu: the combat, economy and world engines still
validate and transact every actual game action.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import sqlite3

import discord

from snowfall.practice import pin
from snowfall.services.experience import Headquarters, headquarters
from snowfall.services.combat_intel import CombatIntelEngine
from snowfall.services.territory import TerritoryEngine
from snowfall.services.mysteries import MysteryEngine
from snowfall.ui.navigation import MenuView


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _due(value: datetime | None) -> str:
    return f"<t:{int(value.timestamp())}:R>" if value is not None else "Ready"


def today_embed(info: Headquarters, settings, intel=None, wars=None, mystery=None) -> discord.Embed:
    card = discord.Embed(title="📋 Today's Snowfall",
                         colour=discord.Colour.from_rgb(106, 179, 219))
    flag = "🧪 TEST — NO PRIZES" if getattr(settings, "mode", "production") == "practice" else "❄️ LIVE EVENT"
    card.set_footer(text=f"{flag} • v0.2.7 • Personal view")
    if info.player is None:
        card.description = ("**Not registered yet.**\n"
                            "Choose **Do Next** to declare your own MafiaReturns name and city. "
                            "No account password is needed.")
        return card

    name = discord.utils.escape_markdown(info.player.mr_username).replace("@", "＠")
    card.description = (f"**{name}** · {info.player.city} · "
                        f"Day **{info.day or '—'}/7** · **{info.phase.upper()}**\n"
                        f"Season **{info.season_points} pts** · Today **{info.daily_points} pts**")
    if info.day is None:
        card.add_field(name="📅 Event status",
                       value="The host has not opened a live event day. Daily actions are unavailable.",
                       inline=False)
    else:
        claimed = sum(q.claimed for q in info.quests)
        quest_lines = []
        for q in info.quests:
            indicator = "✅" if q.claimed else ("🎁" if q.progress >= q.target else "▫️")
            quest_lines.append(f"{indicator} {q.name} — **{q.progress}/{q.target}**"
                               + (" · claimed" if q.claimed else ""))
        card.add_field(name=f"🎄 Daily missions · {claimed}/{len(info.quests)} claimed",
                       value="\n".join(quest_lines) or "No missions available",
                       inline=False)
        presents = f"Daily present: **{info.daily_gift}**"
        if info.day == 4:
            presents += f"\nBonus present: **{info.bonus_gift}**"
        card.add_field(name="🎁 Presents", value=presents, inline=False)
        if info.world is not None:
            boss_text = ("Disabled by host" if not info.world.boss_enabled else
                         f"{info.world.boss_attempts}/6 attempts")
            card.add_field(name="☃️ World attempts",
                           value=(f"Snow Don: **{boss_text}**\n"
                                  f"City Siege: **{info.world.siege_attempts}/4 attempts**"),
                           inline=True)
        card.add_field(name="🎯 PvP points", value=f"**{info.resources.today_pvp}/300** today",
                       inline=True)
    if wars is not None and wars.day is not None:
        matchup = wars.match(wars.viewer_city)
        if matchup:
            opponent = matchup.opponent(wars.viewer_city)
            my = wars.banner(wars.viewer_city)
            held = len(wars.held(wars.viewer_city))
            card.add_field(
                name="🗺️ City Wars · Honorary",
                value=(f"**{wars.viewer_city} vs {opponent}** today"
                       f" · **{held}** districts held\n"
                       f"🤝 {my.active} city contributors · {my.rally_marks} rally marks"
                       "\nOpen **/snowfun territory** for missions and district control."),
                inline=False)
    if mystery is not None and mystery.case is not None:
        found = sum(c.found for c in mystery.clues)
        card.add_field(
            name=f"🕵️ Day {mystery.day} Christmas Mystery",
            value=(f"**{mystery.case.title}** · {found}/3 clues"
                   + (" · ✅ Solved" if mystery.solved else " · Open case")
                   + ("\n✨ Secret encounter ready!" if mystery.secret_ready else "")
                   + ("\n🎁 Secret memento collected" if mystery.secret else "")
                   + "\nOpen **/snowfun mystery** to investigate."),
            inline=False)
    if intel is not None and intel.revenge_alerts:
        names = ", ".join(discord.utils.escape_markdown(r.name).replace("@", "＠")
                          for r in intel.revenge_alerts[:3])
        card.add_field(name=f"🔔 Revenge alerts · {len(intel.revenge_alerts)}",
                       value=f"{names}\nOpen **/snowfun rivalries** for your private record. "
                             "Eligibility is checked before every attack.",
                       inline=False)
    card.add_field(name="⏱️ Your next timers",
                   value=(f"Snowball: **{_due(info.next_snowball)}**"
                          f" · Throw: **{_due(info.next_throw)}**\n"
                          f"Warmth: **{_due(info.next_warmth)}**"
                          f" · Reset: **{_due(info.next_reset)}**"
                          if info.phase == "live" else
                          "⏸️ Frozen during pause" if info.phase == "paused"
                          else "Daily timers start when the event goes live."),
                   inline=False)
    card.add_field(name="👉 Recommended next", value=info.next_action, inline=False)
    return card


async def show_today(interaction, settings, store, owner_id: int) -> None:
    settings, store = pin(settings, store)
    await interaction.response.defer()
    try:
        info = await asyncio.to_thread(headquarters, store, settings.season_key, owner_id, _now())
        intel = None
        wars = None
        mystery = None
        if info.player is not None and info.phase in ("live", "paused"):
            try:
                intel = await asyncio.to_thread(CombatIntelEngine(store).snapshot,
                                                settings.season_key, owner_id)
            except (ValueError, sqlite3.Error):
                pass
            try:
                wars = await asyncio.to_thread(TerritoryEngine(store).board,
                                               settings.season_key, owner_id, _now())
            except (ValueError, sqlite3.Error):
                pass
            try:
                mystery = await asyncio.to_thread(
                    MysteryEngine(store).snapshot,
                    settings.season_key, owner_id, _now())
            except (ValueError, sqlite3.Error):
                pass
        await interaction.edit_original_response(
            content=None, embed=today_embed(info, settings, intel, wars, mystery), attachments=[],
            view=TodayView(settings, store, owner_id, info),
            allowed_mentions=discord.AllowedMentions.none())
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ Could not load today's progress: {exc}", embed=None, attachments=[],
            view=TodayView(settings, store, owner_id),
            allowed_mentions=discord.AllowedMentions.none())


async def quick_action(interaction, settings, store, owner_id: int,
                       *, route_override: str | None = None) -> None:
    """Navigate only. All scores and inventory remain owned by the original engines."""
    settings, store = pin(settings, store)
    if interaction.user.id != owner_id:
        await interaction.response.send_message("This is another player's private menu.",
                                                ephemeral=True)
        return
    await interaction.response.defer()
    try:
        info = await asyncio.to_thread(headquarters, store, settings.season_key, owner_id, _now())
        route = route_override or info.next_action_route
        if info.player is None and route not in ("join", "guide"):
            route = "join" if info.phase in ("registration", "ready", "live", "paused") else "guide"
        if info.phase != "live" and route in ("fight", "quests", "world", "winter", "arcade"):
            route = "hq"

        card = None
        if route == "join":
            from snowfall.ui.dashboard import CityPicker
            if info.phase not in ("registration", "ready", "live", "paused"):
                route = "guide"
            else:
                view = CityPicker(settings, store, owner_id)
                text = "❄️ Choose your city, then declare your own MR username:"
        if route == "guide":
            from snowfall.ui.headquarters import STEPS, WelcomeTour
            title, description = STEPS[0]
            card = discord.Embed(title=f"📖 Getting Started — {title} (1/3)",
                                 description=description, colour=0x6AB3DB)
            view, text = WelcomeTour(settings, store, owner_id, 0), None
        elif route == "player":
            from snowfall.ui.navigation import PlayerMenu
            view, text = PlayerMenu(settings, store, owner_id), (
                "🛡️ Press **Enter Arena** to volunteer as a target for 36 active hours. "
                "It doesn't cost anything or award points.")
        elif route == "quests":
            from snowfall.services.economy import EconomyEngine
            from snowfall.ui.economy import QuestsMenu, quests_text
            quests = await asyncio.to_thread(EconomyEngine(store).quests, settings.season_key,
                                             owner_id, _now())
            view, text = QuestsMenu(settings, store, owner_id), quests_text(quests)
        elif route == "fight":
            from snowfall.services.combat import CombatEngine
            from snowfall.ui.combat import TargetPicker, RetryView
            targets = await asyncio.to_thread(CombatEngine(store).targets, settings.season_key,
                                              owner_id, _now())
            if targets:
                view = TargetPicker(settings, store, owner_id, targets)
                text = f"🎯 **{len(targets)} eligible rivals.** Choose a target or Recommended Rival."
            else:
                view = RetryView(settings, store, owner_id)
                text = "No available rival targets. Ask rival-city players to use /snow ready."
        elif route == "world":
            from snowfall.services.world import WorldEngine
            from snowfall.ui.world import WorldView, status_text
            state = await asyncio.to_thread(WorldEngine(store).status, settings.season_key,
                                            owner_id, _now())
            view, text = WorldView(settings, store, owner_id), status_text(state)
        elif route == "arcade":
            from snowfall.services.social_arcade import SocialArcadeEngine
            from snowfall.ui.social_arcade import ArcadeHubView, hub_text
            lobby = await asyncio.to_thread(
                SocialArcadeEngine(store).lobby, settings.season_key, owner_id, _now())
            view, text = ArcadeHubView(settings, store, owner_id), hub_text(lobby)
        elif route == "winter":
            from snowfall.services.winter_fun import WinterFunEngine
            from snowfall.ui.winter_fun import WinterActivitiesView, _text
            snapshot = await asyncio.to_thread(WinterFunEngine(store).shop, settings.season_key,
                                               owner_id, _now())
            view, text = WinterActivitiesView(settings, store, owner_id), _text("Activities", snapshot)
        elif route == "rankings":
            from snowfall.ui.navigation import RankingsMenu, _embed
            view = RankingsMenu(settings, store, owner_id)
            card = _embed("🏆 Rankings", "Individual results determine prizes; city awards are honorary.",
                          settings)
            text = None
        elif route == "hq":
            from snowfall.ui.headquarters import HeadquartersView, headquarters_embed
            view = HeadquartersView(settings, store, owner_id)
            card = headquarters_embed(info, settings)
            text = None
        elif route != "join":
            raise ValueError("Unknown recommended action.")
        await interaction.edit_original_response(
            content=text, embed=card, view=view, attachments=[],
            allowed_mentions=discord.AllowedMentions.none())
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ That action is not available: {exc}\nNo game action was taken.",
            embed=None, attachments=[], view=TodayView(settings, store, owner_id),
            allowed_mentions=discord.AllowedMentions.none())


class TodayView(MenuView):
    def __init__(self, settings, store, owner_id, info: Headquarters | None = None):
        super().__init__(settings, store, owner_id)
        if info is not None and (info.player is None or info.phase != "live"):
            for entry in (self.quests, self.fight, self.world, self.winter, self.arcade):
                self.remove_item(entry)

    @discord.ui.button(label="Do Next", emoji="✨", style=discord.ButtonStyle.success)
    async def next(self, interaction, _):
        await quick_action(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Daily Quests", emoji="🎄", style=discord.ButtonStyle.primary)
    async def quests(self, interaction, _):
        await quick_action(interaction, self.settings, self.store, self.owner_id,
                           route_override="quests")

    @discord.ui.button(label="Find a Rival", emoji="🎯", style=discord.ButtonStyle.primary)
    async def fight(self, interaction, _):
        await quick_action(interaction, self.settings, self.store, self.owner_id,
                           route_override="fight")

    @discord.ui.button(label="Snow Don / Siege", emoji="☃️", style=discord.ButtonStyle.primary)
    async def world(self, interaction, _):
        await quick_action(interaction, self.settings, self.store, self.owner_id,
                           route_override="world")

    @discord.ui.button(label="Winter Arcade", emoji="🎮",
                       style=discord.ButtonStyle.success, row=1)
    async def arcade(self, interaction, _):
        await quick_action(interaction, self.settings, self.store, self.owner_id,
                           route_override="arcade")

    @discord.ui.button(label="Winter Activities", emoji="🎄", style=discord.ButtonStyle.secondary, row=1)
    async def winter(self, interaction, _):
        await quick_action(interaction, self.settings, self.store, self.owner_id,
                           route_override="winter")

    @discord.ui.button(label="Headquarters", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def hq(self, interaction, _):
        from snowfall.ui.headquarters import show_headquarters
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Refresh Today", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, _):
        await show_today(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary, row=1)
    async def games(self, interaction, _):
        from snowfall.ui.navigation import show_game
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=2)
    async def home(self, interaction, _):
        from snowfall.ui.navigation import show_home
        await show_home(interaction, self.settings, self.store, self.owner_id)
