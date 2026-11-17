"""Private Discord combat menus: choose target -> style -> confirm -> result.

The same CombatEngine powers buttons and slash commands; Discord text is never
trusted for hit calculation or score changes.
"""
from __future__ import annotations

import asyncio
import secrets
import sqlite3
from datetime import datetime, timezone

import discord

from snowfall.practice import pin, practice_expired

from snowfall.services.combat import ATTACKS, CombatEngine, CombatError, CombatResult
from snowfall.services.combat_intel import CombatIntelEngine, target_order
from snowfall.services.combat_flair import fight_beat
from snowfall.ui.dashboard import escape_name
from snowfall.graphics import cards, delivery


def _now():
    return datetime.now(timezone.utc)


def _result_text(result: CombatResult, target: str) -> str:
    name = escape_name(target)
    if result.repeated:
        return (f"🔁 This **{result.style.title()}** against **{name}** was already recorded. "
                f"Original result: **{'hit' if result.hit else 'miss'}**; "
                "no second snowball or score was consumed.")
    if not result.hit:
        spent = "Golden Snowball" if result.style == "golden" else "snowball"
        return (f"❄️ Your **{result.style.title()}** missed **{name}**! "
                f"One {spent} used. No points scored. Cooldown: 30s.")
    extra = " 💥 **CRITICAL!**" if result.critical else ""
    ko = " 🥶 **KNOCKOUT!** (30-minute recovery)" if result.knocked_out else ""
    shield = f" • {result.armour_damage} absorbed by fort" if result.armour_damage else ""
    bonus = f" • City +{result.bonus_city}" if result.bonus_city else ""
    bonus += f" • KO +{result.bonus_ko}" if result.bonus_ko else ""
    bonus += f" • Gear +{result.item_bonus_points}" if result.item_bonus_points else ""
    gear = f" • **{result.modifier_item.title()} used**" if result.modifier_item else ""
    guard = " • Guard reduced incoming damage" if result.guarded else ""
    return (f"🎯 **{name}** hit with a **{result.style.title()}**!{extra}{ko}\n"
            f"**Warmth damage:** {result.warmth_damage}{shield}{gear}{guard}\n"
            f"**Your points:** +{result.points_awarded}{bonus}"
            + (f" • Defender +{result.defense_points} defence" if result.defense_points else "")
            + "\nCooldown: 30s. Your attack was saved safely.")


