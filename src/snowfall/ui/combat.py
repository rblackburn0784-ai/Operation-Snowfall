"""Private Discord combat menus: choose target -> style -> confirm -> result.

The same CombatEngine powers buttons and slash commands; Discord text is never
trusted for hit calculation or score changes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.services.combat import ATTACKS, CombatEngine, CombatError, CombatResult
from snowfall.ui.dashboard import escape_name


def _now():
    return datetime.now(timezone.utc)


def _result_text(result: CombatResult, target: str) -> str:
    name = escape_name(target)
    if not result.hit:
        return (f"❄️ Your **{result.style.title()}** missed **{name}**! "
                "One snowball used. No points scored. Cooldown: 30s.")
    extra = " 💥 **CRITICAL!**" if result.critical else ""
    ko = " 🥶 **KNOCKOUT!** (30-minute recovery)" if result.knocked_out else ""
    shield = f" • {result.armour_damage} absorbed by fort" if result.armour_damage else ""
    bonus = f" • City +{result.bonus_city}" if result.bonus_city else ""
    bonus += f" • KO +{result.bonus_ko}" if result.bonus_ko else ""
    return (f"🎯 **{name}** hit with a **{result.style.title()}**!{extra}{ko}\n"
            f"**Warmth damage:** {result.warmth_damage}{shield}\n"
            f"**Your points:** +{result.points_awarded}{bonus}"
            + (f" • Defender +{result.defense_points} defence" if result.defense_points else "")
            + "\nCooldown: 30s. Your attack was saved safely.")


class CombatMenu(discord.ui.View):
    """Selection, confirmation and result are edited in the same private message."""
    def __init__(self, settings, store, owner_id: int, timeout=180):
        super().__init__(timeout=timeout)
        self.settings = settings
        self.store = store
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.settings.guild_id or interaction.user.id != self.owner_id:
            await interaction.response.send_message("This is someone else's private snowball menu.", ephemeral=True)
            return False
        return True

    async def _targets(self, interaction: discord.Interaction):
        engine = CombatEngine(self.store)
        try:
            targets = await asyncio.to_thread(engine.targets, self.settings.season_key,
                                              interaction.user.id, _now())
        except CombatError as exc:
            await interaction.response.edit_message(content=str(exc), view=None)
            return
        if not targets:
            await interaction.response.edit_message(
                content="No eligible rivals right now. Ask people to `/snow ready`, or return later.",
                view=None,
            )
            return
        await interaction.response.edit_message(
            content="🎯 **Choose a rival from another city:**",
            view=TargetPicker(self.settings, self.store, interaction.user.id, targets),
        )


class TargetPicker(CombatMenu):
    def __init__(self, settings, store, owner_id: int, targets):
        super().__init__(settings, store, owner_id)
        self.names = {str(t.discord_user_id): t.mr_username for t in targets}
        options = [discord.SelectOption(
            label=f"{t.mr_username} — {t.city}"[:100],
            description=f"Warmth {t.warmth}/100 · {t.hits_remaining} scored hits left"[:100],
            value=str(t.discord_user_id),
        ) for t in targets]
        selector = discord.ui.Select(placeholder="Select a rival player", options=options)

        async def chosen(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=f"🎯 **Target:** {escape_name(self.names[selector.values[0]])}\n"
                        "Select the throw to preview its accuracy and damage:",
                view=ThrowMenu(settings, store, owner_id, int(selector.values[0]),
                               self.names[selector.values[0]]),
            )

        selector.callback = chosen
        self.add_item(selector)


class ThrowMenu(CombatMenu):
    def __init__(self, settings, store, owner_id: int, target_id: int, name: str):
        super().__init__(settings, store, owner_id)
        self.target_id, self.name = target_id, name

    async def _choose(self, interaction: discord.Interaction, style: str):
        chance, damage, score = ATTACKS[style]
        await interaction.response.edit_message(
            content=(f"❄️ **Confirm {style.title()}** against **{escape_name(self.name)}**?\n"
                     f"Hit chance: **{int(chance*100)}%** | Warmth damage: **{damage}** | "
                     f"Points on hit: **{score}** before bonuses.\n"
                     "Cost: **1 snowball**. Cooldown: **30 seconds**.\n"
                     "Target eligibility and protection are checked again when you confirm."),
            view=ConfirmThrow(self.settings, self.store, self.owner_id,
                              self.target_id, self.name, style),
        )

    @discord.ui.button(label="Quick Lob · 75%", style=discord.ButtonStyle.success)
    async def quick(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._choose(interaction, "quick")

    @discord.ui.button(label="Standard · 60%", style=discord.ButtonStyle.primary)
    async def standard(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._choose(interaction, "standard")

    @discord.ui.button(label="Power · 40%", style=discord.ButtonStyle.danger)
    async def power(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._choose(interaction, "power")

    @discord.ui.button(label="Back to Targets", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._targets(interaction)


class ConfirmThrow(CombatMenu):
    def __init__(self, settings, store, owner_id: int, target_id: int,
                 name: str, style: str):
        super().__init__(settings, store, owner_id)
        self.target_id, self.name, self.style = target_id, name, style

    @discord.ui.button(label="❄️ THROW!", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()  # component update, under Discord's 3s limit
        try:
            result = await asyncio.to_thread(
                CombatEngine(self.store).throw, self.settings.season_key,
                interaction.user.id, self.target_id, self.style,
                str(interaction.id), _now(),
            )
        except CombatError as exc:
            await interaction.edit_original_response(
                content=f"⚠️ {exc}\nNo snowball was spent.", view=RetryView(
                    self.settings, self.store, self.owner_id,
                ),
            )
            return
        await interaction.edit_original_response(
            content=_result_text(result, self.name),
            view=RetryView(self.settings, self.store, self.owner_id),
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._targets(interaction)


class RetryView(CombatMenu):
    @discord.ui.button(label="Choose Another Target", style=discord.ButtonStyle.primary)
    async def another(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._targets(interaction)


async def send_target_menu(interaction: discord.Interaction, settings, store):
    """For slash commands or dashboard; caller must defer response ephemerally."""
    try:
        targets = await asyncio.to_thread(CombatEngine(store).targets,
                                          settings.season_key, interaction.user.id, _now())
    except CombatError as exc:
        await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
        return
    if not targets:
        await interaction.followup.send(
            "No eligible rivals yet. Players can use `/snow ready` to enter the arena. "
            "Rivals also need to be from a different city, and not protected or knocked out.",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "🎯 **Pick a rival:**", view=TargetPicker(settings, store, interaction.user.id, targets),
        ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
    )
