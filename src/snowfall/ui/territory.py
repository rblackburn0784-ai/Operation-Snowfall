"""One-message private six-city War Room with a selectable map and days.

City and day selectors are READ-ONLY. All territory, rivalry and collaboration
statistics derive from recorded actions; the UI cannot claim land directly.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import discord

from snowfall.db.store import CITIES
from snowfall.graphics import delivery
from snowfall.graphics.territory_cards import (
    territory_map_card, city_banners_card, city_territory_card,
)
from snowfall.practice import pin
from snowfall.services.territory import CITY_STYLE, TerritoryEngine, TerritoryError
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now():
    return datetime.now(timezone.utc)


def _safe(value):
    return discord.utils.escape_markdown(str(value)).replace("@", "＠")


def _owner_name(owner):
    return _safe(owner) if owner else "Neutral / tied"


def territory_text(board, *, page="map", city=None, rivalries=()) -> str:
    """Text-first summaries; all statements are explicit about honorary status."""
    city = city or board.viewer_city
    my = board.banner(city)
    top = (f"🗺️ **CITY WARS — DAY {board.day if board.day else '—'}/7**"
           f" · {board.phase.upper()}\n"
           "**Fictional territory map — honorary only, individual prizes unchanged.**")
    if board.day is None:
        return (top + "\nThe districts activate when the event host starts the "
                "seven-day battle. Until then, city banners are available to inspect.")

    if page == "banners":
        lines = [top, "\n🚩 **The Six City Banners**"]
        for entry in board.banners:
            lines.append(f"**{entry.emblem} {entry.city}** — {_safe(entry.motto)}\n"
                         f"  {len(board.held(entry.city))} districts held · "
                         f"{entry.active} active contributors · "
                         f"{entry.rally_marks} rally marks")
        lines.append("\n*City crests and honours are cosmetic, not purchasable advantages.*")
    elif page == "matchups":
        lines = [top, "\n⚔️ **Daily City Rivalry Challenges**"]
        for fight in board.matches:
            lines.append(
                f"**{fight.city_a} vs {fight.city_b}**\n"
                f"  🤝 Rally {fight.rally_a}–{fight.rally_b} marks "
                f"→ **{_owner_name(fight.rally_owner)}** controls {_safe(fight.rally_district)}\n"
                f"  🎯 Scored hits {fight.hits_a}–{fight.hits_b}, "
                f"throws {fight.throws_a}–{fight.throws_b} "
                f"→ **{_owner_name(fight.duel_owner)}** controls {_safe(fight.duel_district)}")
        lines.append("\n*A tie or 0–0 leaves the frontier neutral. "
                     "Each city's opponent rotates daily.*")
    elif page == "missions":
        fight = board.match(city)
        lines = [top, f"\n🤝 **{city} — Collaborative Operations**"]
        if fight:
            lines.append(f"Today's designated rival: **{fight.opponent(city)}**.")
        # Only the registered player's crew has the personal three-goal panel.
        if city == board.viewer_city:
            for mission in board.missions:
                lines.append(f"{'✅' if mission.complete else '▫️'} **{mission.name}** — "
                             f"{mission.progress}/{mission.target}\n  {_safe(mission.description)}")
        else:
            lines.append(f"🏙️ **{my.mission_name}** — "
                         f"{my.mission_progress}/{my.mission_target} "
                         f"({'Complete' if my.mission_complete else 'In progress'})")
            lines.append("Detailed crew and ambush objectives are shown for your own registered city.")
        lines.append("\n*No new points, items, snowflakes or paid rewards for these missions.*")
    elif page == "rivals":
        lines = [top, f"\n📊 **{city} — Season-to-Date Cross-City Statistics**"]
        for rival in rivalries:
            lines.append(f"**vs {rival.opponent}:** {rival.throws} throws, "
                         f"{rival.hits} hits, {rival.damage_dealt} damage, "
                         f"{rival.knockouts} KOs\n"
                         f"  ↩️ Received: {rival.hits_received} hits, "
                         f"{rival.damage_received} damage, "
                         f"{rival.knockouts_received} KOs")
        lines.append("\n*Statistics come from actual completed PvP attacks; "
                     "they cannot grant district bonuses.*")
    elif page == "city":
        held = board.held(city)
        home = next(d for d in board.districts if d.key == f"home:{city}")
        lines = [top, f"\n🚩 **{my.emblem} {city} — {_safe(my.motto)}**",
                 f"Home stronghold: **{my.home_district}** "
                 f"({'Claimed' if home.owner else 'Neutral'}) "
                 f"· Crew quorum {my.active}/{my.stronghold_quorum}",
                 f"**{len(held)} honorary districts held** · {my.rally_marks} rally marks "
                 f"· {my.active}/{my.registered} active city members",
                 f"City mission: **{_safe(my.mission_name)}** "
                 f"{my.mission_progress}/{my.mission_target}",
                 ("Controlled: " + ", ".join(_safe(x.name) for x in held)) if held
                 else "No districts controlled yet — all honours are earned from genuine daily activity."]
        fight = board.match(city)
        if fight:
            lines.append(f"Daily match: **{fight.opponent(city)}** · "
                         f"Rally: {fight.rally_a}–{fight.rally_b} · "
                         f"Scored hits: {fight.hits_a}–{fight.hits_b}")
        lines.append("\n*Inspect cities via the dropdown. No city can purchase or manually claim territory.*")
    else:
        lines = [top, "\n🏙️ **Daily District Map — 12 Honorary Districts**"]
        for entry in board.banners:
            home = next(x for x in board.districts if x.key == f"home:{entry.city}")
            lines.append(f"{entry.emblem} **{entry.city}** — {_safe(home.name)} "
                         f"({'Claimed' if home.owner else 'Neutral'}) "
                         f"· {len(board.held(entry.city))} districts")
        neutral = sum(d.owner is None for d in board.districts)
        lines.append(f"\n**{neutral} neutral districts** · "
                     f"{sum(d.owner is not None for d in board.districts)} claimed")
        lines.append("Use **Daily Matchups** for the three cross-city fronts, "
                     "or select a city to inspect its banner and operations.")
    return "\n".join(lines)[:1960]


async def show_territory(interaction, settings, store, owner_id: int, *,
                         page="map", city=None, day=None, deferred=False):
    settings, store = pin(settings, store)
    if not deferred:
        await interaction.response.defer()
    try:
        engine = TerritoryEngine(store)
        board = await asyncio.to_thread(engine.board, settings.season_key,
                                        owner_id, _now(), day=day)
        selected_city = city if city in CITIES else board.viewer_city
        rivalries = ()
        if page == "rivals":
            rivalries = await asyncio.to_thread(engine.rivalries,
                                                 settings.season_key, owner_id,
                                                 selected_city)
        view = TerritoryView(settings, store, owner_id, board,
                             page=page, city=selected_city)
        if page == "banners":
            def render():
                return city_banners_card(board)
        elif page in ("city", "missions"):
            def render():
                return city_territory_card(board, selected_city)
        else:
            def render():
                return territory_map_card(board, highlighted_city=selected_city)
        await delivery.edit_result(interaction,
                                   territory_text(board, page=page, city=selected_city,
                                                  rivalries=rivalries),
                                   view, render,
                                   alt=f"Day {board.day or 'upcoming'} six-city "
                                       "honorary territory map and control status")
    except (TerritoryError, ValueError, sqlite3.Error) as exc:
        fallback = TerritoryView(settings, store, owner_id)
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}", embed=None, attachments=[], view=fallback,
            allowed_mentions=discord.AllowedMentions.none())


class TerritoryView(MenuView):
    def __init__(self, settings, store, owner_id, board=None, *,
                 page="map", city=None):
        super().__init__(settings, store, owner_id)
        self.page = page
        self.day = board.day if board is not None else None
        self.selected_city = city or (board.viewer_city if board else None)
        options = [discord.SelectOption(
            label=city_name,
            value=city_name,
            description=CITY_STYLE[city_name][1],
            default=city_name == self.selected_city)
            for city_name in CITIES]
        picker = discord.ui.Select(placeholder="Choose a city to inspect",
                                   options=options, row=0, min_values=1, max_values=1)
        async def choose_city(interaction):
            await show_territory(interaction, self.settings, self.store, self.owner_id,
                                 page="city", city=picker.values[0], day=self.day)
        picker.callback = choose_city
        self.add_item(picker)
        if board is not None and board.current_day is not None:
            choices = [discord.SelectOption(
                label=f"Event Day {n}" + (" (Current)" if n == board.current_day else ""),
                value=str(n), default=n == self.day)
                for n in range(1, board.current_day + 1)]
            days = discord.ui.Select(placeholder="Inspect a finished or current day",
                                     options=choices, row=1)
            async def choose_day(interaction):
                await show_territory(interaction, self.settings, self.store, self.owner_id,
                                     page=self.page, city=self.selected_city,
                                     day=int(days.values[0]))
            days.callback = choose_day
            self.add_item(days)

    @discord.ui.button(label="Territory Map", emoji="🗺️",
                       style=discord.ButtonStyle.primary, row=2)
    async def map(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             day=self.day)

    @discord.ui.button(label="Daily Matchups", emoji="⚔️",
                       style=discord.ButtonStyle.secondary, row=2)
    async def matchups(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             page="matchups", day=self.day)

    @discord.ui.button(label="My City", emoji="🏙️",
                       style=discord.ButtonStyle.success, row=2)
    async def my_city(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             page="city", day=self.day)

    @discord.ui.button(label="City Missions", emoji="🤝",
                       style=discord.ButtonStyle.success, row=2)
    async def missions(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             page="missions", day=self.day)

    @discord.ui.button(label="City Banners", emoji="🚩",
                       style=discord.ButtonStyle.secondary, row=3)
    async def banners(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             page="banners", day=self.day)

    @discord.ui.button(label="Rivalry Statistics", emoji="📊",
                       style=discord.ButtonStyle.secondary, row=3)
    async def rivalries(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             page="rivals", city=self.selected_city, day=self.day)

    @discord.ui.button(label="City HQ", emoji="🏙️",
                       style=discord.ButtonStyle.secondary, row=3)
    async def headquarters(self, interaction, _):
        from snowfall.ui.community import show_city
        await show_city(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Refresh", emoji="🔄",
                       style=discord.ButtonStyle.secondary, row=3)
    async def refresh(self, interaction, _):
        await show_territory(interaction, self.settings, self.store, self.owner_id,
                             page=self.page, city=self.selected_city, day=self.day)

    @discord.ui.button(label="Game Menus", emoji="🎮",
                       style=discord.ButtonStyle.secondary, row=4)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠",
                       style=discord.ButtonStyle.secondary, row=4)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
