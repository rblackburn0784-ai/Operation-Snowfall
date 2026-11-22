from datetime import datetime, timedelta, timezone

import pytest

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.services.mysteries import MysteryEngine
from snowfall.services.winter_fun import WinterFunEngine


def test_web_activities_share_existing_engines_without_answer_leaks(tmp_path):
    now = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
    store = Store(tmp_path / "activity.db")
    store.initialize()
    store.ensure_season("qa", now)
    store.register("qa", 101, "Tester", "Chicago", now - timedelta(days=1))
    store.transition("qa", 900, "start", now, "Test")
    game = SharedGame(store, "qa")
    first = game.activities(101, now=now)
    assert first["day"] == 1 and first["player_id"] == "101"
    assert "culprit" not in first["case"]
    assert first["case"]["conclusion"] is None
    assert all(c["text"] is None for c in first["case"]["clues"])
    assert len(first["history"]) == 1
    with pytest.raises(ValueError, match="day changed"):
        game.activity_action(101, "clue", "window", 2, "web-a", now=now)
    with pytest.raises(ValueError, match="two clues"):
        game.activity_action(101, "accuse", "bellhop", 1, "web-b", now=now)
    game.activity_action(101, "clue", "window", 1, "web-c", now=now)
    assert MysteryEngine(store).snapshot("qa", 101, now).clues[0].found
    MysteryEngine(store).investigate("qa", 101, "door", "discord-clue", now)
    assert game.activities(101, now=now)["case"]["clues"][2]["found"]
    game.activity_action(101, "encounter", "help", 1, "web-d", now=now)
    assert WinterFunEngine(store).shop("qa", 101, now).encounter
    assert game.activities(101, now=now)["case"]["secret_ready"]
    a = game.activity_action(101, "secret", "listen", 1, "web-e", now=now)
    b = game.activity_action(101, "secret", "listen", 1, "web-e", now=now)
    assert a["message"] == b["message"] and b["repeated"]
    game.activity_action(101, "accuse", "bellhop", 1, "web-f", now=now)
    assert game.activities(101, now=now)["case"]["solved"]
    with store.connect() as con:
        for table in ("score_ledger", "prize_awards"):
            assert con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
