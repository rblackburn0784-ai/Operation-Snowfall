"""Optional non-scoring PvP tactics laboratory; only visible in practice days.

Feint and defensive-stance examples are deliberately hypothetical. They do
not invoke combat/guard/economy engines, consume ammunition, or write the DB.
"""
from __future__ import annotations

import secrets

import discord

from snowfall.practice import pin
from snowfall.services.combat import ATTACKS
from snowfall.ui.combat import CombatMenu
from snowfall.ui.dashboard import escape_name


class CombatLab(CombatMenu):
    def __init__(self, settings, store, owner_id: int, target_id: int, name: str):
        settings, store = pin(settings, store)
        if getattr(settings, "mode", "production") != "practice":
            raise ValueError("Tactics Lab only exists in an isolated practice day.")
        super().__init__(settings, store, owner_id)
        self.target_id, self.name = target_id, name

    def _description(self) -> str:
        return (f"🧪 **TACTICS LAB — {escape_name(self.name)}**\n"
                "Choose an optional **hypothetical drill**. The exercise is "
                "completely separate from the event's actual PvP engine.\n"
                "Feint: simulated 10-point accuracy increase on Standard.\n"
                "Defensive Stance: simulated incoming warmth damage reduction of 2.\n"
                "**No snowballs, points, cooldowns, inventory or official stats change.**")

    async def _run(self, interaction, tactic: str):
        if getattr(self.settings, "mode", "production") != "practice":
            await interaction.response.send_message("Practice lab unavailable.", ephemeral=True)
            return
        if tactic == "feint":
            roll = secrets.randbelow(10_000) / 10_000
            chance = min(0.95, ATTACKS["standard"][0] + .10)
            result = (f"🥷 **Feint drill:** virtual hit chance **{chance:.0%}**, "
                      f"roll **{roll:.1%}** → **{'HIT' if roll < chance else 'MISS'}**.")
        else:
            incoming = ATTACKS["standard"][1]
            result = (f"🛡️ **Defensive Stance drill:** virtual incoming damage "
                      f"**{incoming} → {max(1, incoming - 2)}**. No actual guard was applied.")
        await interaction.response.edit_message(
            content=f"{self._description()}\n\n{result}", embed=None,
            attachments=[], view=self)

    @discord.ui.button(label="Feint Drill", emoji="🥷", style=discord.ButtonStyle.primary)
    async def feint(self, interaction, _):
        await self._run(interaction, "feint")

    @discord.ui.button(label="Defensive Stance", emoji="🛡️", style=discord.ButtonStyle.success)
    async def stance(self, interaction, _):
        await self._run(interaction, "stance")

    @discord.ui.button(label="Back to Throws", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction, _):
        from snowfall.ui.combat import ThrowMenu
        await interaction.response.edit_message(
            content=f"🎯 Target: {escape_name(self.name)}. Choose a real practice-day throw:",
            embed=None, attachments=[],
            view=ThrowMenu(self.settings, self.store, self.owner_id, self.target_id, self.name))
