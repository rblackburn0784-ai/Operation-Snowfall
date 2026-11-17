"""Private rivalry dossier, revenge alerts and non-scoring combat intelligence."""
from __future__ import annotations

import asyncio
from io import BytesIO
import sqlite3

import discord

from snowfall.graphics import delivery
from snowfall.graphics.combat_cards import rivalry_card
from snowfall.practice import pin
from snowfall.services.combat_intel import CombatIntel, CombatIntelEngine
from snowfall.ui.navigation import MenuView, show_game, show_home


def _safe(value) -> str:
    return discord.utils.escape_markdown(str(value or "—")).replace("@", "＠")


def rivalry_text(info: CombatIntel) -> str:
    result = [
        "📜 **Snowfall Rivalry Dossier — Your private combat record**",
        f"🎯 Scored PvP hits: **{info.total_hits}/{info.total_attacks}** "
        f"· Current streak: **{info.current_streak}** · Best: **{info.best_streak}**",
        f"🥶 Successful retaliations: **{info.revenge_count}**",
    ]
    if info.revenge_alerts:
        result.append(f"🔔 **{len(info.revenge_alerts)} revenge opportunity/opportunities** "
                      "(only those currently eligible can be challenged)")
    else:
        result.append("🔕 No outstanding scored-hit revenge alerts.")
    for r in info.rivalries[:8]:
        alert = " 🔔 **REVENGE**" if r.pending_revenge else ""
        when = f" · Last hit <t:{int(r.last_incoming_hit.timestamp())}:R>" if (
            r.pending_revenge and r.last_incoming_hit is not None) else ""
        result.append(
            f"**{_safe(r.name)}** · {_safe(r.city)}{alert}\n"
            f"Hits **{r.hits}–{r.received_hits}** · "
            f"Throws **{r.attacks}** · Accuracy **{r.accuracy}%** "
            f"· KOs **{r.knockouts}** · Retaliations **{r.revenges}**{when}"
        )
    if not info.rivalries:
        result.append("No PvP encounters yet. Find a rival to begin a feud.")
    if len(info.rivalries) > 8:
        result.append(f"+ {len(info.rivalries)-8} more rivalries on record.")
    result.append("*Alerts are private in-game reminders, not unsolicited DMs. "
                  "No additional points, prizes, or attack permissions.*")
    return "\n".join(result)[:1950]


async def _state(settings, store, owner):
    info = await asyncio.to_thread(CombatIntelEngine(store).snapshot, settings.season_key, owner)
    player = await asyncio.to_thread(store.get_player, settings.season_key, owner)
    return info, player.city if player else "Chicago"


async def show_rivalries(interaction, settings, store, owner_id: int):
    settings, store = pin(settings, store)
    await interaction.response.defer()
    view = RivalryView(settings, store, owner_id)
    try:
        intel, city = await _state(settings, store, owner_id)
        await delivery.edit_result(interaction, rivalry_text(intel), view,
                                   lambda: rivalry_card(intel, city),
                                   alt="Personal battle streak, rival statistics and pending revenge alerts")
    except (ValueError, sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}", view=view, attachments=[], embed=None,
            allowed_mentions=discord.AllowedMentions.none())


async def send_rivalries(interaction, settings, store):
    """Only for a slash command already deferred ephemeral."""
    settings, store = pin(settings, store)
    view = RivalryView(settings, store, interaction.user.id)
    try:
        intel, city = await _state(settings, store, interaction.user.id)
        caption = rivalry_text(intel)
    except (ValueError, sqlite3.Error) as exc:
        await interaction.followup.send(f"⚠️ {_safe(exc)}", view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())
        return
    try:
        picture = await asyncio.to_thread(rivalry_card, intel, city)
        embed = discord.Embed(colour=discord.Colour.from_rgb(111, 188, 228))
        embed.set_image(url="attachment://rivalries.png")
        await interaction.followup.send(
            content=caption, embed=embed,
            file=discord.File(BytesIO(picture), filename="rivalries.png",
                description="Personal combat rivalry dossier"),
            view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, OSError, ValueError, MemoryError):
        await interaction.followup.send(caption, view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())


class RivalryView(MenuView):
    @discord.ui.button(label="Revenge Finder", emoji="🔔", style=discord.ButtonStyle.primary)
    async def revenge(self, interaction, _):
        from snowfall.ui.combat import open_target_menu
        await open_target_menu(interaction, self.settings, self.store, self.owner_id, mode="revenge")

    @discord.ui.button(label="Find a Rival", emoji="🎯", style=discord.ButtonStyle.success)
    async def targets(self, interaction, _):
        from snowfall.ui.combat import open_target_menu
        await open_target_menu(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Refresh Dossier", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction, _):
        await show_rivalries(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary, row=1)
    async def games(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
