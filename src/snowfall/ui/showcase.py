"""v0.2.2 owned, seasonal, and shareable illustrated player showcase.

Private navigation is an owner-checked ephemeral message; the separate public
slash command is an explicit opt-in and rate limited by discord.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO

import discord

from snowfall.graphics import cards, delivery
from snowfall.practice import pin
from snowfall.services.showcase import Showcase, ShowcaseError, showcase as load_showcase
from snowfall.services.winter_fun import COSMETICS, SLOTS
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe(value: object) -> str:
    return discord.utils.escape_markdown(cards.clean(value, 65)).replace("@", "＠")


def card_text(info: Showcase, *, public: bool = False) -> str:
    lines = [
        f"🎩 **{_safe(info.player.mr_username)}** · {_safe(info.player.city)}",
        f"**{_safe(info.title)}** · **{info.best_rarity}** equipped style",
        f"🏆 **{info.points}** season pts · ✨ **{info.resources.snowflakes}** Snowflakes",
        f"🎖️ **{info.badge_count}/{info.badge_total}** earned badges · "
        f"🎨 **{info.owned_count}/{info.cosmetic_total}** owned cosmetics",
    ]
    if info.arcade_stamps:
        lines.append(f"🎟️ **Winter Arcade:** {len(info.arcade_stamps)}/11 "
                     "decorative passport stamps")
    for slot in SLOTS:
        key = info.equipped.get(slot)
        item = COSMETICS.get(key) if key else None
        lines.append(f"**{slot.title()}:** "
                     + (f"{_safe(item.name)} · {item.rarity}" if item else "Default"))
    if info.featured_badges:
        lines.append("**Featured badges:** " + " · ".join(
            f"{_safe(t.badge)} ({t.rarity})" for t in info.featured_badges))
    lines.append("*Collectible display only. No extra scoring, PvP bonuses or prizes.*")
    if not public:
        lines.append("Use **/snowfun showcase** to publish your card in the current channel "
                     "(once every 10 minutes).")
    return "\n".join(lines)


async def _load(settings, store, user: int, *, public=False) -> Showcase:
    return await asyncio.to_thread(load_showcase, store, settings.season_key,
                                   user, _now(), public=public)


async def show_profile(interaction, settings, store, owner_id: int) -> None:
    """Replace the current private menu, removing prior illustrations."""
    settings, store = pin(settings, store)
    await interaction.response.defer()
    view = ShowcaseView(settings, store, owner_id)
    try:
        info = await _load(settings, store, owner_id)
        await delivery.edit_result(
            interaction, card_text(info), view,
            lambda: cards.profile_card(info.player.mr_username, info.player.city,
                info.resources, info.points, review=info.player.review_state, showcase=info),
            alt=f"Illustrated Snowfall collector card for {cards.clean(info.player.mr_username)}")
    except ShowcaseError as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {exc}", embed=None, attachments=[], view=view,
            allowed_mentions=discord.AllowedMentions.none())


async def send_profile(interaction, settings, store) -> None:
    """Initial, already deferred ephemeral slash or public-dashboard response."""
    settings, store = pin(settings, store)
    try:
        info = await _load(settings, store, interaction.user.id)
        await delivery.send_profile(
            interaction, card_text(info), info.player.mr_username, info.player.city,
            info.resources, info.points, review=info.player.review_state,
            showcase=info, view=ShowcaseView(settings, store, interaction.user.id))
    except ShowcaseError as exc:
        await interaction.followup.send(f"⚠️ {exc}", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())


async def publish_card(interaction, settings, store) -> None:
    """An explicitly invoked *public* slash action, not a hidden menu side effect."""
    settings, store = pin(settings, store)
    if getattr(settings, "mode", "production") == "practice":
        await interaction.response.send_message(
            "🧪 Public cards are disabled in test-day channels. Your practice data stays private.",
            ephemeral=True)
        return
    # Validate before a public defer so rejected identities aren't announced.
    try:
        info = await _load(settings, store, interaction.user.id, public=True)
    except ShowcaseError as exc:
        await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    caption = card_text(info, public=True)
    try:
        image = await asyncio.to_thread(
            cards.profile_card, info.player.mr_username, info.player.city, info.resources,
            info.points, review=info.player.review_state, showcase=info)
        await interaction.followup.send(
            content=caption, file=discord.File(BytesIO(image), filename="snowfall-showcase.png",
                description=f"Snowfall collector card for {cards.clean(info.player.mr_username)}"),
            allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, OSError, ValueError, MemoryError):
        # Public user already chose to share; text remains a useful fallback.
        await interaction.followup.send(content=caption,
            allowed_mentions=discord.AllowedMentions.none())


class ShowcaseView(MenuView):
    @discord.ui.button(label="Refresh Card", emoji="🔄", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction, _):
        await show_profile(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="My Wardrobe", emoji="🎩", style=discord.ButtonStyle.success)
    async def wardrobe(self, interaction, _):
        from snowfall.ui.winter_fun import _display
        await _display(interaction, self.settings, self.store, self.owner_id, "Wardrobe")

    @discord.ui.button(label="My Badges", emoji="🎖️", style=discord.ButtonStyle.secondary)
    async def badges(self, interaction, _):
        from snowfall.ui.trophies import show_cabinet
        await show_cabinet(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary, row=1)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
