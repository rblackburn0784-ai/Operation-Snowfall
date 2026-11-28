"""Adventure state, puzzles, isolation, reset and API validation."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from snowfall.db.store import Store
from snowfall.platform.adventure import adventure_action, adventure_view
from snowfall.platform.qa_lifecycle import apply_qa_lifecycle, CONFIRMATIONS, QA_SEASON

NOW = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)


@pytest.fixture
def game(tmp_path):
    store = Store(tmp_path / "qa.sqlite3")
    store.initialize()
    store.ensure_season(QA_SEASON, NOW)
    for player, name in ((101, "Detective"), (102, "Courier")):
        store.register(QA_SEASON, player, name, "Chicago", NOW)
    store.transition(QA_SEASON, 900, "start", NOW, "QA test")
    return SimpleNamespace(store=store, season=QA_SEASON)


def view(game, user=101, now=NOW):
    return adventure_view(game.store, game.season, user, now)


def move(game, a, action, target, user=101, now=NOW, request=None):
    return adventure_action(game.store, game.season, user, now, day=a["day"],
                            epoch=a["epoch"], revision=a["revision"], action=action,
                            target=target, request=request or "test-" + str(a["revision"]))


def test_complete_adventure_and_persistence(game):
    a = view(game)
    assert a["scene"]["key"] == "office" and not a["evidence"]
    assert "Square-heeled" not in str(a)
    with pytest.raises(ValueError, match="not available"):
        move(game, a, "inspect", "parcel")
    with pytest.raises(ValueError, match="not available"):
        move(game, a, "use", "brass_key")
    a = move(game, a, "inspect", "drawer")
    assert len(a["inventory"]) == 1 and view(game) == a
    a = move(game, a, "inspect", "window")
    a = move(game, a, "inspect", "courier")
    assert not any(c["key"] == "report" for c in a["dialogue"]["choices"])
    a = move(game, a, "choose", "receipt")
    a = move(game, a, "choose", "leave")
    a = move(game, a, "inspect", "door")
    a = move(game, a, "use", "brass_key")
    a = move(game, a, "inspect", "door")
    assert a["scene"]["key"] == "alley"
    a = move(game, a, "inspect", "parcel")
    assert len(a["evidence"]) == 3
    a = move(game, a, "inspect", "return")
    a = move(game, a, "inspect", "courier")
    a = move(game, a, "choose", "report")
    assert a["complete"] and a["souvenir"] == "Winter Dispatch Detective"
    assert view(game)["complete"]
    a = move(game, a, "travel", "city")
    a = move(game, a, "travel", "market")
    a = move(game, a, "inspect", "stall")
    assert a["complete"] and len(a["city"]["discoveries"]) == 1
    assert view(game, 102)["inventory"] == []
    with game.store.connect() as con:
        for table in ("score_ledger", "prize_awards"):
            assert con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_replay_and_stale_tab_and_player(game):
    a = view(game)
    b = move(game, a, "inspect", "drawer")
    retry = move(game, a, "inspect", "drawer")
    assert retry["repeated"] and retry["revision"] == b["revision"]
    with pytest.raises(ValueError, match="already used"):
        move(game, a, "inspect", "window")
    with pytest.raises(ValueError, match="another tab"):
        move(game, a, "inspect", "window", request="different")
    with pytest.raises(ValueError, match="reset"):
        move(game, a, "inspect", "drawer", user=102)
    with pytest.raises(ValueError, match="day changed"):
        move(game, b, "inspect", "window", now=NOW + timedelta(days=1))
    assert view(game, now=NOW + timedelta(days=1))["inventory"] == b["inventory"]


def test_qa_reset_invalidates_old_epoch(game):
    a = view(game)
    move(game, a, "inspect", "drawer")
    apply_qa_lifecycle(game, actor_id=900, action="reset",
                       confirmation=CONFIRMATIONS["reset"], reason="QA adventure reset",
                       request_id="adventure-reset-001", now=NOW)
    b = view(game)
    assert b["epoch"] != a["epoch"] and not b["inventory"]
    with pytest.raises(ValueError, match="reset"):
        move(game, a, "inspect", "drawer")


def test_api_identity_csrf_and_validation():
    from fastapi.testclient import TestClient
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings
    from unittest.mock import Mock

    ids = FakeIdentity()
    game = Mock()
    game.adventure_action.return_value = {"message": "Found"}
    app = create_app(fake_settings(), identity=ids, game=game)
    path = "/v1/game/adventure/action"
    body = {"day": 1, "epoch": "a" * 32, "revision": 0, "action": "inspect", "target": "drawer"}
    with TestClient(app, base_url="https://snowfall.example") as client:
        assert client.post(path, json=body).status_code == 401
        token, csrf = ids.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.post(path, json=body).status_code == 403
        headers = {"X-Snowfall-CSRF": csrf, "Idempotency-Key": "adventure-action-123"}
        assert client.post(path, json={**body, "action": "complete"}, headers=headers).status_code == 422
        assert client.post(path, json=body, headers=headers).status_code == 200
        assert game.adventure_action.call_args.args == (101,)
        assert game.adventure_action.call_args.kwargs["target"] == "drawer"


def test_city_daily_unlocks_and_server_rejects_locked_travel(game):
    a = view(game)
    a = move(game, a, "travel", "city")
    assert a["scene"]["key"] == "city"
    locations = {x["key"]: x for x in a["city"]["locations"]}
    assert {k for k, v in locations.items() if v["status"] == "open"} == {"office", "hotel", "market"}
    assert "archive" not in locations
    assert locations["alley"]["reason"] == "Find a way inside"
    for target in ("archive", "alley", "station", "not_a_location"):
        with pytest.raises(ValueError, match="not available"):
            move(game, a, "travel", target)
    for day, key in ((2, "station"), (3, "ice_house"), (4, "post_office"),
                     (5, "press_room"), (6, "telegraph"), (7, "square")):
        date = NOW + timedelta(days=day - 1)
        a = view(game, now=date)
        assert next(x for x in a["city"]["locations"] if x["key"] == key)["status"] == "open"
        a = move(game, a, "travel", key, now=date)
        assert a["scene"]["key"] == key
        a = move(game, a, "travel", "city", now=date)
    assert a["city"]["visited"] == 7


def test_secret_discovery_dialogue_and_unique_souvenirs(game):
    a = move(game, view(game), "travel", "city")
    a = move(game, a, "travel", "market")
    a = move(game, a, "inspect", "stall")
    a = move(game, a, "inspect", "stall")
    assert len(a["city"]["discoveries"]) == 1
    assert view(game)["city"]["discoveries"] == a["city"]["discoveries"]
    a = move(game, a, "travel", "city")
    a = move(game, a, "travel", "hotel")
    assert "hatch" not in {h["key"] for h in a["scene"]["hotspots"]}
    with pytest.raises(ValueError, match="not available"):
        move(game, a, "inspect", "hatch")
    a = move(game, a, "inspect", "directory")
    a = move(game, a, "inspect", "concierge")
    a = move(game, a, "choose", "card")
    a = move(game, a, "choose", "archive")
    a = move(game, a, "choose", "leave")
    a = move(game, a, "inspect", "hatch")
    assert any(x["key"] == "archive" for x in a["city"]["locations"])
    a = move(game, a, "travel", "city")
    a = move(game, a, "travel", "archive")
    a = move(game, a, "inspect", "cabinet")
    assert len(a["city"]["discoveries"]) == 3
    other = view(game, 102)
    assert other["city"]["discoveries"] == []
    assert not any(x["key"] == "archive" for x in other["city"]["locations"])
    apply_qa_lifecycle(game, actor_id=900, action="reset",
                       confirmation=CONFIRMATIONS["reset"], reason="QA city reset",
                       request_id="city-reset-001", now=NOW)
    assert not view(game)["city"]["discoveries"]
    assert not any(x["key"] == "archive" for x in view(game)["city"]["locations"])


def test_city_rewind_and_previous_save_upgrade(game):
    import json
    a = move(game, view(game), "inspect", "drawer")
    # Simulate the exact earlier persisted save format.
    with game.store.connect() as con:
        state = json.loads(con.execute("SELECT state_json FROM web_adventure_progress "
                                       "WHERE player_id=101").fetchone()[0])
        state.pop("visited")
        state.pop("discoveries")
        con.execute("UPDATE web_adventure_progress SET state_json=? WHERE player_id=101",
                    (json.dumps(state),))
    restored = view(game)
    assert restored["epoch"] == a["epoch"] and restored["revision"] == a["revision"]
    assert restored["inventory"] == a["inventory"]
    later = NOW + timedelta(days=1)
    a = move(game, view(game, now=later), "travel", "city", now=later)
    a = move(game, a, "travel", "station", now=later)
    assert view(game, now=NOW)["scene"]["key"] == "city"
    a = view(game)
    with pytest.raises(ValueError, match="not available"):
        move(game, a, "inspect", "ticket")
    with pytest.raises(ValueError, match="not available"):
        move(game, a, "travel", "station")
    a = move(game, a, "travel", "office")
    assert a["inventory"][0]["key"] == "brass_key"
