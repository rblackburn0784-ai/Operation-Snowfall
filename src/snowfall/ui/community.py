"""Private, mobile-friendly city hub, rivalry board and Snowfall Wire previews."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import logging

import discord

from snowfall.graphics import community_cards
from snowfall.practice import pin
from snowfall.services.community import CommunityEngine, CommunityError
from snowfall.ui.navigation import MenuView, show_game, show_home

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe(text: str, length: int = 48) -> str:
    return discord.utils.escape_markdown(" ".join(str(text).split())[:length]).replace("@", "＠")


def city_overview(info) -> str:
    rank = f"#{info.city_rank}" if info.city_rank else "Unranked"
    data = [f"🏙️ **{_safe(info.city)} — City Headquarters**",
            f"Day **{info.day or '—'}/7** • {_safe(info.theme)}",
            f"🏆 Honorary city rank **{rank}** • "
            f"{info.city_score_x100 / 100:.2f} points • "
            f"{info.city_wins} daily wins",
            f"👥 **{info.members}** registered • "
            f"**{info.participants_today}** active scorers today"]
    if info.city_siege_hp:
        hp, mx = info.city_siege_hp
        data.append(f"🏰 City fortress: **{hp}/{mx} HP**")
    if info.objective:
        obj = info.objective
        data.append(f"🤝 **Today's co-op mission: {obj.name}**\n"
                    f"{obj.detail}\n"
                    f"**{obj.progress}/{obj.target} {obj.unit}** "
                    + ("✅ Complete!" if obj.completed else "• In progress")
                    + f" • Goal size: {obj.roster_scale} members")
    else:
        data.append("🤝 City challenges open when the event begins.")
    if info.leaders:
        data.append("🏅 **Today's leading city contributors**\n" +
                    "\n".join(f"{i}. {_safe(name)} — {points} pts"
                              for i, (name, points) in enumerate(info.leaders, 1)))
    else:
        data.append("🏅 No points scored by your city today yet.")
    data.append("*City challenges and standings are for bragging rights only. "
                "Only individual points determine prizes.*")
    return "\n".join(data)


def rivalries_text(city: str, rivalries) -> str:
    result = [f"🎯 **{_safe(city)} — City Rivalries**",
              "Season-to-date, using actual cross-city PvP events.", ""]
    for entry in rivalries:
        result.append(f"**vs {_safe(entry.opponent)}** — "
                      f"{entry.throws} throws, {entry.hits} hits, "
                      f"{entry.damage_dealt} damage dealt\n"
                      f"↩️ Received {entry.hits_received} hits / "
                      f"{entry.damage_received} damage • KOs {entry.knockouts}–{entry.knockouts_received}")
    result.append("\n*Honorary rivalry statistics: no bonus points or city rewards.*")
    return "\n".join(result)


def mission_text(info) -> str:
    obj = info.objective
    if obj is None:
        return "🤝 **City Mission**\nYour daily city challenge unlocks at the event kickoff."
    percent = min(100, int(100 * obj.progress / max(1, obj.target)))
    return (f"🤝 **{_safe(info.city)} — Cooperative Mission, Day {obj.day}**\n"
            f"**{obj.name}**\n{obj.detail}\n\n"
            f"Progress: **{obj.progress}/{obj.target} {obj.unit}** ({percent}%)\n"
            + ("✅ **Mission cleared!**" if obj.completed else "❄️ Keep working together!")
            + "\n\n*Honorary badge only: does not change city standings, individual points, "
              "items or prize eligibility.*")


async def _city_data(settings, store, user_id):
    return await asyncio.to_thread(CommunityEngine(store).headquarters,
                                   settings.season_key, user_id, _now())


async def _show(interaction, settings, store, owner_id: int, mode: str):
    settings, store = pin(settings, store)
    if mode == "wire":
        from snowfall.ui.wire import show_wire
        await show_wire(interaction, settings, store, owner_id)
        return
    await interaction.response.defer()
    view = CityHubView(settings, store, owner_id)
    try:
        info = await _city_data(settings, store, owner_id)
        if mode == "city":
            from snowfall.graphics.delivery import edit_result
            await edit_result(interaction, city_overview(info), view,
                              lambda: community_cards.city_headquarters_card(info),
                              alt=f"City Headquarters for {info.city}")
            return
        if mode == "rivalries":
            content = rivalries_text(info.city, info.rivalries)
        elif mode == "mission":
            content = mission_text(info)
        else:
            content = "Unknown city menu."
        await interaction.edit_original_response(content=content, embed=None,
             attachments=[], view=view, allowed_mentions=discord.AllowedMentions.none())
    except (CommunityError, ValueError, RuntimeError) as exc:
        await interaction.edit_original_response(content=f"⚠️ {exc}", embed=None,
             attachments=[], view=view, allowed_mentions=discord.AllowedMentions.none())


async def show_city(interaction, settings, store, owner_id: int) -> None:
    await _show(interaction, settings, store, owner_id, "city")


async def send_city(interaction, settings, store) -> None:
    """Run after a slash command has deferred with ephemeral=True."""
    settings, store = pin(settings, store)
    try:
        info = await _city_data(settings, store, interaction.user.id)
        text = city_overview(info)
        view = CityHubView(settings, store, interaction.user.id)
        try:
            png = await asyncio.to_thread(community_cards.city_headquarters_card, info)
            embed = discord.Embed(colour=discord.Colour.from_rgb(122, 193, 225))
            embed.set_image(url="attachment://city-hq.png")
            await interaction.followup.send(content=text, embed=embed,
                file=discord.File(BytesIO(png), filename="city-hq.png",
                                  description=f"{info.city} City Headquarters"),
                view=view, ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
        except (OSError, discord.HTTPException, ValueError, MemoryError):
            log.warning("City art upload unavailable; using accessible text", exc_info=True)
            await interaction.followup.send(content=text, view=view, ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
    except CommunityError as exc:
        await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)


class CityHubView(MenuView):
    @discord.ui.button(label="City HQ", emoji="🏙️", style=discord.ButtonStyle.primary)
    async def city(self, interaction, _):
        await _show(interaction, self.settings, self.store, self.owner_id, "city")

    @discord.ui.button(label="Co-op Mission", emoji="🤝", style=discord.ButtonStyle.success)
    async def mission(self, interaction, _):
        await _show(interaction, self.settings, self.store, self.owner_id, "mission")

    @discord.ui.button(label="Rivalries", emoji="🎯", style=discord.ButtonStyle.secondary)
    async def rivalries(self, interaction, _):
        await _show(interaction, self.settings, self.store, self.owner_id, "rivalries")

    @discord.ui.button(label="Snowfall Wire", emoji="🗞️", style=discord.ButtonStyle.secondary)
    async def wire(self, interaction, _):
        await _show(interaction, self.settings, self.store, self.owner_id, "wire")

    @discord.ui.button(label="Territory Map", emoji="🗺️",
                       style=discord.ButtonStyle.primary, row=1)
    async def territory(self, interaction, _):
        from snowfall.ui.territory import show_territory
        await show_territory(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
