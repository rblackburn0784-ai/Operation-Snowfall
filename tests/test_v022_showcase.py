"""v0.2.2: illustrated, owned-only, score-neutral seasonal collections."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.graphics import cards
from snowfall.services.achievements import AchievementEngine
from snowfall.services.combat import CombatEngine
from snowfall.services.showcase import ShowcaseError, showcase
from snowfall.services.winter_fun import COSMETICS, RARITY_ORDER, WinterFunEngine

KEY = "winter-showcase"
NOW = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "showcase.sqlite3")
    store.initialize()
    store.ensure_season(KEY, NOW)
    store.register(KEY, 101, "DudeNoir", "Chicago", NOW - timedelta(days=1))
    store.register(KEY, 202, "RivalNoir", "New York", NOW - timedelta(days=1))
    store.transition(KEY, 900, "start", NOW, "Begin")
    with store.connect() as con:
        con.execute("UPDATE player_resources SET snowflakes=90 "
                    "WHERE season_key=? AND discord_user_id=101", (KEY,))
    return store


def _image(blob):
    with Image.open(BytesIO(blob)) as image:
        assert image.size == (960, 540)
        assert image.mode == "RGB"
        return image.copy()


def _card(info):
    return cards.profile_card(info.player.mr_username, info.player.city, info.resources,
                              info.points, showcase=info)


def test_purchased_frames_banners_trails_gear_and_portraits_are_visible(game):
    engine = WinterFunEngine(game)
    original = showcase(game, KEY, 101, NOW)
    default = _image(_card(original))
    keys = ["ice_frame", "snow_trail", "goggles", "midnight_banner", "noir_detective"]
    for key in keys:
        engine.buy(KEY, 101, key, f"purchase-{key}", NOW)
        engine.equip(KEY, 101, key, NOW)
    changed = showcase(game, KEY, 101, NOW)
    assert set(changed.equipped.values()) == set(keys)
    assert changed.owned_count == 5
    assert changed.best_rarity == "Rare"
    assert changed.badge_count == 3  # New collector milestones, including full outfit.
    assert {x.key for x in changed.badges} == {"first_style", "collector", "full_outfit"}
    after = _image(_card(changed))
    assert default.tobytes() != after.tobytes()
    assert after.getpixel((750, 185)) != default.getpixel((750, 185))
    assert len(_card(changed)) < 2_000_000
    assert CombatEngine(game).ledger_total(KEY, 101) == 0
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0


def test_rarity_fixed_nonrandom_and_legendary_card(game):
    assert set(RARITY_ORDER) == {"Common", "Rare", "Epic", "Legendary"}
    assert {c.rarity for c in COSMETICS.values()} == set(RARITY_ORDER)
    assert COSMETICS["frost_spectre"].rarity == "Legendary"
    engine = WinterFunEngine(game)
    engine.buy(KEY, 101, "frost_spectre", "legendary-portrait", NOW)
    engine.equip(KEY, 101, "frost_spectre", NOW)
    model = showcase(game, KEY, 101, NOW)
    assert model.best_rarity == "Legendary"
    assert model.equipped["portrait"] == "frost_spectre"
    assert _card(model).startswith(b"\x89PNG\r\n\x1a\n")


def test_display_never_equips_unowned_item_or_cross_season(game):
    with game.connect() as con:
        con.execute("INSERT INTO cosmetic_equipped"
                    "(season_key,discord_user_id,category,cosmetic_key) "
                    "VALUES(?,?,?,?)", (KEY, 101, "frame", "gold_frame"))
    model = showcase(game, KEY, 101, NOW)
    assert "frame" not in model.equipped
    assert model.owned_count == 0
    game.ensure_season("second", NOW)
    game.register("second", 101, "DifferentDude", "Detroit", NOW)
    game.transition("second", 900, "start", NOW, "Another season")
    other = showcase(game, "second", 101, NOW)
    assert other.equipped == {} and other.owned_count == 0
    assert other.badge_count == 0


def test_public_cards_reject_review_flags_while_private_data_stays_scoped(game):
    with game.connect() as con:
        con.execute("UPDATE players SET review_state='flagged' "
                    "WHERE season_key=? AND discord_user_id=101", (KEY,))
    with pytest.raises(ShowcaseError, match="identity review"):
        showcase(game, KEY, 101, NOW, public=True)
    with pytest.raises(ShowcaseError):
        showcase(game, KEY, 101, NOW)  # The wardrobe authority also blocks review flags.
    with pytest.raises(ShowcaseError, match="Register"):
        showcase(game, KEY, 1000, NOW, public=True)


def test_cosmetic_milestone_title_only_after_owned_five_slots(game):
    engine = WinterFunEngine(game)
    for key in ("ice_frame", "snow_trail", "goggles", "midnight_banner", "noir_detective"):
        engine.buy(KEY, 101, key, "collect-" + key, NOW)
    cab = AchievementEngine(game).cabinet(KEY, 101)
    assert cab.records.cosmetics_unlocked == 5
    assert cab.records.style_slots == 0
    assert cab.unlocked_count == 2
    for key in ("ice_frame", "snow_trail", "goggles", "midnight_banner", "noir_detective"):
        engine.equip(KEY, 101, key, NOW)
    cab = AchievementEngine(game).cabinet(KEY, 101)
    assert cab.records.style_slots == 5
    assert cab.unlocked_count == 3
    assert AchievementEngine(game).equip(KEY, 101, "full_outfit") == "Frost Fashion Icon"
    info = showcase(game, KEY, 101, NOW)
    assert info.featured_badges[0].key == "full_outfit"
    assert info.title == "Frost Fashion Icon"
    assert CombatEngine(game).ledger_total(KEY, 101) == 0


def test_all_six_city_cards_render_with_portrait_defaults(tmp_path):
    cities = ("Chicago", "New York", "Detroit", "Philadelphia", "Las Vegas", "Los Angeles")
    for i, city in enumerate(cities, 1):
        store = Store(tmp_path / f"city-{i}.sqlite3")
        store.initialize()
        store.ensure_season(KEY, NOW)
        store.register(KEY, i, f"Mobster{i}", city, NOW - timedelta(days=1))
        store.transition(KEY, 900, "start", NOW, "Start")
        _image(_card(showcase(store, KEY, i, NOW)))


def test_discord_showcase_views_and_private_test_rehearsal(game, monkeypatch):
    pytest.importorskip("discord")
    from snowfall.commands.winter_fun import SnowFunGroup
    from snowfall.ui.showcase import ShowcaseView, show_profile, publish_card
    from snowfall.ui.winter_fun import WinterActivitiesView
    from snowfall.ui.trophies import TrophyCabinet

    config = SimpleNamespace(guild_id=7, season_key=KEY, mode="production",
                             admin_user_ids=frozenset())
    monkeypatch.setattr("snowfall.ui.showcase._now", lambda: NOW)
    groups = {c.name for c in SnowFunGroup(config, game).commands}
    assert "showcase" in groups
    for view in (ShowcaseView(config, game, 101), WinterActivitiesView(config, game, 101),
                 TrophyCabinet(config, game, 101)):
        assert len(view.children) <= 25
        assert all(x.row is None or x.row <= 4 for x in view.children)
    assert "My Card" in {x.label for x in WinterActivitiesView(config, game, 101).children}
    assert "My Card" in {x.label for x in TrophyCabinet(config, game, 101).children}

    class Response:
        def __init__(self):
            self.defers = []
            self.messages = []
        async def defer(self, **kw):
            self.defers.append(kw)
        async def send_message(self, *args, **kw):
            self.messages.append((args, kw))

    class Interaction:
        def __init__(self):
            self.user = SimpleNamespace(id=101)
            self.guild_id = 7
            self.channel_id = 1234
            self.client = SimpleNamespace(practice=None)
            self.response = Response()
            self.edits = []
            self.followup = SimpleNamespace(send=self.followup_send)
            self.posts = []
        async def edit_original_response(self, **kw):
            self.edits.append(kw)
        async def followup_send(self, **kw):
            self.posts.append(kw)

    async def exercise():
        event = Interaction()
        await show_profile(event, config, game, 101)
        assert len(event.edits) == 1
        assert event.edits[0]["view"].owner_id == 101
        assert event.edits[0]["embed"].image.url == "attachment://snowfall.png"
        test = Interaction()
        testconfig = SimpleNamespace(guild_id=7, season_key=KEY, mode="practice",
                                     admin_user_ids=frozenset())
        await publish_card(test, testconfig, game)
        assert test.response.messages and not test.posts
        assert "test" in test.response.messages[0][0][0].lower()

        public = Interaction()
        await publish_card(public, config, game)
        assert public.response.defers
        assert len(public.posts) == 1
        assert public.posts[0]["file"].filename == "snowfall-showcase.png"
        assert public.posts[0]["allowed_mentions"].everyone is False

    asyncio.run(exercise())
