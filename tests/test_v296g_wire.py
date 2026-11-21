from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from snowfall.db.store import Season
from snowfall.platform.wire_view import wire_view
from snowfall.services.wire import Headline, WireError


def test_public_wire_uses_verified_headlines_and_rejects_future_day():
    start = datetime(2026, 12, 1, tzinfo=timezone.utc)
    state = Season("qa", start, start, None, 0, None)
    game = SimpleNamespace(store=SimpleNamespace(season=lambda _: state), season="qa")
    with patch("snowfall.platform.wire_view.WireEngine") as engine:
        engine.return_value.headlines.return_value = (Headline("lead", "Verified", "Recorded", "Combat"),)
        now = start + timedelta(days=2)
        result = wire_view(game, now=now)
        assert result["day"] == 3 and result["available_days"] == [1, 2, 3]
        assert result["complete"] is False and result["verified_only"] is True
        assert result["headlines"][0]["title"] == "Verified"
        assert "stories" not in result and "pending_stories" not in result
        assert wire_view(game, day=1, now=now)["complete"] is True
        with pytest.raises(WireError):
            wire_view(game, day=4, now=now)
        engine.return_value.headlines.assert_called_with("qa", 1)


def test_prestart_and_closed_are_not_fake_news():
    start = datetime(2026, 12, 1, tzinfo=timezone.utc)
    state = Season("qa", start, start, None, 0, None)
    game = SimpleNamespace(store=SimpleNamespace(season=lambda _: state), season="qa")
    with patch("snowfall.platform.wire_view.WireEngine") as engine:
        assert wire_view(game, now=start-timedelta(hours=1))["day"] is None
        engine.assert_not_called()
        engine.return_value.headlines.return_value = ()
        result = wire_view(game, now=start+timedelta(days=7))
        assert result["phase"] == "closed" and result["day"] == 7
        assert result["complete"] is True
