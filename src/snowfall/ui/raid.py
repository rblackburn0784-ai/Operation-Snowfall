"""Private, owner-checked v0.2.4 cooperative Snow Don Raid HQ.

All pages are read-only. Player-selected Attack delegates to WorldConfirm,
which uses the original authoritative WorldEngine transaction. Victory Replay
only reads the original final-blow record; it cannot award an extra prize.
"""
from __future__ import annotations

import asyncio
import sqlite3

import discord

from snowfall.graphics import delivery, cards
from snowfall.graphics.raid_cards import (
    raid_board_card, raid_leaders_card, final_defeat_cinematic,
)
from snowfall.practice import pin
from snowfall.services.boss_raid import RaidEngine
from snowfall.services.world import WorldEngine, WorldError
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _escape(value: object) -> str:
    return discord.utils.escape_markdown(str(value)).replace("@", "＠")


def raid_text(raid, user_id: int, *, page="Overview") -> str:
    """Always includes a useful text-only fallback for image/Discord errors."""
    content = [
        f"☃️ **Snow Don Raid HQ — Day {raid.day}/7** · **{raid.phase}**",
        (f"**Shared HP:** {raid.remaining_hp}/{raid.max_hp} "
         f"· **Co-op progress:** {raid.progress}% "
         f"· **Active raiders:** {raid.contributors}"),
        ("**Milestones:** " +
         ", ".join(f"{n}% ✅" if n in raid.milestones else f"{n}% ▫️"
                   for n in (25, 50, 75, 100))),
    ]
    if not raid.enabled:
        content.append("The boss is disabled by the event organiser.")
    elif raid.defeated:
        content.append(f"🏆 **The Snow Don has fallen!** "
                       f"Finishing snowball: **{_escape(raid.final_hitter or 'Unknown')}**."
                       " Use **Victory Replay** to watch the cinematic.")
    else:
        next_target = f"{raid.next_milestone}%" if raid.next_milestone else "Victory"
        content.append(f"**Next co-op milestone:** {next_target} · "
                       "Everyone's legal shared boss hits advance the same HP bar.")
    mine = raid.member(user_id)
    if mine:
        content.append(f"**Your raid record:** {mine.shared_damage} shared damage, "
                       f"{mine.shared_hits} real hits, {mine.echo_attacks} echo drills "
                       f"from {mine.attacks} attempts.")
    else:
        content.append("**Your raid record:** No boss attacks logged today.")
    if page == "Raiders":
        content.append("\n**🏅 Raider Contributions (shared damage only)**")
        for idx, entry in enumerate(raid.members[:8], 1):
            content.append(f"{idx}. **{_escape(entry.name)}** · {_escape(entry.city)} — "
                           f"**{entry.shared_damage}** damage, "
                           f"{entry.shared_hits} hits"
                           + (" · 🏁 Finisher" if entry.final_blow else ""))
        if not raid.members:
            content.append("The raid roster is empty. Be the first to take part!")
    elif page == "City Crews":
        content.append("\n**🏙️ Co-operating Cities**")
        for entry in raid.cities:
            content.append(f"**{_escape(entry.name)}:** {entry.damage} shared damage "
                           f"· {entry.raiders} raider(s)")
        if not raid.cities:
            content.append("No city has dealt damage yet.")
        content.append("**Cross-city rally:** "
                       + ("✅ Complete" if len(raid.cities) >= 2 else
                          "Join the fight from two different cities."))
    elif page == "Raid Goals":
        goals = (
            ("First Wave", raid.contributors >= 3,
             f"{raid.contributors}/3 unique raiders"),
            ("Cross-City Alliance", len(raid.cities) >= 2,
             f"{len(raid.cities)}/2 cities with real shared hits"),
            ("Frostbreaker", raid.shared_damage >= 100,
             f"{min(raid.shared_damage,100)}/100 shared damage"),
            ("The Don Falls", raid.defeated, "Defeat the shared Snow Don"),
        )
        content.append("\n**🤝 Cooperative Raid Objectives**")
        for title, done, progress in goals:
            content.append(f"{'✅' if done else '▫️'} **{title}** — {progress}")
        content.append("Objectives grant **recognition only**, not extra scoring rewards.")
    else:
        content.append(f"**Raid activity:** {raid.hit_count} real hits "
                       f"· {raid.misses} missed shared attempts "
                       f"· {raid.echo_attacks} late training attempts.")
        if raid.members:
            captain = raid.members[0]
            content.append(f"**Damage leader:** {_escape(captain.name)} "
                           f"({captain.shared_damage} HP contributed)")
    content.append(
        "\n*Individual scores and existing once-only defeat rewards remain unchanged. "
        "Echo training does not damage the shared boss or count towards raid honours.*"
    )
    return "\n".join(content)[:1850]


async def _load(settings, store, owner):
    status = await asyncio.to_thread(WorldEngine(store).status,
                                     settings.season_key, owner, _now())
    if status.day is None:
        raise ValueError("The boss raid is not open yet.")
    raid = await asyncio.to_thread(RaidEngine(store).report, settings.season_key,
                                   status.day)
    return status, raid