class CombatMenu(discord.ui.View):
    """Selection, confirmation and result are edited in the same private message."""
    def __init__(self, settings, store, owner_id: int, timeout=180):
        super().__init__(timeout=timeout)
        self.settings, self.store = pin(settings, store)
        self.owner_id = owner_id
        from snowfall.ui.navigation import attach_game_navigation
        attach_game_navigation(self, self.settings, self.store, self.owner_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day has ended.", ephemeral=True)
            return False
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
            await interaction.response.edit_message(
                content=f"⚠️ {exc}", view=RetryView(self.settings, self.store, self.owner_id),
                embed=None, attachments=[])
            return
        if not targets:
            await interaction.response.edit_message(
                content="No eligible rivals right now. Ask people to `/snow ready`, or return later.",
                view=RetryView(self.settings, self.store, self.owner_id),
                embed=None, attachments=[],
            )
            return
        try:
            intel = await asyncio.to_thread(CombatIntelEngine(self.store).snapshot,
                                            self.settings.season_key, self.owner_id)
        except (ValueError, sqlite3.Error):
            intel = None
        alerts = len(intel.revenge_alerts) if intel is not None else 0
        await interaction.response.edit_message(
            content="🎯 **Choose a rival from another city:**"
                    + (f"\n🔔 **{alerts} private revenge alert(s)** in your rivalry dossier."
                       if alerts else ""),
            view=TargetPicker(self.settings, self.store, interaction.user.id, targets,
                              intel=intel),
            embed=None, attachments=[],
        )


def suggested_targets(targets):
    """Prefer targets with two fresh legal scoring hits, then healthier rivals.

    Selection is an assistive sort only; CombatEngine re-checks eligibility and
    the two-hit cap inside the actual attack transaction.
    """
    return sorted(targets, key=lambda t: (-t.hits_remaining, -t.warmth,
                                           t.city.casefold(), t.mr_username.casefold(),
                                           t.discord_user_id))


async def open_target_menu(interaction, settings, store, owner_id, *, mode="smart"):
    """Re-read live eligibility and personal history; never auto-perform a throw."""
    settings, store = pin(settings, store)
    await interaction.response.defer()
    try:
        options = await asyncio.to_thread(CombatEngine(store).targets, settings.season_key,
                                          owner_id, _now())
        try:
            intel = await asyncio.to_thread(CombatIntelEngine(store).snapshot,
                                            settings.season_key, owner_id)
        except (ValueError, sqlite3.Error):
            intel = None
        ordered = target_order(options, intel, mode) if intel is not None else (
            suggested_targets(options) if mode != "revenge" else [])
        if ordered:
            view = TargetPicker(settings, store, owner_id, ordered, intel=intel, mode=mode)
            label = "pending revenge rivals" if mode == "revenge" else "eligible rival(s)"
            content = (f"🎯 **{len(ordered)} {label}** — "
                       "Choose a rival or use the quick-target buttons. All throws "
                       "still require confirmation and live eligibility checks.")
            if intel is not None and intel.revenge_alerts:
                content += f"\n🔔 **{len(intel.revenge_alerts)} pending revenge alert(s)** in your history."
        else:
            view = RetryView(settings, store, owner_id)
            content = ('No pending revenge rivals are currently eligible. An alert '
                       'does not override KO recovery, shields or scoring limits.'
                       if mode == "revenge" else
                       'No eligible rivals right now. Ask players in other cities to use /snow ready.')
    except (CombatError, ValueError) as exc:
        view = RetryView(settings, store, owner_id)
        content = f"⚠️ {exc}"
    await interaction.edit_original_response(content=content, embed=None,
                                              attachments=[], view=view,
                                              allowed_mentions=discord.AllowedMentions.none())


class TargetPicker(CombatMenu):
    def __init__(self, settings, store, owner_id: int, targets, *, intel=None, mode="smart"):
        super().__init__(settings, store, owner_id)
        settings, store = self.settings, self.store
        self.intel = intel
        self.mode = mode
        self.targets = target_order(targets, intel, mode) if intel is not None else suggested_targets(targets)
        self.names = {str(t.discord_user_id): t.mr_username for t in self.targets}
        options = [discord.SelectOption(
            label=f"{'🔔 ' if intel and intel.rival(t.discord_user_id) and intel.rival(t.discord_user_id).pending_revenge else ''}{t.mr_username} — {t.city}"[:100],
            description=f"Warmth {t.warmth}/100 · {t.hits_remaining} scored hits left"[:100],
            value=str(t.discord_user_id),
        ) for t in self.targets]
        selector = discord.ui.Select(placeholder="Select a rival player", options=options)

        async def chosen(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=f"🎯 **Target:** {escape_name(self.names[selector.values[0]])}\n"
                        "Select the throw to preview its accuracy and damage:",
                view=ThrowMenu(settings, store, owner_id, int(selector.values[0]),
                               self.names[selector.values[0]]),
                embed=None, attachments=[],
            )

        selector.callback = chosen
        self.add_item(selector)

    async def _surprise(self, interaction, mode="random"):
        # Read eligibility at selection. CombatEngine checks again on confirmation.
        try:
            pool = await asyncio.to_thread(CombatEngine(self.store).targets,
                                            self.settings.season_key, self.owner_id, _now())
        except CombatError as exc:
            await interaction.response.edit_message(content=f"⚠️ {exc}", embed=None,
                attachments=[], view=RetryView(self.settings, self.store, self.owner_id))
            return
        try:
            intel = await asyncio.to_thread(CombatIntelEngine(self.store).snapshot,
                                             self.settings.season_key, self.owner_id)
        except (ValueError, sqlite3.Error):
            intel = None  # Rivalry history is optional: target browsing must still work.
        if mode == "random":
            ordered = pool  # Keep the engine's original pool unmodified for uniform choice.
        elif intel is not None:
            ordered = target_order(pool, intel, mode)
        elif mode == "revenge":
            ordered = []  # Never fabricate a pending revenge match.
        elif mode == "vulnerable":
            ordered = sorted(pool, key=lambda t: (t.warmth, t.mr_username.casefold()))
        else:
            ordered = suggested_targets(pool)
        if not ordered:
            await interaction.response.edit_message(
                content=("No revenge rivals are eligible. Alerts do not bypass "
                         "shields, recovery or the daily cap." if mode == "revenge"
                         else "No eligible rivals left. Try later."),
                embed=None, attachments=[],
                view=RetryView(self.settings, self.store, self.owner_id))
            return
        target = secrets.choice(ordered) if mode == "random" else ordered[0]
        labels = {"smart": "Recommended rival", "random": "Surprise rival",
                  "revenge": "Revenge target", "vulnerable": "Low-warmth rival"}
        await interaction.response.edit_message(
            content=f"🎯 **{labels[mode]}: {escape_name(target.mr_username)}** ({target.city}) — "
                    f"{target.hits_remaining} scored hit(s) available. Choose your throw:",
            view=ThrowMenu(self.settings, self.store, self.owner_id,
                           target.discord_user_id, target.mr_username),
            embed=None, attachments=[])

    @discord.ui.button(label="Recommended Rival", emoji="✨", style=discord.ButtonStyle.primary, row=1)
    async def recommended(self, interaction, _):
        await self._surprise(interaction, mode="smart")

    @discord.ui.button(label="Surprise Me", emoji="🎲", style=discord.ButtonStyle.success, row=1)
    async def random_rival(self, interaction, _):
        await self._surprise(interaction, mode="random")

    @discord.ui.button(label="Revenge Rival", emoji="🔔", style=discord.ButtonStyle.primary, row=1)
    async def revenge(self, interaction, _):
        await self._surprise(interaction, mode="revenge")

    @discord.ui.button(label="Low Warmth", emoji="🥶", style=discord.ButtonStyle.secondary, row=1)
    async def low_warmth(self, interaction, _):
        await self._surprise(interaction, mode="vulnerable")

    @discord.ui.button(label="Rivalry Dossier", emoji="📜", style=discord.ButtonStyle.secondary, row=2)
    async def dossier(self, interaction, _):
        from snowfall.ui.rivalries import show_rivalries
        await show_rivalries(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Refresh Targets", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction, _):
        await open_target_menu(interaction, self.settings, self.store, self.owner_id)


class ThrowMenu(CombatMenu):
    def __init__(self, settings, store, owner_id: int, target_id: int, name: str):
        super().__init__(settings, store, owner_id)
        self.target_id, self.name = target_id, name
        if getattr(self.settings, "mode", "production") == "practice":
            drill = discord.ui.Button(label="Tactics Lab", emoji="🧪",
                                      style=discord.ButtonStyle.secondary, row=1)
            async def open_lab(interaction):
                from snowfall.ui.combat_lab import CombatLab
                view = CombatLab(self.settings, self.store, self.owner_id, self.target_id, self.name)
                await interaction.response.edit_message(
                    content=view._description(), view=view, embed=None, attachments=[])
            drill.callback = open_lab
            self.add_item(drill)

    async def _choose(self, interaction: discord.Interaction, style: str):
        chance, damage, score = ATTACKS[style]
        spent = "1 Golden Snowball" if style == "golden" else "1 regular snowball"
        await interaction.response.edit_message(
            content=(f"❄️ **Confirm {style.title()}** against **{escape_name(self.name)}**?\n"
                     f"Hit chance: **{int(chance*100)}%** | Warmth damage: **{damage}** | "
                     f"Points on hit: **{score}** before bonuses.\n"
                     f"Cost: **{spent}**. Cooldown: **30 seconds**.\n"
                     "Mittens, bombs and opposing guard can modify this preview. "
                     "Target eligibility and protection are checked on confirmation."),
            view=ConfirmThrow(self.settings, self.store, self.owner_id,
                              self.target_id, self.name, style),
            embed=None, attachments=[],
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

    @discord.ui.button(label="Golden · 80%", emoji="✨", style=discord.ButtonStyle.success)
    async def golden(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._choose(interaction, "golden")

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
                ), embed=None, attachments=[],
            )
            return
        # The battle is committed before reading statistics or drawing art.
        # Visual failures cannot revert, duplicate or change an official throw.
        beat = None
        try:
            intel = await asyncio.to_thread(CombatIntelEngine(self.store).snapshot,
                                            self.settings.season_key, self.owner_id)
            beat = fight_beat(result, intel)
        except (ValueError, sqlite3.Error):
            pass
        caption = _result_text(result, self.name)
        if beat is not None:
            caption += (f"\n🎙️ *{beat.reaction}*"
                        f"\n🔥 Scored-hit streak: **{beat.streak}**"
                        f" (best **{beat.personal_best}**) · "
                        f"Rivalry hits: **{beat.pair_hits}–{beat.pair_received}**")
            if beat.revenge:
                caption += "\n🔔 **REVENGE LANDED!** Your retaliation is on the record."
        await delivery.edit_result(
            interaction, caption,
            RetryView(self.settings, self.store, self.owner_id,
                      target_id=self.target_id, target_name=self.name),
            lambda: cards.battle_card(result, self.name, beat=beat),
            alt=(f"{self.style} throw against {self.name}: "
                 f"{'hit' if result.hit else 'miss'}; "
                 f"{result.warmth_damage} damage, {result.points_awarded} points"),
            animate=lambda: cards.hit_animation(result, self.name, beat=beat),
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._targets(interaction)


class RetryView(CombatMenu):
    def __init__(self, settings, store, owner_id, *, target_id=None, target_name=None):
        super().__init__(settings, store, owner_id)
        if target_id is not None and target_name:
            button = discord.ui.Button(label="Rematch Preview", emoji="🎯",
                                       style=discord.ButtonStyle.primary, row=1)
            async def rematch(interaction):
                await interaction.response.edit_message(
                    content=f"🎯 Rematch with {escape_name(target_name)}? "
                            "Choose a throw; live eligibility is verified on confirmation.",
                    embed=None, attachments=[],
                    view=ThrowMenu(self.settings, self.store, self.owner_id,
                                   target_id, target_name))
            button.callback = rematch
            self.add_item(button)

    @discord.ui.button(label="Rivalry Dossier", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def dossier(self, interaction, _):
        from snowfall.ui.rivalries import show_rivalries
        await show_rivalries(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label='Surprise Me', emoji='🎲', style=discord.ButtonStyle.success)
    async def surprise(self, interaction, _):
        await open_target_menu(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Choose Another Target", style=discord.ButtonStyle.primary)
    async def another(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._targets(interaction)


async def send_target_menu(interaction: discord.Interaction, settings, store):
    """For slash commands or dashboard; caller must defer response ephemerally."""
    settings, store = pin(settings, store)
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
    try:
        intel = await asyncio.to_thread(CombatIntelEngine(store).snapshot,
                                        settings.season_key, interaction.user.id)
    except (ValueError, sqlite3.Error):
        intel = None
    alerts = len(intel.revenge_alerts) if intel is not None else 0
    await interaction.followup.send(
        "🎯 **Pick a rival:**" + (f"\n🔔 {alerts} revenge alert(s) in your dossier."
                                  if alerts else ""),
        view=TargetPicker(settings, store, interaction.user.id, targets, intel=intel),
        ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
    )
