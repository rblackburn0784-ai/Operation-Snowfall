import pytest
from snowfall.core.scoring import city_day_score

def test_city_daily_example():
    contributors = [300, 280, 260, 220, 200] + [1] * 7
    assert city_day_score(contributors, siege_cleared=True) == 305

def test_three_members_qualify_with_zero_padding():
    assert city_day_score([300, 300, 300], False) == 180

def test_below_three_active_no_city_points():
    assert city_day_score([300, 300], True) == 0

def test_population_bonus_caps_and_contribution_caps():
    assert city_day_score([500] * 40, True) == 365

def test_no_negative_contributions():
    with pytest.raises(ValueError):
        city_day_score([-1, 10, 20], False)
