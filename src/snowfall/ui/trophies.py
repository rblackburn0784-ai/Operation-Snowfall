"""Ephemeral Trophy Cabinet, personal combat records and cosmetic title selector.

All UI is owner-checked and test-session pinned by MenuView. Navigating edits
one existing message; the initial slash command sends one private response.
"""
from __future__ import annotations

import asyncio
from io import BytesIO

import discord

from snowfall.graphics import cards, delivery
from snowfall.practice import pin
from snowfall.services.achievements import AchievementEngine, TrophyError
from snowfall.ui.navigation import MenuView, show_home, show_game


async def _cabinet(settings, store, owner_id):
    return await asyncio.to_thread(AchievementEngine(store).cabinet,
                                   settings.season_key, owner_id)


def cabinet_text(cabinet, page: int = 0) -> str:
    """Text fallback includes progress for each locked badge."""
    groups = (cabinet.trophies[:7], cabinet.trophies[7:])
    section = groups[page % len(groups)]
    rows = [f"🏆 **{discord.utils.escape_markdown(cabinet.player_name)} — Trophy Cabinet**",
            f"**Equipped title:** {discord.utils.escape_markdown(cabinet.equipped_title)}",
            f"**Badges:** {cabinet.unlocked_count}/{len(cabinet.trophies)} unlocked\n"]
    for badge in section:
        status = '🏅' if badge.unlocked else '🔒'
        rows.append(f"{status} **{badge.badge}** — {badge.progress}/{badge.target}\n"
                    f"   {badge.description} • Title: *{badge.title}*")
    rows.append("\nCosmetics only. Badges do not change scoring, combat, or prizes.")
    return '\n'.join(rows)


def records_embed(cabinet) -> discord.Embed:
    s = cabinet.records
    e = discord.Embed(title='📊 Personal Combat Records',
                      description=(f"**{discord.utils.escape_markdown(cabinet.player_name)}**"
                                   f" • {discord.utils.escape_markdown(cabinet.equipped_title)}"),
                      colour=discord.Colour.from_rgb(106, 179, 219))
    e.add_field(name='🎯 PvP', value=(f'Throws: **{s.pvp_throws}**\nHits: **{s.pvp_hits}**\n'
                                     f'Accuracy: **{s.accuracy}%**\nCriticals: **{s.critical_hits}**\n'
                                     f'Knockouts: **{s.knockouts}**\n'
                                     f'Unique rivals: **{s.unique_rivals}**\n'
                                     f'Best hit: **{s.best_hit}** damage'), inline=True)
    e.add_field(name='☃️ Group Battles', value=(f'Snow Don attacks: **{s.boss_attacks}**\n'
                                                 f'Boss hits: **{s.successful_boss_hits}**\n'
                                                 f'Shared boss damage: **{s.boss_damage}**\n'
                                                 f'Siege attacks: **{s.siege_attacks}**\n'
                                                 f'Fortress damage: **{s.siege_damage}**'), inline=True)
    e.add_field(name='🎄 Event History', value=(f'Quest claims: **{s.quests}**\n'
                                                f'Mystery gifts: **{s.gifts}**\n'
                                                f'Golden gifts: **{s.golden_gifts}**\n'
                                                f'Active scoring days: **{s.active_days}/7**\n'
                                                f'Hot Chocolates used: **{s.hot_chocolates}**'),
                inline=False)
    e.set_footer(text='Season-scoped event history • No additional prizes')
    return e


async def show_cabinet(interaction, settings, store, owner_id: int, page: int = 0):
    settings, store = pin(settings, store)
    await interaction.response.defer()
    try:
        cab = await _cabinet(settings, store, owner_id)
        view = TrophyCabinet(settings, store, owner_id, page=page)
        await delivery.edit_result(interaction, cabinet_text(cab, page), view,
                                   lambda: cards.trophy_cabinet_card(cab),
                                   alt=f'Trophy Cabinet for {cab.player_name}, '
                                       f'{cab.unlocked_count} badges earned')
    except TrophyError as exc:
        await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                                                 attachments=[], view=TrophyCabinet(settings,
                                                     store, owner_id, page=page))


