"""No real users: mass participation/snapshot/cap regression for Milestone F."""
from datetime import datetime, timedelta, timezone

from snowfall.db.store import CITIES, Store
from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine
from snowfall.ops import reconcile

START = datetime(2026, 12, 20, tzinfo=timezone.utc)
KEY = "load-only"


def test_300_players_seven_days_and_restart(tmp_path):
    store = Store(tmp_path / "load.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    # 300 identities are deliberately synthetic, 50 per city.
    for i in range(300):
        store.register(KEY, i + 1, f"Load{i + 1}", CITIES[i // 50],
                       START - timedelta(hours=1))
    store.transition(KEY, 9000, "start", START, "Synthetic load test")
    with store.connect() as con:
        events = []
        for day in range(1, 8):
            for i in range(300):
                events.append((KEY, day, i+1, CITIES[i//50], "quests", 20,
                               f"load:{day}:{i}", (START+timedelta(days=day-1)).isoformat()))
        con.executemany("""INSERT INTO score_ledger
             (season_key,day,player_id,city,category,points,source_key,created_at_utc)
             VALUES(?,?,?,?,?,?,?,?)""", events)
    # Simulate process death before day rollover; restart from persistent state.
    reopened = Store(store.path)
    reopened.initialize()
    world = WorldEngine(reopened)
    world.tick(KEY, START+timedelta(days=7))
    with reopened.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM city_day_snapshots").fetchone()[0] == 42
    standings = world.standings(KEY, START+timedelta(days=7))
    assert len(standings) == 6
    assert all(r.score_x100 > 0 for r in standings)
    assert reconcile(reopened, KEY)["ok"]
    leaders = CombatEngine(reopened).leaderboard(KEY, 10)
    assert len(leaders) == 10
    assert all(row[3] == 140 for row in leaders)
