"""Five playable one-message private Discord games with honorary scoreboards.

Select controls are the only source of input; the service validates every move
against the persisted server-side puzzle. No shared mutable view state, scoring
actions, rewards, public mentions or background network requests.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import sqlite3

import discord

from snowfall.graphics import delivery, social_arcade_cards
from snowfall.practice import pin
from snowfall.services.social_arcade import (
    GAMES, STAMPS, DAILY_GAME_CAP, SocialArcadeEngine, SocialArcadeError,
)
from snowfall.ui.navigation import MenuView, show_game, show_home


def _now():
    return datetime.now(timezone.utc)


def _safe(value, length=96):
    return discord.utils.escape_markdown(
        str(value).replace("\n", " ")[:length]).replace("@", "＠")


def hub_text(lobby, alert=""):
    lines = ["🎮 **WINTER ARCADE & SOCIAL GAMES**",
             "Five games to play without spending a snowball. "
             "**Casual scores and stamps only — no official prizes.**",
             f"Day **{lobby.day or '—'}/7** · {lobby.phase.upper()} "
             f"· {lobby.completed} finished runs · {len(lobby.stamps)} passport stamps"]
    for r in lobby.records:
        spec = GAMES[r.mode]
        state = "Resume" if r.active_id else (
            "Daily limit" if r.attempts_today >= DAILY_GAME_CAP else "Play")
        lines.append(f"{spec.icon} **{spec.title}** · Best {r.personal_best}/100 "
                     f"· Runs {r.attempts_today}/3 today · **{state}**")
    lines.append("Choose a game from the dropdown, or browse the scoreboards "
                 "and your collectible passport. Runs resume after reconnecting.")
    if alert:
        lines.append(f"\n{_safe(alert)}")
    return "\n".join(lines)[:1920]


def game_text(session, *, alert="", stamps=()):
    lines = [f"{GAMES[session.mode].icon} **{session.title.upper()}**",
             f"Day **{session.day}/7** · Run **{session.attempt}/3** "
             f"· **{session.score}/100** arcade points",
             f"Rounds **{session.step}/{session.total_rounds}** · "
             "No snowballs or Snowflakes consumed."]
    if session.feedback:
        lines.append(f"📜 Previous round: {_safe(session.feedback)}")
    if session.finished:
        lines.append("🏁 **Game complete!** Your personal best and casual "
                     "leaderboard have been updated.")
        if stamps:
            lines.append("🏅 **New cosmetic passport stamps:** " +
                         " · ".join(_safe(STAMPS[k]) for k in stamps))
        lines.append("Use **Play Again** for another daily run, "
                     "or return to the arcade for a different game.")
    elif session.current:
        rnd = session.current
        lines.append(f"**Round {rnd.index}/{rnd.total} — {_safe(rnd.category)}**")
        lines.append(f"**{_safe(rnd.prompt, 260)}**")
        lines.append("Choose one of the three responses below. "
                     "The server reveals the result after your choice.")
    if alert:
        lines.append(f"\n**{_safe(alert)}**")
    return "\n".join(lines)[:1930]


def passport_text(lobby):
    lines = [f"🎟️ **MY WINTER ARCADE PASSPORT** — "
             f"{len(lobby.stamps)}/{len(STAMPS)} stamps",
             "**Earned by finishing games, scoring perfectly, and "
             "completing the five-game tour. Cosmetic display only.**"]
    for key, name in STAMPS.items():
        lines.append(f"{'✅' if key in lobby.stamps else '▫️'} {_safe(name)}")
    lines.append(f"\n**Total runs:** {lobby.completed} · "
                 f"**Combined personal bests:** {lobby.bests_total}/500 "
                 "(honorary, not an event score)")
    return "\n".join(lines)[:1910]


def leaderboard_text(mode, rows, period="season"):
    lines = [f"🏆 **{GAMES[mode].icon} {GAMES[mode].title} — "
             f"{period.title()} High Scores**",
             "*Best completed run per player. No bonus points or paid prizes.*"]
    if not rows:
        lines.append("No eligible completed runs yet. Try a game and set the pace!")
    for pos, row in enumerate(rows, 1):
        lines.append(f"**{pos}.** {_safe(row.name)} · {_safe(row.city)} "
                     f"— **{row.best}/100** · {row.games} completed runs")
    return "\n".join(lines)[:1920]


def city_text(rows, period="season"):
    lines = [f"🏙️ **WINTER ARCADE CITY CUP — {period.upper()}**",
             "Honorary city totals: sum of each eligible player's personal "
             "best in each of the five games. No paid prizes or territory control."]
    if not rows:
        lines.append("No eligible teams have finished a game yet.")
    for pos, row in enumerate(rows, 1):
        lines.append(f"**{pos}. {_safe(row.city)}** — "
                     f"{row.score} combined arcade points "
                     f"· {row.players} participating players")
    return "\n".join(lines)[:1920]


async def show_arcade(interaction, settings, store, owner,
                      *, screen="hub", mode="gallery", daily=False,
                      deferred=False, alert=""):
    settings, store = pin(settings, store)
    if not deferred:
        await interaction.response.defer()
    engine = SocialArcadeEngine(store)
    try:
        if screen == "hub" or screen == "passport":
            lobby = await asyncio.to_thread(engine.lobby, settings.season_key,
                                            owner, _now())
            message = (passport_text(lobby) if screen == "passport"
                       else hub_text(lobby, alert))
            view = ArcadeHubView(settings, store, owner)
            if screen == "passport":
                def render():
                    return social_arcade_cards.passport_card(lobby)
            else:
                def render():
                    return social_arcade_cards.lobby_card(lobby)
        elif screen == "board":
            rows = await asyncio.to_thread(engine.leaderboard, settings.season_key,
                                           owner, mode, _now(), daily=daily)
            period = "daily" if daily else "season"
            message = leaderboard_text(mode, rows, period)
            view = ArcadeBoardView(settings, store, owner, mode, daily=daily)
            def render():
                return social_arcade_cards.scoreboard_card(
                    f"{GAMES[mode].title} · {period}", rows)
        elif screen == "city":
            rows = await asyncio.to_thread(engine.city_table, settings.season_key,
                                           owner, _now(), daily=daily)
            period = "daily" if daily else "season"
            message = city_text(rows, period)
            view = ArcadeBoardView(settings, store, owner, mode, daily=daily)
            def render():
                return social_arcade_cards.scoreboard_card(
                    f"City Cup · {period}", rows)
        else:
            raise SocialArcadeError("Unknown arcade page.")
        await delivery.edit_result(interaction, message, view, render,
                                   alt="Winter Arcade games, personal stamps and honorary rankings")
    except (SocialArcadeError, sqlite3.Error, ValueError) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}",embed=None,attachments=[],
            view=ArcadeHubView(settings, store, owner),
            allowed_mentions=discord.AllowedMentions.none())


async def show_arcade_session(interaction, settings, store, owner, session_id,
                              *, deferred=False, alert="", stamps=()):
    settings, store = pin(settings, store)
    if not deferred:
        await interaction.response.defer()
    try:
        engine = SocialArcadeEngine(store)
        session = await asyncio.to_thread(engine.session, settings.season_key,
                                          owner, session_id, _now())
        lobby = await asyncio.to_thread(engine.lobby, settings.season_key,
                                        owner, _now())
        view = ArcadePlayView(settings, store, owner, session,
                              can_play=lobby.phase=="live",
                              can_again=(lobby.phase=="live" and
                                         lobby.record(session.mode).attempts_today<DAILY_GAME_CAP))
        await delivery.edit_result(
            interaction, game_text(session, alert=alert, stamps=stamps), view,
            lambda: social_arcade_cards.game_card(session),
            alt=f"Arcade {session.title}, round {session.step}/{session.total_rounds}, "
                f"score {session.score}/100")
    except (SocialArcadeError, sqlite3.Error, ValueError) as exc:
        await interaction.edit_original_response(
            content=f"⚠️ {_safe(exc)}",embed=None,attachments=[],
            view=ArcadeHubView(settings, store, owner),
            allowed_mentions=discord.AllowedMentions.none())


async def begin_game(interaction, settings, store, owner, mode, *, deferred=False):
    settings, store = pin(settings, store)
    if not deferred:
        await interaction.response.defer()
    try:
        session = await asyncio.to_thread(
            SocialArcadeEngine(store).begin, settings.season_key, owner, mode, _now())
        await show_arcade_session(interaction, settings, store, owner,
                                  session.session_id, deferred=True)
    except (SocialArcadeError, sqlite3.Error, ValueError) as exc:
        await show_arcade(interaction, settings, store, owner, deferred=True,
                          alert=str(exc))


async def send_arcade(interaction, settings, store):
    """New ephemeral slash entry after defer(ephemeral=True)."""
    settings, store = pin(settings, store)
    try:
        lobby = await asyncio.to_thread(
            SocialArcadeEngine(store).lobby,
            settings.season_key, interaction.user.id, _now())
    except (SocialArcadeError, ValueError, sqlite3.Error) as exc:
        await interaction.followup.send(
            f"⚠️ {_safe(exc)}", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())
        return
    view = ArcadeHubView(settings, store, interaction.user.id)
    msg = hub_text(lobby)
    try:
        png = await asyncio.to_thread(social_arcade_cards.lobby_card, lobby)
        embed = discord.Embed(colour=discord.Colour.from_rgb(139, 197, 216))
        embed.set_image(url="attachment://winter-arcade.png")
        await interaction.followup.send(
            content=msg, embed=embed, file=discord.File(
                BytesIO(png), filename="winter-arcade.png",
                description="The five-game Winter Arcade and personal record board"),
            view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, ValueError, OSError, MemoryError):
        await interaction.followup.send(content=msg,view=view,ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


class ArcadeHubView(MenuView):
    def __init__(self, settings, store, owner_id):
        super().__init__(settings,store,owner_id)
        picker = discord.ui.Select(
            placeholder="🎮 Choose a Winter Arcade game",
            options=[discord.SelectOption(
                label=spec.title, value=key,
                description=spec.description[:100])
                for key,spec in GAMES.items()],row=0)
        async def choose(interaction):
            await begin_game(interaction, self.settings, self.store, self.owner_id,
                             picker.values[0])
        picker.callback=choose
        self.add_item(picker)

    @discord.ui.button(label="Play a Game",emoji="🎮",
                       style=discord.ButtonStyle.success,row=1)
    async def help_pick(self, interaction, _):
        await interaction.response.send_message(
            "Choose one of the five games using the dropdown at the top of this arcade menu.",
            ephemeral=True)

    @discord.ui.button(label="High Scores",emoji="🏆",
                       style=discord.ButtonStyle.primary,row=1)
    async def board(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,screen="board")

    @discord.ui.button(label="City Cup",emoji="🏙️",
                       style=discord.ButtonStyle.secondary,row=1)
    async def city(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,screen="city")

    @discord.ui.button(label="My Passport",emoji="🎟️",
                       style=discord.ButtonStyle.primary,row=1)
    async def passport(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,screen="passport")

    @discord.ui.button(label="Refresh",emoji="🔄",
                       style=discord.ButtonStyle.secondary,row=1)
    async def refresh(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Winter Activities",emoji="🎄",
                       style=discord.ButtonStyle.secondary,row=2)
    async def winter(self, interaction, _):
        from snowfall.ui.winter_fun import _display
        await _display(interaction,self.settings,self.store,self.owner_id,"Activities")

    @discord.ui.button(label="Game Menus",emoji="🎮",
                       style=discord.ButtonStyle.secondary,row=2)
    async def games(self, interaction, _):
        await show_game(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Home",emoji="🏠",
                       style=discord.ButtonStyle.secondary,row=2)
    async def home(self, interaction, _):
        await show_home(interaction,self.settings,self.store,self.owner_id)


class ArcadePlayView(MenuView):
    def __init__(self, settings, store, owner_id, session, *,
                 can_play=True, can_again=False):
        super().__init__(settings,store,owner_id)
        self.session_id = session.session_id
        self.mode = session.mode
        if session.current is not None:
            for index, choice in enumerate(session.current.choices):
                btn=discord.ui.Button(
                    label=choice[:75],style=(
                        discord.ButtonStyle.success if index==0 else
                        discord.ButtonStyle.primary if index==1 else
                        discord.ButtonStyle.secondary),row=0,
                    disabled=not can_play)
                async def on_choice(interaction, selected=choice):
                    await interaction.response.defer()
                    try:
                        outcome = await asyncio.to_thread(
                            SocialArcadeEngine(self.store).move,
                            self.settings.season_key,self.owner_id,self.session_id,
                            session.step,selected,str(interaction.id),_now())
                        await show_arcade_session(
                            interaction,self.settings,self.store,self.owner_id,
                            self.session_id,deferred=True,
                            alert="Recorded." if not outcome.repeated else "Already recorded.",
                            stamps=outcome.new_stamps)
                    except (SocialArcadeError, sqlite3.Error, ValueError) as exc:
                        await show_arcade_session(
                            interaction,self.settings,self.store,self.owner_id,
                            self.session_id,deferred=True,alert=str(exc))
                btn.callback=on_choice
                self.add_item(btn)
        if session.finished and can_again:
            again=discord.ui.Button(label="Play Again",emoji="🔄",
                                    style=discord.ButtonStyle.success,row=1)
            async def try_again(interaction):
                await begin_game(interaction,self.settings,self.store,self.owner_id,
                                 session.mode)
            again.callback=try_again
            self.add_item(again)

    @discord.ui.button(label="Arcade Lobby",emoji="🎮",
                       style=discord.ButtonStyle.primary,row=1)
    async def lobby(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="High Scores",emoji="🏆",
                       style=discord.ButtonStyle.secondary,row=1)
    async def board(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,
                          screen="board",mode=self.mode)

    @discord.ui.button(label="My Passport",emoji="🎟️",
                       style=discord.ButtonStyle.secondary,row=1)
    async def passport(self, interaction, _):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,
                          screen="passport")

    @discord.ui.button(label="Game Menus",emoji="🎮",
                       style=discord.ButtonStyle.secondary,row=2)
    async def game(self, interaction, _):
        await show_game(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Home",emoji="🏠",
                       style=discord.ButtonStyle.secondary,row=2)
    async def home(self, interaction, _):
        await show_home(interaction,self.settings,self.store,self.owner_id)


class ArcadeBoardView(MenuView):
    def __init__(self,settings,store,owner_id,mode="gallery",*,daily=False):
        super().__init__(settings,store,owner_id)
        self.mode=mode
        self.daily=daily
        picker=discord.ui.Select(
            placeholder="Select a game's leaderboard",
            options=[discord.SelectOption(label=spec.title,value=key,
                                          default=mode==key)
                     for key,spec in GAMES.items()],row=0)
        async def select(interaction):
            await show_arcade(interaction,self.settings,self.store,self.owner_id,
                              screen="board",mode=picker.values[0],daily=self.daily)
        picker.callback=select
        self.add_item(picker)

    @discord.ui.button(label="Today's Best",emoji="📅",
                       style=discord.ButtonStyle.primary,row=1)
    async def today(self,interaction,_):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,
                          screen="board",mode=self.mode,daily=True)

    @discord.ui.button(label="Season Best",emoji="🏆",
                       style=discord.ButtonStyle.primary,row=1)
    async def season(self,interaction,_):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,
                          screen="board",mode=self.mode,daily=False)

    @discord.ui.button(label="City Cup",emoji="🏙️",
                       style=discord.ButtonStyle.secondary,row=1)
    async def city(self,interaction,_):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,
                          screen="city",mode=self.mode,daily=self.daily)

    @discord.ui.button(label="Passport",emoji="🎟️",
                       style=discord.ButtonStyle.secondary,row=1)
    async def passport(self,interaction,_):
        await show_arcade(interaction,self.settings,self.store,self.owner_id,
                          screen="passport")

    @discord.ui.button(label="Arcade Lobby",emoji="🎮",
                       style=discord.ButtonStyle.success,row=2)
    async def lobby(self,interaction,_):
        await show_arcade(interaction,self.settings,self.store,self.owner_id)

    @discord.ui.button(label="Home",emoji="🏠",
                       style=discord.ButtonStyle.secondary,row=2)
    async def home(self,interaction,_):
        await show_home(interaction,self.settings,self.store,self.owner_id)
