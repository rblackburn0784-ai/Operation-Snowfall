from datetime import datetime, timedelta, timezone
import pytest
from snowfall.core.clock import phase, registration_opens, event_ends, game_day

T = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)

def test_registration_opens_exactly_one_week_prior():
    assert registration_opens(T) == T - timedelta(days=7)
    assert phase(T, T - timedelta(days=7, seconds=1)) == "not_open"
    assert phase(T, T - timedelta(days=7)) == "registration"

def test_seven_full_days():
    assert phase(T, T) == "live"
    assert game_day(T, T) == 1
    assert game_day(T, T + timedelta(days=6, hours=23)) == 7
    assert phase(T, T + timedelta(days=7)) == "closed"
    assert game_day(T, T + timedelta(days=7)) is None
    assert event_ends(T) - T == timedelta(hours=168)

def test_reject_naive_dates():
    with pytest.raises(ValueError):
        phase(T, datetime(2026, 12, 13))
