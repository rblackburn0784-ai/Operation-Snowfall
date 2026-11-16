"""v0.1.6b: one-message private navigation, with host-only test controls.

Public dashboard remains persistent; clicking its Main Menu creates a private
message. All subsequent navigation edits that same private message. The host
panel ALWAYS uses the production settings for live status and an explicitly
separate PracticeManager for disposable rehearsal commands.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import sqlite3

import discord

from snowfall.core.permissions import is_host, permitted_guild
from snowfall.practice import pin, practice_expired, PracticeError
from snowfall.services.combat import CombatEngine, CombatError
from snowfall.services.economy import EconomyEngine, EconomyError
from snowfall.services.world import WorldEngine, WorldError
from snowfall.ops import check_health, reconcile, is_approved


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _host(settings, user_id: int) -> bool:
    return is_host(user_id, getattr(settings, "admin_user_ids", frozenset()))


def _mode(settings) -> str:
    return "🧪 TEST DAY — NO PRIZES" if getattr(settings, "mode", "production") == "practice" else "❄️ LIVE EVENT"


def _embed(title: str, description: str, settings, *, warning: bool = False) -> discord.Embed:
    colour = discord.Colour.orange() if warning else discord.Colour.from_rgb(106, 179, 219)
    card = discord.Embed(title=title, description=description, colour=colour)
    card.set_footer(text=f"{_mode(settings)} • v0.1.8 • Private navigation")
    return card


async def _edit(interaction: discord.Interaction, *, view, embed=None, content=None):
    """Acknowledge first and replace the existing ephemeral menu, including old art."""
    await interaction.response.defer()
    await interaction.edit_original_response(content=content, embed=embed, view=view,
                                             attachments=[], allowed_mentions=discord.AllowedMentions.none())


class MenuView(discord.ui.View):
    """Owner-checked, session-pinned navigation that fails closed after test reset."""

    def __init__(self, settings, store, owner_id: int, *, host_only: bool = False,
                 admin_context: bool = False):
        super().__init__(timeout=300)
        self.settings, self.store = pin(settings, store)
        self.owner_id = owner_id
        self.host_only = host_only
        self.admin_context = admin_context

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not permitted_guild(
                interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("This menu belongs to a different player or server.",
                                                    ephemeral=True)
            return False
        if self.host_only and not _host(self.settings, interaction.user.id):
            await interaction.response.send_message("Only configured hosts can use this panel.", ephemeral=True)
            return False
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day ended. Open `/snow menu` again.",
                                                    ephemeral=True)
            return False
        manager = getattr(interaction.client, "practice", None)
        if manager is not None and not self.admin_context:
            session = manager.session
            practice = getattr(self.settings, "mode", "production") == "practice"
            if practice and (session is None or session.id != self.settings.session_id or
                             interaction.channel_id != session.channel_id):
                await interaction.response.send_message("Old test menu. Run `/snow menu` in the active test channel.",
                                                        ephemeral=True)
                return False
            if not practice and session is not None and interaction.channel_id == session.channel_id:
                await interaction.response.send_message("Open `/snow menu` again for this test day.",
                                                        ephemeral=True)
                return False
        return True


async def _home_embed(settings, store) -> discord.Embed:
    from snowfall.ui.dashboard import dashboard_embed

    now = _now()
    season, people = await asyncio.gather(
        asyncio.to_thread(store.season, settings.season_key),
        asyncio.to_thread(store.registrations, settings.season_key),
    )
    card = dashboard_embed(settings, season, now, len(people))
    card.title = "❄️ Operation Snowfall — Main Menu"
    card.add_field(name="🏠 My Headquarters", value="Timers • Daily progress • What to do next", inline=False)
    card.add_field(name="🎮 Game Menus", value="Snowballs • Inventory • Quests • Boss • Siege", inline=False)
    card.add_field(name="🧑 My Player", value="Register, view stats and enter the arena", inline=False)
    card.add_field(name="🏆 Rankings", value="Individual prizes and honorary city standings", inline=False)
    card.add_field(name="🏅 Trophy Cabinet", value="Cosmetic achievements, titles and personal records", inline=False)
    card.set_footer(text=f"{_mode(settings)} • v0.1.8 • Only you can see this menu")
    return card


async def send_main_menu(interaction, settings, store):
    """For slash commands / public dashboard; caller has deferred ephemerally."""
    settings, store = pin(settings, store)
    card = await _home_embed(settings, store)
    await interaction.followup.send(embed=card,
                                    view=MainMenu(settings, store, interaction.user.id),
                                    ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def show_home(interaction, settings, store, owner_id: int):
    settings, store = pin(settings, store)
    await interaction.response.defer()
    try:
        card = await _home_embed(settings, store)
        await interaction.edit_original_response(content=None, embed=card,
            view=MainMenu(settings, store, owner_id), attachments=[])
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        await interaction.edit_original_response(content=f"⚠️ {exc}", embed=None,
            view=MainMenu(settings, store, owner_id), attachments=[])


async def show_game(interaction, settings, store, owner_id: int):
    settings, store = pin(settings, store)
    await _edit(interaction, view=GameMenu(settings, store, owner_id),
        embed=_embed("🎮 Game Menus", "Select a game section below. Every submenu has **Game Menus** and **Home** navigation.\n\n"
                     "🎯 Fight rivals  •  🎒 Craft & equip  •  🎄 Daily missions\n"
                     "☃️ Snow Don  •  🏰 City Siege  •  🏆 Rankings", settings))


async def show_player(interaction, settings, store, owner_id: int):
    settings, store = pin(settings, store)
    await _edit(interaction, view=PlayerMenu(settings, store, owner_id),
        embed=_embed("🧑 My Player", "Join a city, inspect your player card, or enter the arena.\n"
                     "Your actions and stats use the current live/test season only.", settings))


async def show_rankings(interaction, settings, store, owner_id: int):
    settings, store = pin(settings, store)
    await _edit(interaction, view=RankingsMenu(settings, store, owner_id),
        embed=_embed("🏆 Rankings", "**Individual standings** decide prizes.\n"
                     "**City standings** are honorary and never award credits or perks.\n"
                     "Use the buttons to view the current scores or podium.", settings))


async def show_rules(interaction, settings, store, owner_id: int):
    settings, store = pin(settings, store)
    from snowfall.ui.dashboard import rules_text
    await _edit(interaction, view=HelpMenu(settings, store, owner_id),
                content=rules_text(), embed=None)


class MainMenu(MenuView):
    def __init__(self, settings, store, owner_id: int):
        super().__init__(settings, store, owner_id)
        if not _host(self.settings, owner_id):
            self.remove_item(self.admin_button)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.primary)
    async def games(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="My Headquarters", emoji="🏠", style=discord.ButtonStyle.success, row=1)
    async def headquarters(self, interaction, _):
        from snowfall.ui.headquarters import show_headquarters
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Trophy Cabinet", emoji="🏆", style=discord.ButtonStyle.primary, row=2)
    async def trophies(self, interaction, _):
        from snowfall.ui.trophies import show_cabinet
        await show_cabinet(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="My Player", emoji="🧑", style=discord.ButtonStyle.secondary)
    async def player(self, interaction, _):
        await show_player(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Rankings", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def rankings(self, interaction, _):
        await show_rankings(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Rules & Help", emoji="📖", style=discord.ButtonStyle.secondary)
    async def help(self, interaction, _):
        await show_rules(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Admin / Test", emoji="🛠️", style=discord.ButtonStyle.danger)
    async def admin_button(self, interaction, _):
        await show_admin(interaction, self.owner_id)

    @discord.ui.button(label="Refresh Home", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class GameMenu(MenuView):
    @discord.ui.button(label="My Headquarters", emoji="🏠", style=discord.ButtonStyle.success, row=1)
    async def headquarters(self, interaction, _):
        from snowfall.ui.headquarters import show_headquarters
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Trophy Cabinet", emoji="🏆", style=discord.ButtonStyle.primary, row=2)
    async def trophies(self, interaction, _):
        from snowfall.ui.trophies import show_cabinet
        await show_cabinet(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Snowball Fight", emoji="🎯", style=discord.ButtonStyle.success)
    async def combat(self, interaction, _):
        from snowfall.ui.combat import TargetPicker
        await interaction.response.defer()
        try:
            targets = await asyncio.to_thread(CombatEngine(self.store).targets,
                                              self.settings.season_key, self.owner_id, _now())
            if not targets:
                msg = "No eligible rivals. Ask players from other cities to use `/snow ready`."
                view = GameMenu(self.settings, self.store, self.owner_id)
            else:
                msg = "🎯 **Pick a rival** — choose their name, then preview and confirm your throw."
                view = TargetPicker(self.settings, self.store, self.owner_id, targets)
        except CombatError as exc:
            msg, view = f"⚠️ {exc}", GameMenu(self.settings, self.store, self.owner_id)
        await interaction.edit_original_response(content=msg, embed=None, attachments=[], view=view)

    @discord.ui.button(label="Inventory & Craft", emoji="🎒", style=discord.ButtonStyle.primary)
    async def inventory(self, interaction, _):
        from snowfall.ui.economy import InventoryMenu, inventory_text
        await interaction.response.defer()
        try:
            data = await asyncio.to_thread(EconomyEngine(self.store).inventory,
                                           self.settings.season_key, self.owner_id, _now())
            msg = inventory_text(data)
            view = InventoryMenu(self.settings, self.store, self.owner_id)
        except EconomyError as exc:
            msg = f"⚠️ {exc}"
            view = GameMenu(self.settings, self.store, self.owner_id)
        await interaction.edit_original_response(content=msg, embed=None, attachments=[], view=view)

    @discord.ui.button(label="Daily Quests", emoji="🎄", style=discord.ButtonStyle.primary)
    async def quests(self, interaction, _):
        from snowfall.ui.economy import QuestsMenu, quests_text
        await interaction.response.defer()
        try:
            data = await asyncio.to_thread(EconomyEngine(self.store).quests,
                                           self.settings.season_key, self.owner_id, _now())
            msg = quests_text(data)
            view = QuestsMenu(self.settings, self.store, self.owner_id)
        except EconomyError as exc:
            msg = f"⚠️ {exc}"
            view = GameMenu(self.settings, self.store, self.owner_id)
        await interaction.edit_original_response(content=msg, embed=None, attachments=[], view=view)

    @discord.ui.button(label="Snow Don / Siege", emoji="☃️", style=discord.ButtonStyle.primary)
    async def world(self, interaction, _):
        from snowfall.ui.world import WorldView, status_text
        from snowfall.graphics import cards, delivery
        await interaction.response.defer()
        try:
            state = await asyncio.to_thread(WorldEngine(self.store).status,
                                            self.settings.season_key, self.owner_id, _now())
            await delivery.edit_result(interaction, status_text(state),
                WorldView(self.settings, self.store, self.owner_id),
                lambda: cards.world_status_card(state),
                alt=f"Day {state.day} Snow Don and city fortress status")
        except WorldError as exc:
            await interaction.edit_original_response(content=f"⚠️ {exc}", embed=None,
                attachments=[], view=GameMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Rankings", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def rankings(self, interaction, _):
        await show_rankings(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class PlayerMenu(MenuView):
    @discord.ui.button(label="Headquarters", emoji="🏠", style=discord.ButtonStyle.primary, row=1)
    async def headquarters(self, interaction, _):
        from snowfall.ui.headquarters import show_headquarters
        await show_headquarters(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Guided Start", emoji="📖", style=discord.ButtonStyle.secondary, row=1)
    async def guide(self, interaction, _):
        from snowfall.ui.headquarters import show_tour
        await show_tour(interaction, self.settings, self.store, self.owner_id, 0)

    @discord.ui.button(label="Trophy Cabinet", emoji="🏆", style=discord.ButtonStyle.primary, row=2)
    async def trophies(self, interaction, _):
        from snowfall.ui.trophies import show_cabinet
        await show_cabinet(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Join / Register", emoji="❄️", style=discord.ButtonStyle.primary)
    async def join(self, interaction, _):
        from snowfall.ui.dashboard import CityPicker
        stage = await asyncio.to_thread(self.store.season, self.settings.season_key)
        if stage.phase(_now()) not in ("registration", "ready", "live", "paused"):
            await _edit(interaction, view=PlayerMenu(self.settings, self.store, self.owner_id),
                        content="Registration has not opened or has closed. No changes were made.")
            return
        await _edit(interaction, content="❄️ Choose your MafiaReturns city and declare your username:",
                    view=CityPicker(self.settings, self.store, owner_id=self.owner_id))

    @discord.ui.button(label="My Profile", emoji="🧑", style=discord.ButtonStyle.secondary)
    async def profile(self, interaction, _):
        from snowfall.graphics import cards, delivery
        await interaction.response.defer()
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key, self.owner_id)
        if p is None:
            await interaction.edit_original_response(content="Not registered. Select **Join / Register**.",
                embed=None, attachments=[], view=PlayerMenu(self.settings, self.store, self.owner_id))
            return
        try:
            engine = CombatEngine(self.store)
            r = await asyncio.to_thread(engine.snapshot, self.settings.season_key,
                                        self.owner_id, _now())
            total = await asyncio.to_thread(engine.ledger_total,
                                            self.settings.season_key, self.owner_id)
        except CombatError as exc:
            await interaction.edit_original_response(content=f"⚠️ {exc}", embed=None,
                attachments=[], view=PlayerMenu(self.settings, self.store, self.owner_id))
            return
        from snowfall.ui.dashboard import escape_name
        msg = (f"**{escape_name(p.mr_username)}** — {p.city}\n"
               f"❄️ Snowballs: {r.snowballs}/12 • 🌡️ Warmth: {r.warmth}/100\n"
               f"⭐ Snowflakes: {r.snowflakes} • 🏆 Total points: {total}\n"
               "Use **Enter Arena** to become targetable for 36 active hours.")
        await delivery.edit_result(interaction, msg,
            PlayerMenu(self.settings, self.store, self.owner_id),
            lambda: cards.profile_card(p.mr_username, p.city, r, total, review=p.review_state),
            alt=f"Player profile for {p.mr_username}; {total} points")

    @discord.ui.button(label="Enter Arena", emoji="🛡️", style=discord.ButtonStyle.success)
    async def ready(self, interaction, _):
        await interaction.response.defer()
        try:
            await asyncio.to_thread(CombatEngine(self.store).ready,
                                    self.settings.season_key, self.owner_id, _now())
            msg = "✅ You're targetable for the next **36 effective event hours**. No points awarded."
        except CombatError as exc:
            msg = f"⚠️ {exc}"
        await interaction.edit_original_response(content=msg, embed=None, attachments=[],
            view=PlayerMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Rules", emoji="📖", style=discord.ButtonStyle.secondary)
    async def rules(self, interaction, _):
        await show_rules(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class RankingsMenu(MenuView):
    @discord.ui.button(label="Individuals", emoji="🥇", style=discord.ButtonStyle.primary)
    async def individual(self, interaction, _):
        from snowfall.ui.world import individual_board_text
        await interaction.response.defer()
        ranks = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                        self.settings.season_key, 10)
        await interaction.edit_original_response(content=individual_board_text(ranks),
            embed=None, attachments=[], view=RankingsMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Cities", emoji="🏙️", style=discord.ButtonStyle.secondary)
    async def cities(self, interaction, _):
        from snowfall.ui.world import city_board_text
        await interaction.response.defer()
        ranks = await asyncio.to_thread(WorldEngine(self.store).standings,
                                        self.settings.season_key, _now())
        await interaction.edit_original_response(content=city_board_text(ranks),
            embed=None, attachments=[], view=RankingsMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Podium", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def podium(self, interaction, _):
        from snowfall.graphics import cards, delivery
        from snowfall.ui.world import individual_board_text, city_board_text
        await interaction.response.defer()
        people, cities, season = await asyncio.gather(
            asyncio.to_thread(CombatEngine(self.store).leaderboard, self.settings.season_key, 3),
            asyncio.to_thread(WorldEngine(self.store).standings, self.settings.season_key, _now()),
            asyncio.to_thread(self.store.season, self.settings.season_key),
        )
        final = season.phase(_now()) in ("closed", "finalized")
        msg = ("**Provisional individual podium (no prizes until host approval)**\n"
               + individual_board_text(people) + "\n\n"
               + city_board_text(cities[:3]))
        await delivery.edit_result(interaction, msg,
            RankingsMenu(self.settings, self.store, self.owner_id),
            lambda: cards.champions_card(people, cities, final=final),
            alt="Top three individuals and honorary leading city")

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


class HelpMenu(MenuView):
    @discord.ui.button(label="Rules", emoji="📖", style=discord.ButtonStyle.primary)
    async def rules(self, interaction, _):
        await show_rules(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Privacy", emoji="🔒", style=discord.ButtonStyle.secondary)
    async def privacy(self, interaction, _):
        text = ("**Privacy & Fair Play**\n"
                "The game stores self-declared MR names, Discord IDs, chosen cities, scores and "
                "action logs. Host/staff review disputes. No MR credentials or payment data are used. "
                "Ask the organiser for the published retention deadline, a data copy or removal request.")
        await _edit(interaction, content=text, view=HelpMenu(self.settings, self.store, self.owner_id))

    @discord.ui.button(label="Game Menus", emoji="🎮", style=discord.ButtonStyle.secondary)
    async def game(self, interaction, _):
        await show_game(interaction, self.settings, self.store, self.owner_id)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary)
    async def home(self, interaction, _):
        await show_home(interaction, self.settings, self.store, self.owner_id)


# The host panel intentionally ignores TEST routing when viewing the official event.
def _host_sources(interaction):
    manager = getattr(interaction.client, "practice", None)
    if manager is not None:
        return manager.live_settings, manager.live_store, manager
    return interaction.client.settings, interaction.client.store, None


async def show_admin(interaction, owner_id: int):
    settings, store, manager = _host_sources(interaction)
    if not _host(settings, owner_id):
        await interaction.response.send_message("Only configured hosts can open this panel.", ephemeral=True)
        return
    await _edit(interaction, view=AdminPanel(settings, store, owner_id, manager),
                embed=_admin_embed(settings, manager))


async def send_admin_panel(interaction):
    """For /snowadmin panel. Caller must defer(ephemeral=True) first."""
    settings, store, manager = _host_sources(interaction)
    if not _host(settings, interaction.user.id):
        await interaction.followup.send("Only hosts can use this panel.", ephemeral=True)
        return
    await interaction.followup.send(embed=_admin_embed(settings, manager),
        view=AdminPanel(settings, store, interaction.user.id, manager), ephemeral=True)


def _admin_embed(settings, manager) -> discord.Embed:
    state = manager.snapshot(_now()) if manager is not None else {"active": False}
    practice_line = (f"Day {state['day']}/7 in <#{state['channel_id']}> — {state['players']} players"
                     if state["active"] else "No practice session running")
    return _embed("🛠️ Admin / Test Control Panel",
                  "**LIVE EVENT:** status, launch checks, announcement previews and host commands.\n"
                  f"**TEST CENTRE:** {practice_line}\n\n"
                  "Start/change/end a test day through two-step confirmation. "
                  "**Test data is always separate from live scores and prizes.**", settings)


class AdminPanel(MenuView):
    def __init__(self, settings, store, owner_id, manager=None):
        super().__init__(settings, store, owner_id, host_only=True, admin_context=True)
        self.manager = manager

    @discord.ui.button(label="Test Centre", emoji="🧪", style=discord.ButtonStyle.primary)
    async def tests(self, interaction, _):
        await show_test_centre(interaction, self.owner_id, self.manager)

    @discord.ui.button(label="Live Status", emoji="📡", style=discord.ButtonStyle.secondary)
    async def status(self, interaction, _):
        await interaction.response.defer()
        season, people = await asyncio.gather(
            asyncio.to_thread(self.store.season, self.settings.season_key),
            asyncio.to_thread(self.store.registrations, self.settings.season_key),
        )
        card = _admin_embed(self.settings, self.manager)
        card.add_field(name="Production phase", value=season.phase(_now()), inline=True)
        card.add_field(name="Registered", value=str(len(people)), inline=True)
        card.add_field(name="Game day", value=str(season.day(_now()) or "—"), inline=True)
        await interaction.edit_original_response(content=None, embed=card, attachments=[], view=self)

    @discord.ui.button(label="Launch Checks", emoji="✅", style=discord.ButtonStyle.secondary)
    async def checks(self, interaction, _):
        await interaction.response.defer()
        try:
            health, ledger, approved = await asyncio.gather(
                asyncio.to_thread(check_health, self.store, self.settings.season_key,
                                  self.settings.backup_dir),
                asyncio.to_thread(reconcile, self.store, self.settings.season_key),
                asyncio.to_thread(is_approved, self.store, self.settings.season_key),
            )
            msg = (f"**LIVE Launch Readiness**\n"
                   f"SQLite: `{health['sqlite_check']}` • Schema: {health['schema_version']}\n"
                   f"Scoring audit: {'PASS' if ledger['ok'] else 'FAIL'}\n"
                   f"Last backup: `{health['latest_backup'] or 'NONE'}`\n"
                   f"Kat's approval: {'YES' if approved else 'NO'}\n"
                   "Live Discord permissions and prize verification still require a manual check.")
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            msg = f"⚠️ Unable to check live season: {exc}"
        await interaction.edit_original_response(content=msg, embed=None, attachments=[], view=self)

    @discord.ui.button(label="Broadcasts", emoji="📣", style=discord.ButtonStyle.secondary)
    async def broadcasts(self, interaction, _):
        await _edit(interaction, view=BroadcastMenu(self.settings, self.store,
                    self.owner_id, self.manager),
                    embed=_embed("📣 Live Broadcast Controls",
                        "Refresh the existing five-minute leaderboard or publish/update the current "
                        "day's announcement. Confirm before posting. Neither action touches test data.",
                        self.settings))

    @discord.ui.button(label="Host Commands", emoji="📋", style=discord.ButtonStyle.secondary)
    async def help(self, interaction, _):
        msg = ("**Other host commands** (typed in Discord for extra safeguards):\n"
               "`/snowadmin setup` • `start` • `pause` • `resume` • `finalize`\n"
               "`/snowadmin approve-launch` • `backup` • `review`\n"
               "`/snowadmin adjust-score` • `reconcile` • `export-prizes`\n"
               "All production lifecycle and payout-changing operations retain explicit "
               "confirmation/reason requirements.")
        await _edit(interaction, view=AdminPanel(self.settings, self.store,
                    self.owner_id, self.manager), content=msg)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction, _):
        # A host in a test channel gets the current test home; elsewhere live home.
        manager = self.manager
        session = manager.session if manager is not None else None
        if session is not None and session.channel_id == interaction.channel_id:
            await show_home(interaction, session.settings, session.store, self.owner_id)
        else:
            await show_home(interaction, self.settings, self.store, self.owner_id)


class BroadcastMenu(AdminPanel):
    def __init__(self, settings, store, owner_id, manager=None):
        super().__init__(settings, store, owner_id, manager)
        self.clear_items()  # Dedicated small host subpanel, not a second dashboard.
        for label, action in (("Update Leaderboard", "leaderboard"),
                              ("Announce Current Day", "announcement")):
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            async def trigger(interaction, action=action):
                await _edit(interaction,
                    view=BroadcastConfirm(self.settings, self.store, self.owner_id,
                                          self.manager, action),
                    content=f"⚠️ Confirm publishing **{action}** using LIVE data only?")
            button.callback = trigger
            self.add_item(button)
        back = discord.ui.Button(label="◀ Admin Panel", style=discord.ButtonStyle.secondary)
        async def back_cb(interaction):
            await show_admin(interaction, self.owner_id)
        back.callback = back_cb
        self.add_item(back)


class BroadcastConfirm(AdminPanel):
    def __init__(self, settings, store, owner_id, manager, action):
        super().__init__(settings, store, owner_id, manager)
        self.clear_items()
        proceed = discord.ui.Button(label="Confirm Live Publish", style=discord.ButtonStyle.danger)
        async def confirm(interaction):
            await interaction.response.defer()
            publisher = getattr(interaction.client, "broadcast", None)
            if publisher is None:
                result = "⚠️ Broadcast publisher unavailable."
            else:
                try:
                    if action == "leaderboard":
                        msg = await publisher.update_leaderboard(_now())
                    else:
                        msg = await publisher.publish_current_day(_now(), refresh_existing=True)
                    result = f"✅ LIVE {action} updated: {msg.jump_url}"
                except (discord.HTTPException, ValueError, RuntimeError, AttributeError) as exc:
                    result = f"⚠️ LIVE {action} not updated: {exc}"
            await interaction.edit_original_response(content=result, embed=None, attachments=[],
                 view=AdminPanel(self.settings, self.store, self.owner_id, self.manager))
        proceed.callback = confirm
        self.add_item(proceed)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_cb(interaction):
            await show_admin(interaction, self.owner_id)
        cancel.callback = cancel_cb
        self.add_item(cancel)


def _test_embed(settings, manager) -> discord.Embed:
    state = manager.snapshot(_now()) if manager else {"active": False}
    if state["active"]:
        detail = (f"**Day {state['day']}/7 — {state['theme']}**\n"
                  f"Channel <#{state['channel_id']}> • {state['players']} test players\n"
                  f"Special feature: {state['bonus']}\n")
    else:
        detail = "**No active test day.** Open this panel in your dedicated `#snowfall-testing` channel.\n"
    return _embed("🧪 TEST CENTRE — Day 1–7", detail +
                  "\n**Start / Switch:** choose any day and confirm.\n"
                  "**End:** delete or archive the disposable SQLite session.\n"
                  "Your real #leaderboard, #Announcements, official results and prizes remain untouched.",
                  settings, warning=True)


async def show_test_centre(interaction, owner_id: int, manager):
    if manager is None:
        await _edit(interaction, content="⚠️ Practice manager unavailable.", view=None)
        return
    settings, store = manager.live_settings, manager.live_store
    await _edit(interaction, embed=_test_embed(settings, manager),
                view=TestCentre(settings, store, owner_id, manager))


class TestCentre(AdminPanel):
    def __init__(self, settings, store, owner_id, manager):
        super().__init__(settings, store, owner_id, manager)
        self.clear_items()
        for name, mode in (("▶ Start Day", "start"), ("🔄 Switch Day", "switch")):
            b = discord.ui.Button(label=name, style=discord.ButtonStyle.primary)
            async def callback(interaction, mode=mode):
                if mode == "start" and self.manager.session is not None:
                    await _edit(interaction, content="A test is already active. Use **Switch Day**.",
                                view=TestCentre(self.settings, self.store, self.owner_id, self.manager))
                    return
                if mode == "switch" and self.manager.session is None:
                    await _edit(interaction, content="Start a test before switching days.",
                                view=TestCentre(self.settings, self.store, self.owner_id, self.manager))
                    return
                await _edit(interaction, content=("Choose an event day to START" if mode == "start"
                      else "Choose the replacement day. Previous test points/items will be erased"),
                    view=TestDaySelect(self.settings, self.store, self.owner_id, self.manager, mode))
            b.callback = callback
            self.add_item(b)
        status = discord.ui.Button(label="🔎 Test Status", style=discord.ButtonStyle.secondary)
        async def status_cb(interaction):
            await show_test_centre(interaction, self.owner_id, self.manager)
        status.callback = status_cb
        self.add_item(status)
        for name, mode in (("🗑️ Stop & Delete", "delete"), ("🗄️ Stop & Archive", "archive")):
            b = discord.ui.Button(label=name, style=discord.ButtonStyle.danger)
            async def callback(interaction, mode=mode):
                await _edit(interaction, content=(
                    f"⚠️ **{mode.upper()} TEST DATA?**\nThis terminates the active test only. "
                    "All old practice buttons will be invalidated. Real scores/prizes stay unchanged."),
                    view=TestConfirm(self.settings, self.store, self.owner_id, self.manager, mode))
            b.callback = callback
            self.add_item(b)
        back = discord.ui.Button(label="◀ Admin Panel", style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction):
            await show_admin(interaction, self.owner_id)
        back.callback = back_cb
        self.add_item(back)
        home = discord.ui.Button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)
        async def home_cb(interaction):
            session = self.manager.session
            if session is not None and session.channel_id == interaction.channel_id:
                await show_home(interaction, session.settings, session.store, self.owner_id)
            else:
                await show_home(interaction, self.settings, self.store, self.owner_id)
        home.callback = home_cb
        self.add_item(home)


class TestDaySelect(AdminPanel):
    def __init__(self, settings, store, owner_id, manager, action):
        super().__init__(settings, store, owner_id, manager)
        self.clear_items()
        selector = discord.ui.Select(placeholder="Pick TEST Day 1–7", options=[
            discord.SelectOption(label=f"Day {day}", value=str(day)) for day in range(1, 8)])
        async def choose(interaction):
            day = int(selector.values[0])
            await _edit(interaction, content=(f"🧪 Confirm **TEST DAY {day}**? "
                  + ("Current test results will be discarded. " if action == "switch" else "")
                  + "No production data will be changed."),
                  view=TestConfirm(self.settings, self.store, self.owner_id, self.manager,
                                   action, day=day, channel_id=interaction.channel_id))
        selector.callback = choose
        self.add_item(selector)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_cb(interaction):
            await show_test_centre(interaction, self.owner_id, self.manager)
        cancel.callback = cancel_cb
        self.add_item(cancel)


class TestConfirm(AdminPanel):
    def __init__(self, settings, store, owner_id, manager, action, *, day=None, channel_id=None):
        super().__init__(settings, store, owner_id, manager)
        self.clear_items()
        self.action, self.day, self.channel_id = action, day, channel_id
        proceed = discord.ui.Button(label="✅ Confirm Test Action", style=discord.ButtonStyle.danger)
        async def go(interaction):
            await interaction.response.defer()
            try:
                if self.action == "start":
                    sess = await asyncio.to_thread(self.manager.start, self.day,
                        self.channel_id, self.owner_id, _now())
                    msg = f"✅ TEST Day {sess.day} started in <#{sess.channel_id}>."
                elif self.action == "switch":
                    sess = await asyncio.to_thread(self.manager.change_day, self.day,
                                                   self.owner_id, _now())
                    msg = f"✅ Switched to TEST Day {sess.day}. Previous test results erased."
                elif self.action in ("delete", "archive"):
                    archived = await asyncio.to_thread(self.manager.end,
                                                       archive=self.action == "archive")
                    msg = (f"✅ TEST ended. Archive: `{archived.name}`." if archived else
                           "✅ TEST ended. Disposable data deleted.")
                else:
                    raise PracticeError("Invalid test panel action")
            except (PracticeError, OSError, ValueError, sqlite3.Error) as exc:
                msg = f"⚠️ Test action refused: {exc}"
            await interaction.edit_original_response(content=msg +
                "\nOfficial event state is unchanged. Use `/snow menu` in the test channel to play.",
                embed=None, attachments=[], view=TestCentre(self.settings, self.store,
                                                              self.owner_id, self.manager))
        proceed.callback = go
        self.add_item(proceed)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_cb(interaction):
            await show_test_centre(interaction, self.owner_id, self.manager)
        cancel.callback = cancel_cb
        self.add_item(cancel)


def attach_game_navigation(view: discord.ui.View, settings, store, owner_id: int) -> None:
    """Append consistent Home / Game Menus buttons to existing combat/gear/boss UIs.

    Their original callbacks, artwork, confirmation screens and owner checks are
    unchanged; navigation switches the same ephemeral message and clears old art.
    """
    settings, store = pin(settings, store)
    games = discord.ui.Button(label="◀ Game Menus", style=discord.ButtonStyle.secondary,
                              row=4)
    home = discord.ui.Button(label="🏠 Home", style=discord.ButtonStyle.secondary,
                             row=4)
    async def back(interaction):
        await show_game(interaction, settings, store, owner_id)
    async def root(interaction):
        await show_home(interaction, settings, store, owner_id)
    games.callback = back
    home.callback = root
    view.add_item(games)
    view.add_item(home)
