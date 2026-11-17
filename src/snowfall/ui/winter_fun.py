"""Private v0.2.2 activity centre, wardrobe, encounters and no-prize arcade modes."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.practice import pin
from snowfall.services.winter_fun import (
    COSMETICS, ENCOUNTERS, ENCOUNTER_CHOICES, MODES, SLOTS, WinterFunEngine, WinterFunError,
)
from snowfall.services.daily_missions import missions_for_day
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _title(settings) -> str:
    mode = "🧪 PRACTICE" if getattr(settings, "is_test", False) else "❄️ OPERATION SNOWFALL"
    return f"{mode} — Winter Activities"


def _escape(value: str) -> str:
    return discord.utils.escape_markdown(value).replace("@", "＠")


def _text(page: str, snapshot, *, alert: str = "") -> str:
    lead = f"**🎄 {_escape(page)}** · Day {snapshot.day or '—'}/7 · ✨ {snapshot.balance} Snowflakes"
    sections = [lead, "*All new activities are outside official rankings and prizes.*"]
    if page == "Shop":
        for key, item in COSMETICS.items():
            icon = "✅" if key in snapshot.unlocked else "🛍️"
            sections.append(f"{icon} **{_escape(item.name)}** [{item.rarity}] — "
                            f"{item.cost}✨ · {_escape(item.detail)}")
        sections.append("Choose Buy Cosmetic below. Equipment bonuses work only in arcade modes.")
    elif page == "Wardrobe":
        for slot in SLOTS:
            key = snapshot.equipped.get(slot)
            item = COSMETICS.get(key) if key else None
            name = f"{item.name} [{item.rarity}]" if item else "Default / not equipped"
            sections.append(f"**{slot.title()}:** {_escape(name)}")
        sections.append(f"**Unlocked:** {len(snapshot.unlocked)}/{len(COSMETICS)} cosmetics and equipment")
        sections.append("Use **My Card** to see your selected style and earned badges illustrated.")
    elif page == "Encounter":
        if snapshot.day:
            title, story, souvenir = ENCOUNTERS[snapshot.day - 1]
            sections.extend((f"**{title}**", _escape(story),
                             f"**Souvenir:** {_escape(snapshot.encounter.souvenir)}" if snapshot.encounter
                             else "Discover the encounter to collect today's souvenir."))
        else:
            sections.append("A new surprise encounter becomes available each live event day.")
        sections.append("One souvenir per player per day. No Snowflakes or combat points awarded.")
    elif page == "Arcade":
        for key, (name, detail) in MODES.items():
            sections.append(f"**{_escape(name)}** — {_escape(detail)}\n"
                            f"Attempts: {snapshot.arcade_used[key]}/3 today · "
                            f"Best: {snapshot.arcade_best[key]} arcade score")
        sections.append("Your specialist gear helps only in these three training modes.")
    elif page == "Missions":
        for mission in missions_for_day(snapshot.day):
            sections.append(f"**{mission.title}:** {mission.detail}")
        sections.append("Claim each mission through Daily Quests; normal rewards still apply.")
    else:
        sections.extend(("🛍️ Rarity-labelled cosmetic shop & specialist equipment",
                         "🎩 Illustrated portraits, custom frames, banners, trails & wardrobe",
                         "🎲 Daily encounters",
                         "🎯 Target Practice · 🛡️ Blizzard Dodge · ☃️ Boss Drill",
                         "🎄 Rotating daily missions"))
    if alert:
        sections.append(f"\n**{_escape(alert)}**")
    return "\n".join(sections)[:3900]


async def _display(interaction, settings, store, owner: int, page: str, *, alert="") -> None:
    settings, store = pin(settings, store)
    await interaction.response.defer()
    view = WinterActivitiesView(settings, store, owner)
    try:
        snapshot = await asyncio.to_thread(WinterFunEngine(store).shop, settings.season_key,
                                           owner, _now())
        description = _text(page, snapshot, alert=alert)
        view.page = page
    except WinterFunError as exc:
        description = f"⚠️ {_escape(str(exc))}\nRegister first to access your winter activities."
    await interaction.edit_original_response(content=description, embed=None, attachments=[],
                                             view=view, allowed_mentions=discord.AllowedMentions.none())


async def send_activities(interaction, settings, store, *, page: str = "Activities") -> None:
    """Called by a slash command after defer(ephemeral=True)."""
    settings, store = pin(settings, store)
    try:
        snapshot = await asyncio.to_thread(WinterFunEngine(store).shop, settings.season_key,
                                           interaction.user.id, _now())
        text = _text(page, snapshot)
    except WinterFunError as exc:
        text = f"⚠️ {_escape(str(exc))}. Register first with /snow join."
    await interaction.followup.send(content=f"{_title(settings)}\n{text}",
                                    view=WinterActivitiesView(settings, store, interaction.user.id),
                                    ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


class WinterActivitiesView(MenuView):
    @discord.ui.button(label="Shop", emoji="🛍️", style=discord.ButtonStyle.primary)
    async def shop(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Shop")

    @discord.ui.button(label="Wardrobe", emoji="🎩", style=discord.ButtonStyle.secondary)
    async def wardrobe(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Wardrobe")

    @discord.ui.button(label="Surprise Encounter", emoji="🎲", style=discord.ButtonStyle.success)
    async def encounter(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Encounter")

    @discord.ui.button(label="Arcade Modes", emoji="🎯", style=discord.ButtonStyle.primary)
    async def arcade(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Arcade")

    @discord.ui.button(label="Daily Missions", emoji="🎄", style=discord.ButtonStyle.secondary)
    async def missions(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Missions")

    @discord.ui.button(label="Buy Cosmetic", emoji="✨", style=discord.ButtonStyle.success, row=1)
    async def buy(self, interaction, _):
        await interaction.response.edit_message(content="Choose a cosmetic or specialist gear to unlock.",
                                                embed=None, attachments=[],
                                                view=WinterPicker(self.settings, self.store,
                                                                  self.owner_id, "buy"))

    @discord.ui.button(label="Equip Item", style=discord.ButtonStyle.secondary, row=1)
    async def equip(self, interaction, _):
        await interaction.response.edit_message(content="Choose unlocked winter gear or cosmetic to equip.",
                                                embed=None, attachments=[],
                                                view=WinterPicker(self.settings, self.store,
                                                                  self.owner_id, "equip"))

    @discord.ui.button(label="Find Encounter", style=discord.ButtonStyle.success, row=1)
    async def discover(self, interaction, _):
        await interaction.response.edit_message(content="How will you handle today's encounter?",
            attachments=[], embed=None,
            view=EncounterPicker(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Play Mini-Game", style=discord.ButtonStyle.primary, row=1)
    async def play(self, interaction, _):
        await interaction.response.edit_message(content="Choose a no-prize mini-game. Three tries per mode per day.",
                                                embed=None, attachments=[],
                                                view=WinterPicker(self.settings, self.store,
                                                                  self.owner_id, "play"))

    @discord.ui.button(label="My Card", emoji="🃏", style=discord.ButtonStyle.success, row=2)
    async def card(self, interaction, _):
        from snowfall.ui.showcase import show_profile
        await show_profile(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=2)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class WinterPicker(MenuView):
    def __init__(self, settings, store, owner: int, action: str):
        super().__init__(settings, store, owner)
        self.action = action
        if action == "play":
            options = [discord.SelectOption(label=name, value=k, description=description[:100])
                       for k, (name, description) in MODES.items()]
        else:
            options = [discord.SelectOption(label=x.name, value=k,
                       description=f"{x.rarity} · {x.cost} Snowflakes · {x.category}"[:100])
                       for k, x in COSMETICS.items()]
        chooser = discord.ui.Select(placeholder=f"Choose an item to {action}", options=options)

        async def selected(interaction):
            key = chooser.values[0]
            if action == "equip":
                await interaction.response.defer()
                try:
                    text = await asyncio.to_thread(WinterFunEngine(self.store).equip,
                        self.settings.season_key, self.owner_id, key, _now())
                except WinterFunError as exc:
                    text = f"⚠️ {exc}"
                await interaction.edit_original_response(content=text, view=WinterActivitiesView(
                    self.settings, self.store, self.owner_id), attachments=[])
            else:
                display = COSMETICS[key].name if action == "buy" else MODES[key][0]
                await interaction.response.edit_message(
                    content=f"Confirm {action} of **{_escape(display)}**? "
                            "Cosmetics do not change official scores, combat or prizes.",
                    embed=None, attachments=[],
                    view=WinterConfirm(self.settings, self.store, self.owner_id, action, key))
        chooser.callback = selected
        self.add_item(chooser)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Activities")


class WinterConfirm(MenuView):
    def __init__(self, settings, store, owner: int, action: str, key: str):
        super().__init__(settings, store, owner)
        self.action, self.key = action, key
        if action != "play":
            for child in list(self.children):
                if getattr(child, "label", None) == "Risky Play":
                    self.remove_item(child)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, _):
        await interaction.response.defer()
        engine = WinterFunEngine(self.store)
        try:
            if self.action == "buy":
                message = await asyncio.to_thread(engine.buy, self.settings.season_key,
                    self.owner_id, self.key, str(interaction.id), _now())
            else:
                result = await asyncio.to_thread(engine.play, self.settings.season_key,
                    self.owner_id, self.key, str(interaction.id), _now(), "steady")
                message = (f"🎮 {MODES[self.key][0]}: **{result.points} arcade score** · "
                           f"Personal best: {result.personal_best} · "
                           f"Attempt {result.attempts_used}/3 today" +
                           (" (Already recorded.)" if result.repeated else ""))
        except WinterFunError as exc:
            message = f"⚠️ {exc}"
        await interaction.edit_original_response(content=message, attachments=[], embed=None,
            view=WinterActivitiesView(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Risky Play", style=discord.ButtonStyle.danger)
    async def risky(self, interaction, _):
        if self.action != "play":
            await interaction.response.send_message("Risky strategy is for arcade modes only.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            result = await asyncio.to_thread(WinterFunEngine(self.store).play,
                self.settings.season_key, self.owner_id, self.key, str(interaction.id), _now(), "risky")
            message = (f"🎲 Risky {MODES[self.key][0]}: {result.points} arcade score · "
                       f"Best {result.personal_best} · Attempt {result.attempts_used}/3")
        except WinterFunError as exc:
            message = f"⚠️ {exc}"
        await interaction.edit_original_response(content=message, embed=None, attachments=[],
            view=WinterActivitiesView(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Activities")


class EncounterPicker(MenuView):
    def __init__(self, settings, store, owner):
        super().__init__(settings, store, owner)
        chooser = discord.ui.Select(placeholder="How do you respond?", options=[
            discord.SelectOption(label=label, value=key)
            for key, (label, _) in ENCOUNTER_CHOICES.items()])

        async def respond(interaction):
            choice = chooser.values[0]
            await interaction.response.defer()
            try:
                result = await asyncio.to_thread(WinterFunEngine(self.store).encounter,
                    self.settings.season_key, self.owner_id, str(interaction.id), _now(), choice)
                message = f"{result.title}: {result.story} · Souvenir: {result.souvenir}"
                if result.repeated:
                    message += " (Already encountered today.)"
            except WinterFunError as exc:
                message = f"⚠️ {exc}"
            await interaction.edit_original_response(content=message, embed=None, attachments=[],
                view=WinterActivitiesView(self.settings, self.store, self.owner_id))
        chooser.callback = respond
        self.add_item(chooser)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction, _):
        await _display(interaction, self.settings, self.store, self.owner_id, "Encounter")
