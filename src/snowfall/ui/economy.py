"""Private, ownership-checked item and quest menus for v0.1.4."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.services.economy import (EconomyEngine, EconomyError, ITEM_COSTS,
                                       ITEM_NAMES)


def now():
    return datetime.now(timezone.utc)


def inventory_text(view) -> str:
    rows = [f"**❄️ Snowfall Inventory — Day {view.day or '—'}**",
            f"✨ **{view.snowflakes}/100 Snowflakes** · 🌡️ {view.warmth}/100 warmth · "
            f"🛡️ {view.armour_hp}/25 fort armour"]
    for key, name in ITEM_NAMES.items():
        special = " (throw from combat menu)" if key == "golden" else ""
        price = f" · Craft {ITEM_COSTS[key]}✨" if key in ITEM_COSTS else " · Gift only"
        rows.append(f"• **{name}:** {view.quantities[key]}{price}{special}")
    rows.append(f"**Buffs:** Mittens {'armed' if view.mittens_armed else 'off'} · "
                f"Bomb {'armed' if view.bomb_armed else 'off'} · "
                f"Guard {'active' if view.guard_active else 'off'}")
    rows.append("Craft items with Snowflakes; daily limits apply to activations.")
    return "\n".join(rows)


def quests_text(quests) -> str:
    lines = ["**🎄 Snowfall Daily Quests**", "Earn **20 points + 2 Snowflakes** per claim."]
    for q in quests:
        state = "✅ Claimed" if q.claimed else ("🟩 Claim ready" if q.progress >= q.target else "⬜ In progress")
        lines.append(f"• **{q.name}:** {q.progress}/{q.target} — {state}")
    lines.append("Community: attempt the Snow Don or city siege. Existing winter preparation also counts.")
    return "\n".join(lines)


from snowfall.practice import pin, practice_expired


class EconomyView(discord.ui.View):
    def __init__(self, settings, store, owner_id):
        super().__init__(timeout=180)
        self.settings, self.store = pin(settings, store)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day has ended.", ephemeral=True)
            return False
        if (interaction.guild_id != self.settings.guild_id or
                interaction.user.id != self.owner_id):
            await interaction.response.send_message("This is another player's private menu.", ephemeral=True)
            return False
        return True

    async def show_inventory(self, interaction):
        await interaction.response.defer()
        try:
            data = await asyncio.to_thread(EconomyEngine(self.store).inventory,
                                           self.settings.season_key, self.owner_id, now())
            await interaction.edit_original_response(
                content=inventory_text(data), view=InventoryMenu(self.settings, self.store, self.owner_id))
        except EconomyError as exc:
            await interaction.edit_original_response(content=f"⚠️ {exc}", view=None)

    async def show_quests(self, interaction):
        await interaction.response.defer()
        try:
            quests = await asyncio.to_thread(EconomyEngine(self.store).quests,
                                              self.settings.season_key, self.owner_id, now())
            await interaction.edit_original_response(
                content=quests_text(quests), view=QuestsMenu(self.settings, self.store, self.owner_id))
        except EconomyError as exc:
            await interaction.edit_original_response(content=f"⚠️ {exc}", view=None)


class InventoryMenu(EconomyView):
    @discord.ui.button(label="Craft", emoji="🔨", style=discord.ButtonStyle.primary)
    async def craft(self, interaction, _):
        await interaction.response.edit_message(
            content="Select an item to craft. Snowflakes are only spent after confirmation.",
            view=ItemPicker(self.settings, self.store, self.owner_id, "craft"))

    @discord.ui.button(label="Use Item", emoji="☕", style=discord.ButtonStyle.success)
    async def use(self, interaction, _):
        await interaction.response.edit_message(
            content="Select an item to activate. Golden Snowballs are thrown through the combat menu.",
            view=ItemPicker(self.settings, self.store, self.owner_id, "use"))

    @discord.ui.button(label="Guard On", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def guard_on(self, interaction, _):
        await self._guard(interaction, "on")

    @discord.ui.button(label="Guard Off", style=discord.ButtonStyle.secondary)
    async def guard_off(self, interaction, _):
        await self._guard(interaction, "off")

    @discord.ui.button(label="Daily Quests", style=discord.ButtonStyle.secondary)
    async def quests(self, interaction, _):
        await self.show_quests(interaction)

    async def _guard(self, interaction, mode):
        await interaction.response.defer()
        try:
            result = await asyncio.to_thread(EconomyEngine(self.store).guard,
                                             self.settings.season_key, self.owner_id,
                                             mode, str(interaction.id), now())
            await interaction.edit_original_response(content=result.text,
                                                     view=InventoryMenu(self.settings, self.store, self.owner_id))
        except EconomyError as exc:
            await interaction.edit_original_response(content=f"⚠️ {exc}",
                                                     view=InventoryMenu(self.settings, self.store, self.owner_id))


class ItemPicker(EconomyView):
    def __init__(self, settings, store, owner_id, operation):
        super().__init__(settings, store, owner_id)
        settings, store = self.settings, self.store
        self.operation = operation
        options = [discord.SelectOption(label=ITEM_NAMES[k], value=k,
                   description=f"{ITEM_COSTS[k]} Snowflakes" if operation == "craft"
                   else "Activate item (daily cap applies)") for k in ITEM_COSTS]
        select = discord.ui.Select(placeholder="Choose a tactical item", options=options)

        async def choose(interaction):
            key = select.values[0]
            await interaction.response.edit_message(
                content=f"Confirm {operation} of **{ITEM_NAMES[key]}**?",
                view=ConfirmItem(settings, store, owner_id, operation, key))

        select.callback = choose
        self.add_item(select)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, _):
        await self.show_inventory(interaction)


class ConfirmItem(EconomyView):
    def __init__(self, settings, store, owner_id, operation, item):
        super().__init__(settings, store, owner_id)
        self.operation, self.item = operation, item

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, _):
        await interaction.response.defer()
        engine = EconomyEngine(self.store)
        try:
            result = await asyncio.to_thread(
                engine.craft if self.operation == "craft" else engine.use,
                self.settings.season_key, self.owner_id, self.item,
                str(interaction.id), now())
            text = "✅ " + result.text
        except EconomyError as exc:
            text = "⚠️ " + str(exc) + " No resources spent."
        await interaction.edit_original_response(content=text,
                                                 view=InventoryMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, _):
        await self.show_inventory(interaction)


class QuestsMenu(EconomyView):
    async def _claim(self, interaction, quest):
        await interaction.response.defer()
        try:
            result = await asyncio.to_thread(EconomyEngine(self.store).claim_quest,
                                             self.settings.season_key, self.owner_id, quest, now())
            message = "✅ " + result.text
        except EconomyError as exc:
            message = "⚠️ " + str(exc)
        data = await asyncio.to_thread(EconomyEngine(self.store).quests,
                                       self.settings.season_key, self.owner_id, now())
        await interaction.edit_original_response(content=message + "\n\n" + quests_text(data),
                                                 view=QuestsMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Claim Gloves", style=discord.ButtonStyle.primary)
    async def gloves(self, interaction, _):
        await self._claim(interaction, "throws")

    @discord.ui.button(label="Claim Rivals", style=discord.ButtonStyle.primary)
    async def rivals(self, interaction, _):
        await self._claim(interaction, "rivals")

    @discord.ui.button(label="Claim Preparation", style=discord.ButtonStyle.primary)
    async def community(self, interaction, _):
        await self._claim(interaction, "community")

    @discord.ui.button(label="Open Present", emoji="🎁", style=discord.ButtonStyle.success)
    async def present(self, interaction, _):
        await interaction.response.defer()
        try:
            result = await asyncio.to_thread(EconomyEngine(self.store).present,
                                             self.settings.season_key, self.owner_id,
                                             str(interaction.id), now())
            pretty = ITEM_NAMES.get(result.actual_reward, result.actual_reward.title())
            message = f"🎁 Your daily present: **+{result.amount} {pretty}**!"
            if result.actual_reward != result.reward:
                message += " (inventory cap or special-rule substitution)"
        except EconomyError as exc:
            message = "⚠️ " + str(exc)
        await interaction.edit_original_response(content=message,
                                                 view=QuestsMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.secondary)
    async def inventory(self, interaction, _):
        await self.show_inventory(interaction)


async def send_inventory(interaction, settings, store):
    try:
        data = await asyncio.to_thread(EconomyEngine(store).inventory,
                                       settings.season_key, interaction.user.id, now())
        await interaction.followup.send(content=inventory_text(data),
                                        view=InventoryMenu(settings, store, interaction.user.id), ephemeral=True)
    except EconomyError as exc:
        await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)


async def send_quests(interaction, settings, store):
    try:
        data = await asyncio.to_thread(EconomyEngine(store).quests,
                                       settings.season_key, interaction.user.id, now())
        await interaction.followup.send(content=quests_text(data),
                                        view=QuestsMenu(settings, store, interaction.user.id), ephemeral=True)
    except EconomyError as exc:
        await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
