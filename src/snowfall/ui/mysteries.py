"""Owner-checked one-message Christmas detective desk and seven-day casebook."""
from __future__ import annotations

import asyncio
from io import BytesIO
import sqlite3
from datetime import datetime, timezone

import discord

from snowfall.graphics import delivery, mystery_cards
from snowfall.practice import pin
from snowfall.services.mysteries import (
    MysteryEngine, MysteryError, SECRET_CHOICES,
)
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now():
    return datetime.now(timezone.utc)


def _safe(text):
    return discord.utils.escape_markdown(str(text)).replace("@", "＠").replace("\n", " ")


def case_text(snapshot, page="case", alert=""):
    """Private, accessible text, never leaks a suspect answer before solving."""
    parts = ["🕵️ **THE WINTER UNDERWORLD — CHRISTMAS MYSTERIES**",
             "Seven daily cases and hidden encounters. **No game points, "
             "Snowflakes, paid prizes or extra combat rewards.**"]
    if snapshot.case is not None:
        case = snapshot.case
        parts += [f"**Day {case.day}/7 — {_safe(case.title)}**",
                  _safe(case.scene)]
        if page == "secret":
            if snapshot.secret is not None:
                parts += [f"🎁 **{_safe(snapshot.secret.title)}**",
                          _safe(snapshot.secret.scene),
                          f"**Souvenir:** {_safe(snapshot.secret.souvenir)}",
                          "Your one secret encounter for this day has been recorded."]
            elif snapshot.secret_ready:
                parts += [f"✨ **SECRET DISCOVERED: {_safe(case.secret_title)}**",
                          _safe(case.secret_scene),
                          "Choose how to approach the stranger. Only one "
                          "cosmetic memento can be collected per event day."]
            else:
                parts.append("🔒 **Secret locked.** Examine at least two "
                             "leads and either earn official daily points "
                             "or complete the ordinary daily surprise encounter.")
        elif page == "book":
            parts.append(f"📚 **Cases solved:** {snapshot.solved_count}/7 "
                         f"· **Secret mementos:** {snapshot.souvenirs_count}/7")
        else:
            parts.append("📜 **Evidence Board**")
            for clue in snapshot.clues:
                parts.append(f"{'✅' if clue.found else '🔒'} "
                             f"**{_safe(clue.label)}**"
                             + (f" — {_safe(clue.text)}" if clue.found else
                                " — investigate to reveal"))
            if snapshot.solved:
                parts.append(f"✅ **CASE CLOSED.** {_safe(case.conclusion)}")
            elif snapshot.locked:
                parts.append("🔐 Your two accusations were incorrect. "
                             "The next case opens tomorrow.")
            else:
                parts.append("🎩 **Suspects:** " +
                             " · ".join(_safe(label) for _, label in case.suspects))
                parts.append(f"**Accusations remaining:** "
                             f"{2-snapshot.guesses}/2 · "
                             "Find two clues before accusing anyone.")
            if snapshot.secret is not None:
                parts.append(f"🎁 Secret memento: {_safe(snapshot.secret.souvenir)}")
            elif snapshot.secret_ready:
                parts.append("✨ **A hidden encounter has appeared.** Open Secret Encounter.")
            else:
                parts.append("🔍 Secret lead: two clues + real daily activity.")
    else:
        parts.append("The next mystery opens when the host starts a live event day. "
                     "Your completed casebook is still available to inspect.")
    if page == "book" or snapshot.case is None:
        parts.append("\n📚 **PERSONAL CASEBOOK**")
        for entry in snapshot.history:
            badge = "✅" if entry.solved else "▫️"
            souvenir = "🎁" if entry.secret else "—"
            parts.append(f"{badge} Day {entry.day} · {_safe(entry.title)} "
                         f"· {entry.clues}/3 clues · {entry.attempts}/2 guesses · {souvenir}")
        parts.append(f"**Total:** {snapshot.solved_count}/7 solved; "
                     f"{snapshot.souvenirs_count}/7 secret souvenirs.")
    if alert:
        parts.append(f"\n**{_safe(alert)}**")
    return "\n".join(parts)[:1950]