async def send_cabinet(interaction, settings, store):
    """For already deferred, ephemeral slash commands."""
    settings, store = pin(settings, store)
    try:
        cab = await _cabinet(settings, store, interaction.user.id)
        image = await asyncio.to_thread(cards.trophy_cabinet_card, cab)
        embed = discord.Embed(colour=discord.Colour.from_rgb(106, 179, 219))
        embed.set_image(url='attachment://trophies.png')
        await interaction.followup.send(content=cabinet_text(cab), embed=embed,
            file=discord.File(BytesIO(image), filename='trophies.png',
                              description=f'{cab.unlocked_count} unlocked trophy badges'),
            view=TrophyCabinet(settings, store, interaction.user.id), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, OSError, ValueError, MemoryError) as exc:
        if isinstance(exc, TrophyError):
            message = f'⚠️ {exc}'
        else:
            # Media is always optional; scores and titles are independent.
            try:
                cab = await _cabinet(settings, store, interaction.user.id)
                message = cabinet_text(cab)
            except TrophyError as missing:
                message = f'⚠️ {missing}'
        await interaction.followup.send(message,
            view=TrophyCabinet(settings, store, interaction.user.id), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())


class TrophyCabinet(MenuView):
    def __init__(self, settings, store, owner_id: int, page: int = 0):
        super().__init__(settings, store, owner_id)
        self.page = page

    @discord.ui.button(label='◀ / Next Badges', emoji='🏅', style=discord.ButtonStyle.primary)
    async def page_switch(self, interaction, _):
        await show_cabinet(interaction, self.settings, self.store,
                           self.owner_id, page=1 - self.page)

    @discord.ui.button(label='Combat Records', emoji='📊', style=discord.ButtonStyle.secondary)
    async def records(self, interaction, _):
        await interaction.response.defer()
        try:
            cab = await _cabinet(self.settings, self.store, self.owner_id)
            await interaction.edit_original_response(content=None, attachments=[],
                    embed=records_embed(cab),
                    view=TrophyCabinet(self.settings, self.store, self.owner_id,
                                       page=self.page))
        except TrophyError as exc:
            await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                    attachments=[], view=self)

    @discord.ui.button(label='Equip Title', emoji='🎩', style=discord.ButtonStyle.success)
    async def titles(self, interaction, _):
        await interaction.response.defer()
        try:
            cab = await _cabinet(self.settings, self.store, self.owner_id)
            await interaction.edit_original_response(content=(
                f'🎩 **Select your cosmetic title**\nCurrently equipped: **{cab.equipped_title}**\n'
                'Only unlocked titles appear. Cosmetic only; no score or prize bonuses.'),
                embed=None, attachments=[],
                view=TitleChooser(self.settings, self.store, self.owner_id, cab))
        except TrophyError as exc:
            await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                    attachments=[], view=self)

    @discord.ui.button(label='Headquarters', emoji='🏠', style=discord.ButtonStyle.secondary, row=1)
    async def headquarters(self, interaction, _):
        from snowfall.ui.headquarters import show_headquarters
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Game Menus', emoji='🎮', style=discord.ButtonStyle.secondary, row=1)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Home', emoji='🏠', style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class TitleChooser(MenuView):
    def __init__(self, settings, store, owner_id, cab):
        super().__init__(settings, store, owner_id)
        choices = [discord.SelectOption(label='Snowball Recruit (default)', value='none')]
        choices.extend(discord.SelectOption(label=t.title[:100], value=t.key,
                                            description=t.badge[:100])
                       for t in cab.trophies if t.unlocked)
        select = discord.ui.Select(placeholder='Choose an earned title', options=choices,
                                   min_values=1, max_values=1)

        async def choose(interaction):
            await interaction.response.defer()
            try:
                title = await asyncio.to_thread(AchievementEngine(self.store).equip,
                                        self.settings.season_key, self.owner_id, select.values[0])
                cab_now = await _cabinet(self.settings, self.store, self.owner_id)
                await interaction.edit_original_response(content=(
                    f'✅ Equipped **{discord.utils.escape_markdown(title)}**!\n'
                    'Your selected title is cosmetic and tied to this event season.'),
                    embed=None, attachments=[],
                    view=TitleChooser(self.settings, self.store, self.owner_id, cab_now))
            except TrophyError as exc:
                await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                    attachments=[], view=self)

        select.callback = choose
        self.add_item(select)

    @discord.ui.button(label='Back to Trophies', emoji='🏅', style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction, _):
        await show_cabinet(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Home', emoji='🏠', style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
