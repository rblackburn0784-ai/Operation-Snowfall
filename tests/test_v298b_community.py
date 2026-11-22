from datetime import datetime, timedelta, timezone

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.platform.community_view import community_view
from snowfall.services.social_arcade import SocialArcadeEngine


def test_community_is_aggregate_read_only_and_season_scoped(tmp_path):
    now = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)
    db = Store(tmp_path / "community.db")
    db.initialize()
    for season in ("qa", "other"):
        db.ensure_season(season, now)
        db.register(season, 101, "PrivatePlayer", "Chicago", now-timedelta(days=1))
        db.transition(season, 900, "start", now, "QA")
    game = SharedGame(db, "qa")
    out = community_view(game, now)
    assert len(out["cities"]) == 6
    assert out["verified_only"] and not out["chat_relay"]
    assert out["day"] == 1
    assert out["updates"] == []
    assert "PrivatePlayer" not in str(out)
    assert out["totals"]["throws"] == 0
    assert all(c["objective"] is not None for c in out["cities"])
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0

    engine = SocialArcadeEngine(db)
    for season in ("qa", "other"):
        run = engine.begin(season, 101, "safe", now)
        while not run.finished:
            run = engine.move(season, 101, run.session_id, run.step,
                              run.current.choices[0], f"{season}-{run.step}", now).session
    out = community_view(game, now)
    assert out["totals"]["arcade"] == 1
    assert out["updates"] == [{"city": "Chicago", "kind": "arcade", "count": 1,
                               "unit": "arcade runs completed"}]
    assert community_view(game, now-timedelta(days=2))["day"] is None
