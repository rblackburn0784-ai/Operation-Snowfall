"""Web arcade shares the Discord engine, attempts and honorary records."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.services.social_arcade import SocialArcadeEngine, GAMES


def test_arcade_web_start_replay_and_cross_platform_turns(tmp_path):
    now = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
    store = Store(tmp_path / "arcade.db")
    store.initialize()
    store.ensure_season("qa", now)
    for uid, name in ((101, "Tester"), (102, "Other")):
        store.register("qa", uid, name, "Chicago", now - timedelta(days=1))
    store.transition("qa", 900, "start", now, "Arcade QA")
    web = SharedGame(store, "qa")
    discord = SocialArcadeEngine(store)
    initial = web.arcade_lobby(101, now=now)
    assert len(initial["games"]) == 5
    assert initial["daily_cap"] == 3
    for mode in GAMES:
        run = web.arcade_start(101, mode, 1, 0, now=now)
        sid = run["session_id"]
        assert "answer" not in run["current"]
        assert web.arcade_start(101, mode, 1, 0, now=now)["session_id"] == sid
        assert discord.begin("qa", 101, mode, now).session_id == sid
        with pytest.raises(ValueError, match="another player"):
            web.arcade_session(102, sid, now=now)
        with store.connect() as con:
            puzzles = json.loads(con.execute(
                "SELECT puzzles_json FROM social_arcade_runs WHERE session_id=?", (sid,)
            ).fetchone()[0])
        for step, puzzle in enumerate(puzzles):
            if step == 0:
                discord.move("qa", 101, sid, step, puzzle["answer"], "discord-"+sid, now)
                assert web.arcade_session(101, sid, now=now)["step"] == 1
            else:
                iid = f"web-{sid}-{step}"
                result = web.arcade_move(101, sid, step, puzzle["answer"], iid, now=now)
                assert result["right"]
                assert web.arcade_move(101, sid, step, puzzle["answer"], iid, now=now)["repeated"]
        assert web.arcade_start(101, mode, 1, 0, now=now)["finished"]
        assert discord.lobby("qa", 101, now).record(mode).attempts_today == 1
        assert discord.lobby("qa", 101, now).record(mode).personal_best == 100
        assert web.arcade_board(101, mode, now=now)["players"][0]["best"] == 100
    assert len(web.arcade_lobby(101, now=now)["stamps"]) == 11
    with pytest.raises(ValueError, match="day changed"):
        web.arcade_start(101, "gallery", 2, 0, now=now)
    with store.connect() as con:
        for table in ("score_ledger", "prize_awards", "item_events"):
            assert con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_arcade_api_requires_auth_and_csrf():
    from unittest.mock import Mock
    from fastapi.testclient import TestClient
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings
    ids, game = FakeIdentity(), Mock()
    game.arcade_lobby.return_value = {"player_id": "101"}
    game.arcade_start.return_value = {"session_id": "a"*32}
    game.arcade_move.return_value = {"feedback": "Recorded"}
    with TestClient(create_app(fake_settings(), identity=ids, game=game),
                    base_url="https://snowfall.example") as client:
        assert client.get("/v1/game/arcade").status_code == 401
        token, csrf = ids.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.get("/v1/game/arcade").status_code == 200
        start = {"mode": "gallery", "day": 1, "attempts_today": 0}
        assert client.post("/v1/game/arcade/start", json=start).status_code == 403
        headers = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/game/arcade/start", json=start, headers=headers).status_code == 200
        move = {"session_id": "a"*32, "step": 0, "choice": "Bell"}
        assert client.post("/v1/game/arcade/move", json=move, headers=headers).status_code == 400
        headers["Idempotency-Key"] = "arcade-move-123"
        assert client.post("/v1/game/arcade/move", json=move, headers=headers).status_code == 200
        assert game.arcade_move.call_args.args[:4] == (101, "a"*32, 0, "Bell")
