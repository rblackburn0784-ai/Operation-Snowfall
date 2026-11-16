"""Private, ownership-checked boss and siege buttons, and readable rankings."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.practice import pin, practice_expired

from snowfall.services.world import WorldEngine, WorldError, BOSS_LIMIT, SIEGE_LIMIT
from snowfall.ui.dashboard import escape_name
from snowfall.graphics import cards, delivery
from snowfall.services.boss_personality import reaction_for_result


def now():
    return datetime.now(timezone.utc)


def status_text(state):
    if state.day is None:
        return f"❄️ World events are not open (phase: **{state.phase}**)."
    return (f"**❄️ Snowfall — Day {state.day}/7: {state.theme}**\n"
            f"Phase: **{state.phase.upper()}**\n"
            f"☃️ **Abominable Snow Don:** "
            f"{'Disabled by host' if not state.boss_enabled else f'{state.boss_hp}/{state.boss_max_hp} HP'} "
            f"| Attempts {state.boss_attempts}/{BOSS_LIMIT} "
            f"| Points {state.boss_points}/50\n"
            f"🏰 **{state.city} fortress:** {state.siege_hp}/{state.siege_max_hp} HP "
            f"| Attempts {state.siege_attempts}/{SIEGE_LIMIT} "
            f"| Points {state.siege_points}/50\n"
            "Each NPC attempt costs one ordinary snowball and obeys the shared 30s cooldown. "
            "After a boss/fort defeat, late players can still score normal hit points "
            "against a personal training echo/rubble pile. No extra clear bonuses.")


def result_text(r):
    target = 'Snow Don' if r.kind == 'boss' else f'{r.city} fortress'
    action = '💥 Hit!' if r.hit else '💨 Missed!'
    detail = 'Personal training echo' if r.kind == 'boss' and r.echo else (
        'Practice rubble pile' if r.echo else 'Shared battlefield')
    return (f"**{action} {target} — Day {r.day}**\n"
            f"Damage: **{r.damage}** | Points: **+{r.points}**"
            f"{' | Theme bonus: +' + str(r.theme_points) if r.theme_points else ''}\n"
            f"{detail} | Remaining shared HP: **{r.hp_after}/{r.max_hp}**\n"
            + ('\n' + reaction_for_result(r) if reaction_for_result(r) else '')
            + ('🎉 **FINAL BLOW!**' if r.final_blow else '')
            + ('\n*Repeated Discord interaction; no resources spent again.*' if r.repeated else ''))


def city_board_text(rows):
    text = ['🏙️ **City Championship — honorary standings only**',
            '*No city prizes. Daily totals are provisional until rollover.*']
    for i, r in enumerate(rows, 1):
        status = 'provisional' if r.provisional else 'locked'
        qualifier = '' if r.qualifying_today else ' (today: fewer than 3 scorers)'
        text.append(f"**{i}. {r.city}** — {r.score_x100/100:.2f} pts "
                    f"| Today {r.todays_score_x100/100:.2f} ({status}) "
                    f"| Siege clears {r.siege_clears}{qualifier}")
    return '\n'.join(text)


def individual_board_text(rows):
    text = ['🏆 **Individual Championship — only individuals receive prizes**']
    text.extend(f"**{i}.** {escape_name(name)} ({city}): **{points}** points"
                for i, (name, city, _user, points) in enumerate(rows, 1))
    return '\n'.join(text) if rows else text[0] + '\nNo registered competitors yet.'


class WorldView(discord.ui.View):
    def __init__(self, settings, store, owner_id):
        super().__init__(timeout=180)
        self.settings, self.store = pin(settings, store)
        self.owner_id = owner_id
        from snowfall.ui.navigation import attach_game_navigation
        attach_game_navigation(self, self.settings, self.store, self.owner_id)

    async def interaction_check(self, interaction):
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day has ended.", ephemeral=True)
            return False
        if interaction.guild_id != self.settings.guild_id or interaction.user.id != self.owner_id:
            await interaction.response.send_message('This is another player’s private menu.', ephemeral=True)
            return False
        return True

    async def _attack(self, interaction, kind):
        await interaction.response.edit_message(
            content=f'Confirm one **{kind.title()}** attack? Costs 1 snowball, '
                    'uses the shared 30-second cooldown and counts as a legal NPC attempt.',
            view=WorldConfirm(self.settings, self.store, self.owner_id, kind),
            embed=None, attachments=[])

    @discord.ui.button(label='Attack Snow Don', emoji='☃️', style=discord.ButtonStyle.primary)
    async def boss(self, interaction, _):
        await self._attack(interaction, 'boss')

    @discord.ui.button(label='Attack City Fortress', emoji='🏰', style=discord.ButtonStyle.success)
    async def siege(self, interaction, _):
        await self._attack(interaction, 'siege')

    @discord.ui.button(label='Refresh', style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction, _):
        await interaction.response.defer()
        try:
            state = await asyncio.to_thread(WorldEngine(self.store).status,
                                            self.settings.season_key, self.owner_id, now())
            await delivery.edit_result(
                interaction, status_text(state), WorldView(self.settings, self.store, self.owner_id),
                lambda: cards.world_status_card(state),
                alt=f"Day {state.day}: Snow Don and {state.city} fortress health",
            )
        except WorldError as exc:
            await interaction.edit_original_response(content=f'⚠️ {exc}', embed=None,
                                                     attachments=[], view=WorldView(
                                                         self.settings, self.store, self.owner_id))


class WorldConfirm(discord.ui.View):
    def __init__(self, settings, store, owner_id, kind):
        super().__init__(timeout=120)
        self.settings, self.store = pin(settings, store)
        self.owner_id, self.kind = owner_id, kind
        from snowfall.ui.navigation import attach_game_navigation
        attach_game_navigation(self, self.settings, self.store, self.owner_id)

    async def interaction_check(self, interaction):
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day has ended.", ephemeral=True)
            return False
        if interaction.guild_id != self.settings.guild_id or interaction.user.id != self.owner_id:
            await interaction.response.send_message('Not your attack confirmation.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Confirm Attack', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, _):
        await interaction.response.defer()
        try:
            result = await asyncio.to_thread(WorldEngine(self.store).attack,
                                             self.settings.season_key, self.owner_id,
                                             self.kind, str(interaction.id), now())
        except WorldError as exc:
            await interaction.edit_original_response(
                content=f'⚠️ {exc} No snowballs were spent.',
                view=WorldView(self.settings, self.store, self.owner_id))
            return
        await delivery.edit_result(
            interaction, result_text(result), WorldView(self.settings, self.store, self.owner_id),
            lambda: cards.world_result_card(result),
            alt=(f"{self.kind} attempt: {'hit' if result.hit else 'miss'}, "
                 f"{result.damage} damage, {result.points} points"),
            animate=lambda: cards.world_animation(result),
        )

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, _):
        await interaction.response.defer()
        state = await asyncio.to_thread(WorldEngine(self.store).status,
                                        self.settings.season_key, self.owner_id, now())
        await delivery.edit_result(interaction, status_text(state),
            WorldView(self.settings, self.store, self.owner_id),
            lambda: cards.world_status_card(state),
            alt=f"Day {state.day}: Snow Don and {state.city} fortress health")


async def send_world(interaction, settings, store):
    try:
        state = await asyncio.to_thread(WorldEngine(store).status,settings.season_key,
                                        interaction.user.id,now())
        await delivery.send_world_status(
            interaction, status_text(state), state,
            WorldView(settings, store, interaction.user.id),
        )
    except WorldError as exc:
        await interaction.followup.send(f'⚠️ {exc}',ephemeral=True)
