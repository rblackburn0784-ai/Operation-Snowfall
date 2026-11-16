"""Private, accessible personal Headquarters, timers and onboarding tour."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.services.experience import headquarters, Headquarters
from snowfall.ui.navigation import MenuView, _edit, show_game, show_home
from snowfall.practice import pin


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _due(value: datetime | None, *, paused=False) -> str:
    if paused:
        return '⏸️ Frozen during event pause'
    if value is None:
        return 'Ready / full'
    return f'<t:{int(value.timestamp())}:R>'


def headquarters_embed(info: Headquarters, settings, title: str = "Snowball Recruit") -> discord.Embed:
    colour = discord.Colour.from_rgb(106, 179, 219)
    embed = discord.Embed(title='❄️ My Snowfall Headquarters', colour=colour)
    embed.set_footer(text='🧪 TEST DAY • No prizes' if getattr(settings, 'mode', 'production') == 'practice'
                     else 'Operation Snowfall • Personal dashboard • Individual prizes only')
    if info.player is None:
        embed.description = ('**Welcome, recruit!**\nDeclare your MafiaReturns username and city '
                             'before you can compete. Use **Guided Start** to learn the game.')
        return embed

    embed.add_field(name='🎩 Equipped Title',
                    value=f'**{discord.utils.escape_markdown(title)}**', inline=False)
    r = info.resources
    embed.description = (f'**{discord.utils.escape_markdown(info.player.mr_username)}**  •  '
                         f'**{info.player.city}**  •  **Day {info.day or "—"}/7**\n'
                         f'Phase: **{info.phase.upper()}**  •  '
                         f'Rank: **#{info.rank}**' if info.rank is not None else
                         f'**{discord.utils.escape_markdown(info.player.mr_username)}**  •  '
                         f'**{info.player.city}**  •  **Day {info.day or "—"}/7**\n'
                         f'Phase: **{info.phase.upper()}**  •  Rank: **outside top 100 / unranked**')
    embed.add_field(name='❄️ Resources', inline=True,
                    value=(f'**Snowballs:** {r.snowballs}/12\n'
                           f'**Warmth:** {r.warmth}/100\n'
                           f'**Snowflakes:** {r.snowflakes}/100\n'
                           f'**Fort:** {r.armour_hp}/25'))
    embed.add_field(name='🏆 Progress', inline=True,
                    value=f'**Season:** {info.season_points} pts\n'
                          f'**Today:** {info.daily_points} pts\n'
                          f'**PvP:** {r.today_pvp}/300 pts')
    paused = info.phase == 'paused'
    embed.add_field(name='⏱️ Regeneration and resets', inline=False,
                    value=(f'Next snowball: **{_due(info.next_snowball, paused=paused)}**\n'
                           f'Next warmth: **{_due(info.next_warmth, paused=paused)}**\n'
                           f'Next throw: **{_due(info.next_throw, paused=paused)}**\n'
                           f'Daily reset: **{_due(info.next_reset, paused=paused)}**'))
    if info.quests:
        rows = []
        for q in info.quests:
            marker = '✅ Claimed' if q.claimed else ('🎁 Claim!' if q.progress >= q.target else '▫️')
            rows.append(f'{marker} **{q.name}:** {q.progress}/{q.target}')
        embed.add_field(name='🎄 Daily quests', value='\n'.join(rows), inline=False)
    if info.world:
        w = info.world
        embed.add_field(name='☃️ Your PvE attempts',
                        value=f'Boss: **{w.boss_attempts}/6** • City siege: **{w.siege_attempts}/4**',
                        inline=False)
        embed.add_field(name='🎁 Mystery gifts', value=(f'Daily: **{info.daily_gift}**'
                        + (f'  •  Day 4 extra: **{info.bonus_gift}**' if info.day == 4 else '')),
                        inline=False)
    embed.add_field(name='👉 What next?', value=info.next_action, inline=False)
    return embed


async def _equipped_title(settings, store, user_id: int) -> str:
    from snowfall.services.achievements import AchievementEngine, TrophyError, DEFAULT_TITLE
    try:
        cab = await asyncio.to_thread(AchievementEngine(store).cabinet,
                                      settings.season_key, user_id)
        return cab.equipped_title
    except TrophyError:
        return DEFAULT_TITLE


async def show_headquarters(interaction, settings, store, owner_id: int) -> None:
    settings, store = pin(settings, store)
    await interaction.response.defer()
    try:
        info = await asyncio.to_thread(headquarters, store, settings.season_key, owner_id, _now())
        equipped = await _equipped_title(settings, store, owner_id) if info.player else "Snowball Recruit"
        await interaction.edit_original_response(content=None, attachments=[],
            embed=headquarters_embed(info, settings, equipped),
            view=HeadquartersView(settings, store, owner_id))
    except (ValueError, RuntimeError) as exc:
        await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None, attachments=[],
            view=HeadquartersView(settings, store, owner_id))


async def send_headquarters(interaction, settings, store) -> None:
    """Slash command: response has already been deferred ephemerally."""
    settings, store = pin(settings, store)
    info = await asyncio.to_thread(headquarters, store, settings.season_key, interaction.user.id, _now())
    equipped = await _equipped_title(settings, store, interaction.user.id) if info.player else "Snowball Recruit"
    await interaction.followup.send(embed=headquarters_embed(info, settings, equipped), ephemeral=True,
        view=HeadquartersView(settings, store, interaction.user.id),
        allowed_mentions=discord.AllowedMentions.none())


class HeadquartersView(MenuView):
    @discord.ui.button(label='Find a Fight', emoji='🎯', style=discord.ButtonStyle.success)
    async def fight(self, interaction, _):
        from snowfall.ui.combat import open_target_menu
        await open_target_menu(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Daily Rewards', emoji='🎁', style=discord.ButtonStyle.primary)
    async def rewards(self, interaction, _):
        from snowfall.ui.economy import QuestsMenu, quests_text
        from snowfall.services.economy import EconomyEngine, EconomyError
        await interaction.response.defer()
        try:
            quests = await asyncio.to_thread(EconomyEngine(self.store).quests,
                                              self.settings.season_key, self.owner_id, _now())
            await interaction.edit_original_response(content=quests_text(quests), embed=None,
                 attachments=[], view=QuestsMenu(self.settings, self.store, self.owner_id))
        except EconomyError as exc:
            await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                 attachments=[], view=HeadquartersView(self.settings, self.store, self.owner_id))

    @discord.ui.button(label='Snow Don / Siege', emoji='☃️', style=discord.ButtonStyle.primary)
    async def boss(self, interaction, _):
        from snowfall.ui.world import WorldView, status_text
        from snowfall.services.world import WorldEngine, WorldError
        await interaction.response.defer()
        try:
            status = await asyncio.to_thread(WorldEngine(self.store).status,
                                              self.settings.season_key, self.owner_id, _now())
            await interaction.edit_original_response(content=status_text(status), embed=None,
                 attachments=[], view=WorldView(self.settings, self.store, self.owner_id))
        except WorldError as exc:
            await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                 attachments=[], view=HeadquartersView(self.settings, self.store, self.owner_id))

    @discord.ui.button(label='Refresh', emoji='🔄', style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, _):
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Game Menus', emoji='🎮', style=discord.ButtonStyle.secondary, row=1)
    async def menus(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Home', emoji='🏠', style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Trophy Cabinet', emoji='🏆', style=discord.ButtonStyle.primary, row=2)
    async def trophies(self, interaction, _):
        from snowfall.ui.trophies import show_cabinet
        await show_cabinet(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Guided Start', emoji='📖', style=discord.ButtonStyle.secondary, row=2)
    async def tutorial(self, interaction, _):
        await show_tour(interaction, self.settings, self.store, self.owner_id, 0)


STEPS = (
    ('Welcome to Snowfall', '1️⃣ **Choose a city and declare your own MR username.**\n'
     'No MafiaReturns password or account link is needed. City choice is locked after your first scored action.'),
    ('Enter the arena', '2️⃣ **Press Enter Arena** to become targetable, then use **Find a Fight**.\n'
     'Only rival cities can be targeted. Protected, knocked-out and unavailable rivals are excluded.\n'
     'Preview your throw and confirm before a snowball is spent.'),
    ('Earn points every day', '3️⃣ **Check Daily Quests, mystery gifts, Snow Don and your city siege.**\n'
     'Snowballs and warmth regenerate every 20 minutes; throws share a 30-second cooldown.\n'
     'City rankings give bragging rights only—real prizes go to individuals.'),
)


async def show_tour(interaction, settings, store, owner_id: int, step: int) -> None:
    settings, store = pin(settings, store)
    title, text = STEPS[step]
    embed = discord.Embed(title=f'📖 Getting Started — {title} ({step+1}/3)',
                          description=text, colour=discord.Colour.from_rgb(106, 179, 219))
    await _edit(interaction, embed=embed, view=WelcomeTour(settings, store, owner_id, step))


class WelcomeTour(MenuView):
    def __init__(self, settings, store, owner_id, step=0):
        super().__init__(settings, store, owner_id)
        self.step = step
        if step == 0:
            self.remove_item(self.previous)
        if step == 2:
            self.remove_item(self.next)

    @discord.ui.button(label='◀ Previous', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, _):
        await show_tour(interaction, self.settings, self.store, self.owner_id, self.step - 1)

    @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.primary)
    async def next(self, interaction, _):
        await show_tour(interaction, self.settings, self.store, self.owner_id, self.step + 1)

    @discord.ui.button(label='Join / Register', emoji='❄️', style=discord.ButtonStyle.success)
    async def join(self, interaction, _):
        from snowfall.ui.dashboard import CityPicker
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        if season.phase(_now()) not in ('registration', 'ready', 'live', 'paused'):
            await interaction.response.send_message('Registration is not open yet.', ephemeral=True)
            return
        await _edit(interaction, content='Choose your city, then declare your MR username:',
            view=CityPicker(self.settings, self.store, self.owner_id))

    @discord.ui.button(label='My Headquarters', emoji='🏠', style=discord.ButtonStyle.secondary, row=1)
    async def hq(self, interaction, _):
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Home', style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
