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