async def _snapshot(settings, store, owner):
    return await asyncio.to_thread(
        MysteryEngine(store).snapshot, settings.season_key, owner, _now())


async def show_mystery(interaction, settings, store, owner, *,
                       page="case", alert="", deferred=False):
    settings, store = pin(settings, store)
    if not deferred:
        await interaction.response.defer()
    try:
        snap = await _snapshot(settings, store, owner)
        view = MysteryView(settings, store, owner)
        if page == "book" or snap.case is None:
            def render():
                return mystery_cards.casebook_card(snap, city=getattr(
                    _player_city(settings, store, owner), "city", "Chicago"))
        elif page == "secret" and snap.secret is not None:
            def render():
                return mystery_cards.secret_postcard_card(snap)
        else:
            def render():
                return mystery_cards.case_file_card(snap)
        await delivery.edit_result(interaction, case_text(snap, page, alert), view,
                                   render, alt="Snowfall detective mystery evidence board")
    except (MysteryError, ValueError, sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}", embed=None, attachments=[],
            view=MysteryView(settings, store, owner),
            allowed_mentions=discord.AllowedMentions.none())


def _player_city(settings, store, owner):
    # Safe quick local read by the graphics worker; no Discord traffic.
    return store.get_player(settings.season_key, owner)


async def send_mystery(interaction, settings, store):
    """Slash-command entry after defer(ephemeral=True)."""
    settings, store = pin(settings, store)
    try:
        snap = await _snapshot(settings, store, interaction.user.id)
    except (MysteryError, ValueError, sqlite3.Error) as exc:
        await interaction.followup.send(f"⚠️ {_safe(exc)}",
                                        ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
        return
    view = MysteryView(settings, store, interaction.user.id)
    message = case_text(snap)
    try:
        png = await asyncio.to_thread(
            mystery_cards.case_file_card if snap.case else mystery_cards.casebook_card,
            snap)
        embed = discord.Embed(colour=discord.Colour.from_rgb(195, 165, 103))
        embed.set_image(url="attachment://casebook.png")
        await interaction.followup.send(
            content=message, ephemeral=True, view=view, embed=embed,
            file=discord.File(BytesIO(png), filename="casebook.png",
                              description="Detective evidence case file"),
            allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, OSError, ValueError, MemoryError):
        await interaction.followup.send(
            content=message, ephemeral=True, view=view,
            allowed_mentions=discord.AllowedMentions.none())


class MysteryView(MenuView):
    @discord.ui.button(label="Case File", emoji="🕵️",
                       style=discord.ButtonStyle.primary, row=0)
    async def case(self, interaction, _):
        await show_mystery(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Inspect Evidence", emoji="🔎",
                       style=discord.ButtonStyle.success, row=0)
    async def clues(self, interaction, _):
        try:
            snap = await _snapshot(self.settings, self.store, self.owner_id)
            if snap.case is None:
                await show_mystery(interaction, self.settings, self.store, self.owner_id,
                                   alert="No active case yet.")
                return
            await interaction.response.edit_message(
                content="🔍 **Inspect a clue.** Each distinct lead can be examined "
                        "once per day. Your evidence is saved automatically.",
                embed=None, attachments=[],
                view=MysteryChoice(self.settings, self.store, self.owner_id, "clue", snap))
        except (MysteryError, ValueError, sqlite3.Error) as exc:
            await interaction.response.send_message(f"⚠️ {_safe(exc)}", ephemeral=True)

    @discord.ui.button(label="Name Suspect", emoji="🎩",
                       style=discord.ButtonStyle.primary, row=0)
    async def suspect(self, interaction, _):
        try:
            snap = await _snapshot(self.settings, self.store, self.owner_id)
            if snap.case is None or snap.solved or snap.locked or sum(c.found for c in snap.clues) < 2:
                await show_mystery(interaction, self.settings, self.store, self.owner_id,
                                   alert="You need two clues and an open case to accuse a suspect.")
                return
            await interaction.response.edit_message(
                content="🎩 **Who is responsible?** You have up to two different "
                        "accusations. Answers are checked privately, with no prize consequences.",
                embed=None, attachments=[],
                view=MysteryChoice(self.settings, self.store, self.owner_id, "suspect", snap))
        except (MysteryError, ValueError, sqlite3.Error) as exc:
            await interaction.response.send_message(f"⚠️ {_safe(exc)}", ephemeral=True)

    @discord.ui.button(label="Secret Encounter", emoji="✨",
                       style=discord.ButtonStyle.success, row=1)
    async def secret(self, interaction, _):
        try:
            snap = await _snapshot(self.settings, self.store, self.owner_id)
            if not snap.secret_ready:
                await show_mystery(interaction, self.settings, self.store, self.owner_id,
                                   page="secret")
                return
            await interaction.response.edit_message(
                content=case_text(snap, "secret"), embed=None, attachments=[],
                view=MysteryChoice(self.settings, self.store, self.owner_id, "secret", snap))
        except (MysteryError, ValueError, sqlite3.Error) as exc:
            await interaction.response.send_message(f"⚠️ {_safe(exc)}", ephemeral=True)

    @discord.ui.button(label="My Casebook", emoji="📚",
                       style=discord.ButtonStyle.secondary, row=1)
    async def book(self, interaction, _):
        await show_mystery(interaction, self.settings, self.store, self.owner_id,
                           page="book")

    @discord.ui.button(label="Winter Activities", emoji="🎄",
                       style=discord.ButtonStyle.secondary, row=1)
    async def winter(self, interaction, _):
        from snowfall.ui.winter_fun import _display
        await _display(interaction, self.settings, self.store, self.owner_id, "Activities")

    @discord.ui.button(label="Game Menus", emoji="🎮",
                       style=discord.ButtonStyle.secondary, row=2)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠",
                       style=discord.ButtonStyle.secondary, row=2)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class MysteryChoice(MenuView):
    def __init__(self, settings, store, owner, mode, snapshot):
        super().__init__(settings, store, owner)
        if mode == "clue":
            options = [discord.SelectOption(
                label=clue.label, value=clue.key,
                description="Revisit evidence" if clue.found else "Inspect this hidden clue")
                for clue in snapshot.clues]
        elif mode == "suspect":
            options = [discord.SelectOption(label=name, value=key)
                       for key, name in snapshot.case.suspects]
        elif mode == "secret":
            options = [discord.SelectOption(label=name, value=key)
                       for key, (name, _) in SECRET_CHOICES.items()]
        else:
            raise ValueError("Unknown mystery interaction.")
        picker = discord.ui.Select(placeholder="Choose your next move",
                                   options=options, row=0)
        async def selected(interaction):
            await interaction.response.defer()
            engine = MysteryEngine(self.store)
            try:
                key = picker.values[0]
                if mode == "clue":
                    found, repeated = await asyncio.to_thread(
                        engine.investigate, self.settings.season_key,
                        self.owner_id, key, str(interaction.id), _now())
                    result = f"🔎 {found.label}: {found.text}"
                    if repeated:
                        result += " (Already recorded.)"
                elif mode == "suspect":
                    accused = await asyncio.to_thread(
                        engine.accuse, self.settings.season_key,
                        self.owner_id, key, str(interaction.id), _now())
                    result = (("✅ " if accused.correct else "❄️ ") + accused.message
                              + f" — {accused.attempts_used}/2 attempts")
                else:
                    discovered = await asyncio.to_thread(
                        engine.secret, self.settings.season_key,
                        self.owner_id, key, str(interaction.id), _now())
                    result = f"✨ {discovered.scene} Souvenir: {discovered.souvenir}"
                    if discovered.repeated:
                        result += " (Already recorded.)"
                await show_mystery(interaction, self.settings, self.store, self.owner_id,
                                   page="secret" if mode == "secret" else "case",
                                   alert=result, deferred=True)
            except (MysteryError, ValueError, sqlite3.Error) as exc:
                await interaction.edit_original_response(
                    content=f"⚠️ {_safe(exc)}", embed=None, attachments=[],
                    view=MysteryView(self.settings, self.store, self.owner_id),
                    allowed_mentions=discord.AllowedMentions.none())
        picker.callback = selected
        self.add_item(picker)

    @discord.ui.button(label="Back to Case File",
                       style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction, _):
        await show_mystery(interaction, self.settings, self.store, self.owner_id)
