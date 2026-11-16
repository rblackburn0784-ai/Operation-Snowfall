"""Persistent main menu and self-declared registration interface."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from snowfall.practice import pin, practice_expired

from snowfall.core.permissions import permitted_guild
from snowfall.db.store import CITIES, RegistrationError


def escape_name(name: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(name))


def rules_text() -> str:
    return (
        "**❄️ Operation Snowfall — Community Christmas Event**\n"
        "Seven full days of snowball battles across six MafiaReturns city teams.\n"
        "• **Entry:** Self-declare your MR username and city. No MR password or account linking.\n"
        "• **Registration:** Opens 168 hours before scheduled kickoff; late entry is allowed.\n"
        "• **Prizes:** Only individual awards receive prizes. City titles are for bragging rights.\n"
        "• **Fair play:** One MR name per Discord account; impersonation reports go to staff.\n"
        "• **Privacy:** Declared names, Discord IDs and scores are stored; see `/snow privacy`.\n"
        "• **Combat:** `/snow ready` opts in to being targeted for 36 effective hours.\n"
        "• **Attacks:** Quick 75% / Standard 60% / Power 40%; 30s cooldown.\n"
        "• **Protection:** Two scoring hits per target/day, 15m anti-camping shield, 30m KO recovery.\n"
        "• **PvP limit:** 300 scored PvP points per player per game day.\n"
        "• **Economy:** Craft cocoa, forts, mittens and bombs; Golden is a rare present.\n"
        "• **Quests:** Three daily objectives (20 points + 2 Snowflakes each); one gift after a claim.\n"
        "This is a fan-community game, not a direct MafiaReturns account integration."
    )


def dashboard_embed(settings, season, now: datetime, registered: int) -> discord.Embed:
    stage = season.phase(now)
    opens = int(season.registration_opens().timestamp())
    starts = int(season.planned_start.timestamp())
    ending = season.projected_end(now)
    embed = discord.Embed(
        title=("🧪 Operation Snowfall — TEST ARENA" if settings.is_test else
               "❄️ Operation Snowfall — Event Headquarters"),
        description=(
            f"**Phase:** {stage.replace('_', ' ').title()}\n"
            f"**Registration:** <t:{opens}:F>\n"
            f"**Scheduled kickoff:** <t:{starts}:F>\n"
            f"**Projected end:** {f'<t:{int(ending.timestamp())}:F>' if ending else 'After host starts'}\n"
            f"**Current day:** {season.day(now) or '—'} / 7\n"
            f"**Registered players:** {registered}\n"
            "**Prizes:** Individual only. City standings = bragging rights."
        ),
        color=0x78B9EA,
    )
    embed.set_footer(text="v0.1.7 • TEST — NO PRIZES" if settings.is_test else
                     "v0.1.7 • Live event, individual prizes only")
    return embed


class JoinModal(discord.ui.Modal, title="Operation Snowfall — Register"):
    mr_username = discord.ui.TextInput(label="MafiaReturns username", min_length=2, max_length=32)
    declaration = discord.ui.TextInput(label="Type I AGREE to self-declare", min_length=7, max_length=7)

    def __init__(self, settings, store, city: str):
        super().__init__(timeout=180)
        self.settings, self.store = pin(settings, store)
        self.city = city

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day has ended.", ephemeral=True)
            return
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return
        if self.declaration.value.strip().upper() != "I AGREE":
            await interaction.response.send_message("Type I AGREE to confirm your own MR identity.", ephemeral=True)
            return
        # The database re-checks the time inside the write transaction.
        await interaction.response.defer(ephemeral=True)
        try:
            p = await asyncio.to_thread(
                self.store.register, self.settings.season_key, interaction.user.id,
                str(self.mr_username.value), self.city, datetime.now(timezone.utc))
        except RegistrationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ **{escape_name(p.mr_username)}** registered for **{p.city}**. "
            "Your claim is self-declared; staff may review identity disputes. "
            "Open `/snow hq` for resources, next steps and the daily quests!",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


class CityPicker(discord.ui.View):
    def __init__(self, settings, store, owner_id: int | None = None):
        super().__init__(timeout=180)
        settings, store = pin(settings, store)
        if owner_id is not None:
            back = discord.ui.Button(label="◀ My Player", style=discord.ButtonStyle.secondary, row=1)
            home = discord.ui.Button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)

            async def go_back(interaction):
                if interaction.user.id != owner_id or practice_expired(settings, store):
                    await interaction.response.send_message("This registration menu has expired.", ephemeral=True)
                    return
                from snowfall.ui.navigation import show_player
                await show_player(interaction, settings, store, owner_id)

            async def go_home(interaction):
                if interaction.user.id != owner_id or practice_expired(settings, store):
                    await interaction.response.send_message("This registration menu has expired.", ephemeral=True)
                    return
                from snowfall.ui.navigation import show_home
                await show_home(interaction, settings, store, owner_id)

            back.callback = go_back
            home.callback = go_home
            self.add_item(back)
            self.add_item(home)
        picker = discord.ui.Select(
            placeholder="Choose your MafiaReturns city",
            options=[discord.SelectOption(label=c, value=c) for c in CITIES])

        async def selected(interaction: discord.Interaction):
            if practice_expired(settings, store):
                await interaction.response.send_message("This test day has ended.", ephemeral=True)
                return
            if not permitted_guild(interaction.guild_id, settings.guild_id):
                await interaction.response.send_message("Wrong event server.", ephemeral=True)
                return
            if store.season(settings.season_key).phase(datetime.now(timezone.utc)) not in (
                    "registration", "ready", "live", "paused"):
                await interaction.response.send_message("Registration is not open.", ephemeral=True)
                return
            await interaction.response.send_modal(JoinModal(settings, store, picker.values[0]))

        picker.callback = selected
        self.add_item(picker)


class Dashboard(discord.ui.View):
    def __init__(self, settings, store):
        settings, store = pin(settings, store)
        super().__init__(timeout=900 if getattr(settings, "mode", "production") == "practice" else None)
        self.settings, self.store = settings, store
        if getattr(settings, "mode", "production") == "practice":
            # Do not reuse IDs of persistent production buttons in test messages.
            for i, child in enumerate(self.children):
                if getattr(child, "custom_id", None):
                    child.custom_id = f"snowfall:rehearsal:{settings.session_id[:12]}:{i}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if practice_expired(self.settings, self.store):
            await interaction.response.send_message("This test day has ended.", ephemeral=True)
            return False
        manager = getattr(interaction.client, "practice", None)
        current = manager.session if manager is not None else None
        if (getattr(self.settings, "mode", "production") == "production" and
                current is not None and
                interaction.channel_id == current.channel_id):
            await interaction.response.send_message(
                "This is the production dashboard. Use `/snow dashboard` for the TEST day.",
                ephemeral=True)
            return False
        if not permitted_guild(interaction.guild_id, self.settings.guild_id):
            await interaction.response.send_message("Wrong event server.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Join", emoji="❄️", style=discord.ButtonStyle.primary,
                       custom_id="snowfall:v1:join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        stage = self.store.season(self.settings.season_key).phase(datetime.now(timezone.utc))
        if stage not in ("registration", "ready", "live", "paused"):
            await interaction.response.send_message("Registration has not opened yet or has closed.", ephemeral=True)
            return
        await interaction.response.send_message("Select your city and declare your MR username:",
                                                view=CityPicker(self.settings, self.store), ephemeral=True)

    @discord.ui.button(label="My Profile", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:profile")
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.graphics.delivery import send_profile
        await interaction.response.defer(ephemeral=True)
        p = await asyncio.to_thread(self.store.get_player, self.settings.season_key, interaction.user.id)
        if p:
            from snowfall.services.combat import CombatEngine, CombatError
            try:
                engine = CombatEngine(self.store)
                r = await asyncio.to_thread(engine.snapshot, self.settings.season_key,
                                            interaction.user.id, datetime.now(timezone.utc))
                total = await asyncio.to_thread(engine.ledger_total, self.settings.season_key,
                                                interaction.user.id)
                msg = (f"**{escape_name(p.mr_username)}** — {p.city}\n"
                       f"**Identity:** {p.review_state}\n"
                       f"❄️ {r.snowballs}/12 snowballs • 🌡️ {r.warmth}/100 warmth\n"
                       f"**Day PvP:** {r.today_pvp}/300 • **Total:** {total} points\n"
                       "Use `/snow ready` to enter the arena; `/snow throw` to attack.")
                await send_profile(interaction, msg, p.mr_username, p.city, r, total,
                                   review=p.review_state)
                return
            except CombatError as exc:
                msg = str(exc)
        else:
            msg = "Not registered. Click Join."
        await interaction.followup.send(msg, ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:rules")
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(rules_text(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Throw", emoji="🎯", style=discord.ButtonStyle.success,
                       custom_id="snowfall:v1:throw")
    async def throw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.combat import send_target_menu
        await interaction.response.defer(ephemeral=True)
        await send_target_menu(interaction, self.settings, self.store)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Refresh the existing menu rather than creating another Discord message.
        await interaction.response.defer()
        now = datetime.now(timezone.utc)
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        players = await asyncio.to_thread(self.store.registrations, self.settings.season_key)
        await interaction.edit_original_response(
            embed=dashboard_embed(self.settings, season, now, len(players)), view=self)

    @discord.ui.button(label="Main Menu", emoji="🏠", style=discord.ButtonStyle.primary,
                       custom_id="snowfall:v1:main-menu", row=1)
    async def main_menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.navigation import send_main_menu
        await interaction.response.defer(ephemeral=True)
        await send_main_menu(interaction, self.settings, self.store)

    @discord.ui.button(label="My Headquarters", emoji="🏠", style=discord.ButtonStyle.success,
                       custom_id="snowfall:v1:hq", row=1)
    async def headquarters_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.headquarters import send_headquarters
        await interaction.response.defer(ephemeral=True)
        await send_headquarters(interaction, self.settings, self.store)

    @discord.ui.button(label="Inventory", emoji="🎒", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:inventory", row=1)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.economy import send_inventory
        await interaction.response.defer(ephemeral=True)
        await send_inventory(interaction, self.settings, self.store)

    @discord.ui.button(label="Daily Quests", emoji="🎄", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:quests", row=1)
    async def quests_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.economy import send_quests
        await interaction.response.defer(ephemeral=True)
        await send_quests(interaction, self.settings, self.store)

    @discord.ui.button(label="Snow Don", emoji="☃️", style=discord.ButtonStyle.primary,
                       custom_id="snowfall:v1:boss", row=2)
    async def boss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.world import send_world
        await interaction.response.defer(ephemeral=True)
        await send_world(interaction, self.settings, self.store)

    @discord.ui.button(label="City Siege", emoji="🏰", style=discord.ButtonStyle.success,
                       custom_id="snowfall:v1:siege", row=2)
    async def siege_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.world import send_world
        await interaction.response.defer(ephemeral=True)
        await send_world(interaction, self.settings, self.store)

    @discord.ui.button(label="Podium", emoji="🥇", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:podium", row=2)
    async def podium_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.graphics.delivery import send_champions
        from snowfall.services.combat import CombatEngine
        from snowfall.services.world import WorldEngine
        await interaction.response.defer(ephemeral=True)
        now = datetime.now(timezone.utc)
        season = await asyncio.to_thread(self.store.season, self.settings.season_key)
        people = await asyncio.to_thread(CombatEngine(self.store).leaderboard,
                                         self.settings.season_key, 3)
        cities = await asyncio.to_thread(WorldEngine(self.store).standings,
                                         self.settings.season_key, now)
        final = season.phase(now) in ("closed", "finalized")
        await send_champions(interaction,
            "Podium preview (staff review required before prizes). "
            "City standings are honorary only.", people, cities, final=final)

    @discord.ui.button(label="City Standings", emoji="🏆", style=discord.ButtonStyle.secondary,
                       custom_id="snowfall:v1:cities", row=2)
    async def cities_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from snowfall.ui.world import city_board_text
        from snowfall.services.world import WorldEngine
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(WorldEngine(self.store).standings,
                                       self.settings.season_key, datetime.now(timezone.utc))
        await interaction.followup.send(city_board_text(rows), ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