async def show_raid(interaction, settings, store, owner_id, *, page="Overview"):
    """Edit the current ephemeral menu exactly once."""
    settings, store = pin(settings, store)
    await interaction.response.defer()
    view = RaidView(settings, store, owner_id)
    try:
        status, raid = await _load(settings, store, owner_id)
        if page == "Raiders":
            def render():
                return raid_leaders_card(raid, city=status.city)
        else:
            def render():
                return raid_board_card(raid, viewer_id=owner_id, city=status.city)
        await delivery.edit_result(interaction, raid_text(raid, owner_id, page=page),
                                   view, render, alt=f"Day {raid.day} Snow Don "
                                   "raid milestones, shared damage and participants")
    except (WorldError, ValueError, sqlite3.Error) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_escape(exc)}", embed=None, attachments=[], view=view,
            allowed_mentions=discord.AllowedMentions.none())


async def send_raid(interaction, settings, store):
    """New ephemeral slash response; caller has already deferred."""
    settings, store = pin(settings, store)
    try:
        status, raid = await _load(settings, store, interaction.user.id)
    except (WorldError, ValueError, sqlite3.Error) as exc:
        await interaction.followup.send(f"⚠️ {_escape(exc)}", ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
        return
    try:
        from io import BytesIO
        payload = await asyncio.to_thread(raid_board_card, raid,
                                          viewer_id=interaction.user.id, city=status.city)
        embed = discord.Embed(colour=discord.Colour.from_rgb(131, 191, 239))
        embed.set_image(url="attachment://raid.png")
        await interaction.followup.send(
            content=raid_text(raid, interaction.user.id), embed=embed,
            file=discord.File(BytesIO(payload), filename="raid.png",
                              description="Shared Snow Don raid overview"),
            ephemeral=True, view=RaidView(settings, store, interaction.user.id),
            allowed_mentions=discord.AllowedMentions.none())
    except (OSError, ValueError, MemoryError, discord.HTTPException):
        await interaction.followup.send(
            content=raid_text(raid, interaction.user.id),
            ephemeral=True, view=RaidView(settings, store, interaction.user.id),
            allowed_mentions=discord.AllowedMentions.none())


class RaidView(MenuView):
    @discord.ui.button(label="Raid Overview", emoji="☃️", style=discord.ButtonStyle.primary)
    async def overview(self, interaction, _):
        await show_raid(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Top Raiders", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def leaders(self, interaction, _):
        await show_raid(interaction, self.settings, self.store, self.owner_id, page="Raiders")

    @discord.ui.button(label="City Crews", emoji="🏙️", style=discord.ButtonStyle.secondary)
    async def cities(self, interaction, _):
        await show_raid(interaction, self.settings, self.store, self.owner_id, page="City Crews")

    @discord.ui.button(label="Co-op Goals", emoji="🤝", style=discord.ButtonStyle.success)
    async def goals(self, interaction, _):
        await show_raid(interaction, self.settings, self.store, self.owner_id, page="Raid Goals")

    @discord.ui.button(label="Attack Snow Don", emoji="❄️", style=discord.ButtonStyle.danger, row=1)
    async def attack(self, interaction, _):
        from snowfall.ui.world import WorldConfirm
        await interaction.response.edit_message(
            content="☃️ **Confirm a real Snow Don attempt?** Costs one regular snowball, "
                    "uses the 30-second shared throw cooldown, "
                    "and counts towards six daily boss attempts.",
            embed=None, attachments=[], view=WorldConfirm(
                self.settings, self.store, self.owner_id, "boss"))

    @discord.ui.button(label="Victory Replay", emoji="🎬", style=discord.ButtonStyle.primary, row=1)
    async def replay(self, interaction, _):
        await interaction.response.defer()
        try:
            status, raid = await _load(self.settings, self.store, self.owner_id)
            final = await asyncio.to_thread(RaidEngine(self.store).final_result,
                                            self.settings.season_key, raid.day)
            if final is None:
                await interaction.edit_original_response(
                    content="🎬 The finale unlocks after a genuine shared boss defeat.",
                    embed=None, attachments=[],
                    view=RaidView(self.settings, self.store, self.owner_id))
                return
            await delivery.edit_result(
                interaction,
                f"🎬 **Victory Replay — Day {raid.day}/7**\n"
                f"The Snow Don was defeated by **{_escape(raid.final_hitter)}**. "
                f"{raid.contributors} raider(s) contributed. "
                "**Replay is cosmetic only:** no attack, ammo, points or prizes.",
                RaidView(self.settings, self.store, self.owner_id),
                lambda: cards.world_result_card(final),
                alt="Snow Don final defeat cinema replay — original saved fight",
                animate=lambda: final_defeat_cinematic(final))
        except (WorldError, ValueError, sqlite3.Error) as exc:
            await interaction.edit_original_response(
                content=f"⚠️ {_escape(exc)}", view=RaidView(
                    self.settings, self.store, self.owner_id),
                embed=None, attachments=[])

    @discord.ui.button(label="World Battles", emoji="🏰", style=discord.ButtonStyle.secondary, row=2)
    async def world(self, interaction, _):
        from snowfall.ui.world import WorldView, status_text
        await interaction.response.defer()
        try:
            state = await asyncio.to_thread(WorldEngine(self.store).status,
                                            self.settings.season_key, self.owner_id, _now())
            await delivery.edit_result(interaction, status_text(state),
                WorldView(self.settings, self.store, self.owner_id),
                lambda: cards.world_status_card(state),
                alt="Current boss and fortress status")
        except WorldError as exc:
            await interaction.edit_original_response(
                content=f"⚠️ {_escape(exc)}", view=RaidView(
                    self.settings, self.store, self.owner_id),
                embed=None, attachments=[])

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary, row=2)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=2)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)
