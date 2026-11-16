"""Disposable 168-hour synthetic competition, driven through real game engines.

No Discord tokens, live config, production database or external network calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from snowfall.db.store import CITIES, Store
from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine
from snowfall.ops import reconcile, capture_final_awards


class FixedRandom:
    def random(self) -> float:
        return 0.10


def run_simulation() -> str:
    start = datetime(2026, 12, 10, 19, tzinfo=timezone.utc)
    season = "synthetic-seven-day-only"
    with TemporaryDirectory(prefix="snowfall-dry-run-") as tmp:
        db = Store(Path(tmp) / "test.sqlite3")
        db.initialize()
        db.ensure_season(season, start)
        users = list(range(100, 118))  # 3 players per city, 18 active participants
        for offset, user in enumerate(users):
            db.register(season, user, f"SimPlayer{user}", CITIES[offset // 3],
                        start - timedelta(days=1))
        db.transition(season, 999, "start", start, "Synthetic dry run; no real users")
        combat = CombatEngine(db, FixedRandom())
        world = WorldEngine(db, FixedRandom())
        throws, pve, hits = 0, 0, 0
        for day in range(7):
            day_start = start + timedelta(days=day)
            world.tick(season, day_start)
            for user in users:
                combat.ready(season, user, day_start + timedelta(minutes=1))
            for index, user in enumerate(users):
                target = users[(index + 3) % len(users)]
                shot = combat.throw(season, user, target, "quick", f"sim-pvp-{day}-{user}",
                                    day_start + timedelta(minutes=3))
                throws += 1
                hits += bool(shot.hit)
            for user in users:
                world.attack(season, user, "boss", f"sim-boss-{day}-{user}",
                             day_start + timedelta(minutes=10))
                pve += 1
                world.attack(season, user, "siege", f"sim-siege-{day}-{user}",
                             day_start + timedelta(minutes=11))
                pve += 1
            # Each 24-hour rollover locks the previous city's results.
            world.tick(season, day_start + timedelta(hours=23, minutes=59))
        end = start + timedelta(days=7)
        world.tick(season, end)
        assert db.season(season).phase(end) == "closed"
        db.transition(season, 999, "finalize", end, "Synthetic seven days complete")
        check = reconcile(db, season)
        if not check["ok"]:
            raise RuntimeError(f"Simulation scoring failed integrity check: {check}")
        with db.connect() as con:
            locked = con.execute("SELECT COUNT(*) FROM city_day_snapshots WHERE season_key=?",
                                 (season,)).fetchone()[0]
        if locked != 42:
            raise RuntimeError(f"Expected 42 city-day snapshots, got {locked}")
        awards = capture_final_awards(db, season, 999, end)
        if any(a["place"] not in (1, 2, 3) for a in awards):
            raise RuntimeError("Synthetic payout was not individual-only")
        return json.dumps({"mode": "OFFLINE SIMULATION, NO REAL PAYOUTS",
                           "days": 7, "players": len(users), "pvp_throws": throws,
                           "pvp_hits": hits, "pve_attempts": pve,
                           "city_day_snapshots": locked,
                           "award_places": len(awards), "ledger_ok": check["ok"]}, indent=2)


if __name__ == "__main__":
    print(run_simulation())
