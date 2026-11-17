"""v0.2.6 Christmas Mysteries: seven-case narrative and replay/award isolation."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
import sqlite3
from types import SimpleNamespace

import pytest
from PIL import Image

from snowfall.db.store import Store
from snowfall.services.mysteries import (
    MysteryEngine, MysteryError, CASES, SECRET_CHOICES, SECRET_VARIANTS, MAX_GUESSES,
)
from snowfall.services.winter_fun import WinterFunEngine
from snowfall.graphics.mystery_cards import case_file_card, casebook_card, secret_postcard_card

KEY = "mystery-event"
START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "mystery.db")
    store.initialize()
    store.ensure_season(KEY, START)
    for uid, name, city in [(101, "TheDude", "Chicago"),
                            (102, "Jago", "Chicago"),
                            (201, "Santa Fox", "New York")]:
        store.register(KEY, uid, name, city, START - timedelta(days=1))
    store.transition(KEY, 900, "start", START, "Launch mystery test")
    return store


def counts(store):
    with store.connect() as con:
        return tuple(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("score_ledger", "combat_events", "pve_events",
                                   "prize_awards", "item_events", "arcade_events",
                                   "cosmetic_purchases", "cosmetic_unlocks", "player_resources"))


def png(payload):
    assert payload.startswith(b"\x89PNG") and len(payload) < 2_000_000
    with Image.open(BytesIO(payload)) as image:
        assert image.size == (960, 540)


def clue(engine, user, lead, index=1, now=START):
    return engine.investigate(KEY, user, lead, f"lead-{user}-{index}", now)


def test_seven_distinct_solvable_cases_and_no_answer_in_clue_names():
    assert len(CASES) == 7
    assert len({c.title for c in CASES}) == 7
    assert len({c.secret_title for c in CASES}) == 7
    for day, c in enumerate(CASES, 1):
        assert c.day == day
        assert len(c.leads) == len(c.suspects) == 3
        assert len({x[0] for x in c.leads}) == 3
        assert len({x[0] for x in c.suspects}) == 3
        assert c.culprit in dict(c.suspects)
        assert c.conclusion and c.secret_scene
    assert MAX_GUESSES == 2 and len(SECRET_CHOICES) == 3
    assert len(SECRET_VARIANTS) == 3


def test_clue_discovery_and_guess_replays_never_duplicate_or_spend(game):
    engine = MysteryEngine(game)
    first = engine.snapshot(KEY, 101, START)
    assert first.day == 1 and first.phase == "live"
    assert first.guesses == 0 and not first.secret_ready
    assert len(first.clues) == 3 and not any(c.found for c in first.clues)
    baseline = counts(game)
    png(case_file_card(first))
    png(casebook_card(first))
    with pytest.raises(MysteryError, match="at least two clues"):
        engine.accuse(KEY, 101, "bellhop", "early", START)
    with pytest.raises(MysteryError, match="not in today's case"):
        engine.investigate(KEY, 101, "invalid", "bad-lead", START)
    found, repeated = clue(engine, 101, "window", 1)
    assert found.found and not repeated
    again, repeat = engine.investigate(KEY, 101, "window", "lead-101-1", START)
    assert again == found and repeat
    _, new_interaction_repeat = engine.investigate(KEY, 101, "window", "another", START)
    assert new_interaction_repeat
    with pytest.raises(MysteryError, match="belongs to another investigation"):
        engine.investigate(KEY, 101, "counter", "lead-101-1", START)
    clue(engine, 101, "door", 2)
    correct = engine.accuse(KEY, 101, "bellhop", "guess-one", START)
    assert correct.correct and correct.solved and correct.attempts_used == 1
    assert "CASE CLOSED" in correct.message
    same = engine.accuse(KEY, 101, "bellhop", "guess-one", START)
    assert same.repeated and same.correct
    with pytest.raises(MysteryError, match="already"):
        engine.accuse(KEY, 101, "courier", "guess-after-solved", START)
    snap = engine.snapshot(KEY, 101, START)
    assert snap.solved and snap.solved_count == 1
    assert sum(c.found for c in snap.clues) == 2
    assert snap.history[0].attempts == 1
    assert counts(game) == baseline
    png(case_file_card(snap))
    png(casebook_card(snap))
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM mystery_clues").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM mystery_guesses").fetchone()[0] == 1


def test_wrong_guess_limit_no_brute_force_and_season_scope(game):
    engine = MysteryEngine(game)
    engine.investigate(KEY, 102, "window", "2-w", START)
    engine.investigate(KEY, 102, "counter", "2-c", START)
    bad = engine.accuse(KEY, 102, "courier", "g1", START)
    assert not bad.correct and bad.attempts_used == 1
    retry = engine.accuse(KEY, 102, "courier", "g2", START)
    assert retry.repeated and retry.attempts_used == 1
    second = engine.accuse(KEY, 102, "musician", "g3", START)
    assert second.attempts_used == 2 and not second.correct
    locked = engine.snapshot(KEY, 102, START)
    assert locked.locked and not locked.solved
    with pytest.raises(MysteryError, match="No accusations"):
        engine.accuse(KEY, 102, "bellhop", "g4", START)
    with pytest.raises(MysteryError, match="belongs to another accusation"):
        engine.accuse(KEY, 102, "bellhop", "g1", START)
    assert engine.snapshot(KEY, 101, START).guesses == 0
    assert engine.snapshot(KEY, 201, START).guesses == 0


def test_secret_gate_ordinary_encounter_accessibility_and_one_memento(game):
    engine = MysteryEngine(game)
    clue(engine, 101, "window", 1)
    clue(engine, 101, "door", 2)
    with pytest.raises(MysteryError, match="Find two clues"):
        engine.secret(KEY, 101, "listen", "secret-early", START)
    assert not engine.snapshot(KEY, 101, START).secret_ready
    ordinary = WinterFunEngine(game).encounter(KEY, 101, "ordinary", START, "help")
    assert ordinary.souvenir
    ready = engine.snapshot(KEY, 101, START)
    assert ready.secret_ready and ready.activity
    before = counts(game)
    won = engine.secret(KEY, 101, "listen", "secret-ok", START)
    assert "Midnight Note" in won.souvenir
    assert won.title == CASES[0].secret_title
    assert not won.repeated and won.scene
    repeated = engine.secret(KEY, 101, "listen", "secret-ok", START)
    assert repeated.repeated and repeated.souvenir == won.souvenir
    repeated_different_id = engine.secret(KEY, 101, "follow", "new-id", START)
    assert repeated_different_id.repeated and repeated_different_id.souvenir == won.souvenir
    with pytest.raises(MysteryError, match="belongs to another encounter"):
        engine.secret(KEY, 101, "assist", "secret-ok", START)
    snap = engine.snapshot(KEY, 101, START)
    assert snap.secret and snap.souvenirs_count == 1
    assert not snap.secret_ready
    png(secret_postcard_card(snap))
    assert counts(game) == before
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM mystery_secrets").fetchone()[0] == 1


def test_daily_points_also_unlock_secrets_without_ordinary_encounter(game):
    engine = MysteryEngine(game)
    clue(engine, 201, "window", 1)
    clue(engine, 201, "counter", 2)
    with game.connect() as con:
        con.execute("INSERT INTO score_ledger(season_key,day,player_id,city,category,"
                    "points,source_key,created_at_utc) VALUES (?,?,?,'New York',"
                    "'quest',20,'test:clue-activity',?)",
                    (KEY, 1, 201, START.isoformat()))
    ready = engine.snapshot(KEY, 201, START)
    assert ready.secret_ready and ready.activity
    first = engine.secret(KEY, 201, "assist", "credited-secret", START)
    assert "Frosted Lantern" in first.souvenir
    assert engine._variant(KEY, 201, 1) == engine._variant(KEY, 201, 1)
    assert counts(game)[0] == 1  # Only the fixture's legitimate activity credit.


def test_pause_day_rollover_and_closed_casebook(game):
    engine = MysteryEngine(game)
    clue(engine, 101, "window", 1)
    game.transition(KEY, 900, "pause", START + timedelta(hours=1), "Stop the clock")
    snap = engine.snapshot(KEY, 101, START + timedelta(days=5))
    assert snap.phase == "paused" and snap.day == 1
    assert snap.clues[0].found
    with pytest.raises(MysteryError, match="LIVE|live"):
        engine.investigate(KEY, 101, "door", "paused-investigate",
                           START + timedelta(days=5))
    game.transition(KEY, 900, "resume", START + timedelta(days=5), "Back")
    day2 = START + timedelta(days=6, minutes=1)
    d2 = engine.snapshot(KEY, 101, day2)
    assert d2.day == 2 and not any(x.found for x in d2.clues)
    assert d2.solved_count == 0
    assert engine.investigate(KEY, 101, "engine", "day2-clue",
                              day2)[0].found
    with pytest.raises(MysteryError, match="not in today's case"):
        engine.investigate(KEY, 101, "window", "old-day-lead", day2)
    day7end = START + timedelta(days=12, hours=1)
    finished = engine.snapshot(KEY, 101, day7end)
    assert finished.phase == "closed" and finished.day is None
    assert finished.history[0].clues == 1 and finished.history[1].clues == 1
    png(casebook_card(finished))
    with pytest.raises(MysteryError, match="LIVE|live"):
        engine.secret(KEY, 101, "listen", "closed-secret", day7end)


def test_final_case_and_immutable_schema_restarts(game):
    engine = MysteryEngine(game)
    final_time = START + timedelta(days=6, minutes=2)
    case = CASES[6]
    assert engine.snapshot(KEY, 101, final_time).case == case
    engine.investigate(KEY, 101, "keyring", "last-key", final_time)
    engine.investigate(KEY, 101, "footprints", "last-footprints", final_time)
    solved = engine.accuse(KEY, 101, "caretaker", "last-answer", final_time)
    assert solved.correct
    reopened = Store(game.path)
    reopened.initialize()
    assert reopened.schema_version() == 9
    assert MysteryEngine(reopened).snapshot(KEY, 101, final_time).solved
    for table in ("mystery_clues", "mystery_guesses"):
        with reopened.connect() as con:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                con.execute(f"DELETE FROM {table}")
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                con.execute(f"UPDATE {table} SET day=1")
    with reopened.connect() as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_parallel_double_clicks_and_user_identity_boundary(game):
    engine = MysteryEngine(game)
    def inspect(i):
        return engine.investigate(KEY, 101, "door", f"thread-{i}", START)
    with ThreadPoolExecutor(max_workers=2) as pool:
        output = list(pool.map(inspect, (1, 2)))
    assert sorted(repeated for _, repeated in output) == [False, True]
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM mystery_clues").fetchone()[0] == 1
    with pytest.raises(MysteryError, match="another investigation"):
        engine.investigate(KEY, 201, "door", "thread-1", START)
    with pytest.raises(MysteryError, match="Register"):
        engine.snapshot(KEY, 9999, START)
    game.review(KEY, 900, 101, "flagged", "Identity review", START)
    with pytest.raises(MysteryError, match="identity review"):
        engine.investigate(KEY, 101, "window", "flagged", START)


def test_upgrading_v8_sqlite_is_safe_and_idempotent(game):
    with game.connect() as con:
        for table in ("mystery_clues", "mystery_guesses", "mystery_secrets"):
            con.execute(f"DROP TABLE {table}")
        con.execute("PRAGMA user_version=8")
        before = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    game.initialize()
    game.initialize()
    assert game.schema_version() == 9
    with game.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0] == before
        assert all(con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (t,)).fetchone() for t in ("mystery_clues", "mystery_guesses", "mystery_secrets"))
    assert MysteryEngine(game).snapshot(KEY, 101, START).day == 1


def test_discord_menus_and_graphics_are_private_and_under_limits(game, monkeypatch):
    discord = pytest.importorskip("discord")
    from snowfall.commands.winter_fun import SnowFunGroup
    from snowfall.ui.mysteries import (
        MysteryView, MysteryChoice, show_mystery, case_text,
    )
    from snowfall.ui.winter_fun import WinterActivitiesView
    from snowfall.ui.navigation import GameMenu

    settings = SimpleNamespace(guild_id=1234, season_key=KEY, mode="production",
                               admin_user_ids=frozenset())
    monkeypatch.setattr("snowfall.ui.mysteries._now", lambda: START)
    snap = MysteryEngine(game).snapshot(KEY, 101, START)
    assert "mystery" in {x.name for x in SnowFunGroup(settings, game).commands}
    assert "Mystery Casebook" in {x.label for x in GameMenu(settings, game, 101).children}
    assert "Mystery Casebook" in {x.label for x in WinterActivitiesView(settings, game, 101).children}
    assert "Vanishing Christmas Ledger" in case_text(snap)
    for view in (MysteryView(settings, game, 101),
                 MysteryChoice(settings, game, 101, "clue", snap),
                 MysteryChoice(settings, game, 101, "suspect", snap),
                 MysteryChoice(settings, game, 101, "secret", snap)):
        assert isinstance(view, discord.ui.View)
        assert len(view.children) <= 25
        assert all(x.row is None or 0 <= x.row <= 4 for x in view.children)

    class FakeInteraction:
        def __init__(self):
            self.user = SimpleNamespace(id=101)
            self.guild_id = 1234
            self.client = SimpleNamespace(practice=None)
            self.channel_id = 99
            self.response = SimpleNamespace(defer=self.defer)
            self.edits = []
        async def defer(self, **kwargs):
            pass
        async def edit_original_response(self, **kwargs):
            self.edits.append(kwargs)

    async def scenario():
        target = FakeInteraction()
        await show_mystery(target, settings, game, 101)
        assert len(target.edits) == 1
        assert target.edits[0]["attachments"]
        book = FakeInteraction()
        await show_mystery(book, settings, game, 101, page="book")
        assert "PERSONAL CASEBOOK" in book.edits[0]["content"]
    asyncio.run(scenario())
