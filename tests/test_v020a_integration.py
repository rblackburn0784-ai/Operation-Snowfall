"""End-to-end v0.2.0a compatibility smoke test using actual service engines.

No Discord token required. All game actions share the same SQLite database and
clock, proving new activities cannot inflate older combat or prize ledgers.
"""
from datetime import datetime, timedelta, timezone

from snowfall.db.store import Store
from snowfall.ops import reconcile
from snowfall.services.achievements import AchievementEngine
from snowfall.services.combat import CombatEngine
from snowfall.services.community import CommunityEngine
from snowfall.services.economy import EconomyEngine
from snowfall.services.winter_fun import WinterFunEngine
from snowfall.services.world import WorldEngine

START = datetime(2026, 12, 21, 19, tzinfo=timezone.utc)
KEY = "v020a-integration"


class CertainHit:
    def random(self):
        return 0.01


def test_full_live_day_all_engines_share_valid_state_without_bonus_exploits(tmp_path):
    store = Store(tmp_path / "integration.sqlite3")
    store.initialize()
    store.ensure_season(KEY, START)
    for user, name, city in (
        (101, "TheDude", "Chicago"),
        (201, "RivalNewYork", "New York"),
        (301, "RivalDetroit", "Detroit"),
    ):
        store.register(KEY, user, name, city, START - timedelta(hours=2))
    store.transition(KEY, 999, "start", START, "Integration test kickoff")
    WorldEngine(store).tick(KEY, START)

    combat = CombatEngine(store, CertainHit())
    world = WorldEngine(store, CertainHit())
    economy = EconomyEngine(store, CertainHit())
    winter = WinterFunEngine(store, CertainHit())

    combat.ready(KEY, 201, START)
    combat.ready(KEY, 301, START)

    # Two real rival hits, three real NPC hits: five legitimate attacks total.
    assert combat.throw(KEY, 101, 201, "quick", "hit-ny", START + timedelta(minutes=1)).hit
    assert combat.throw(KEY, 101, 301, "quick", "hit-detroit", START + timedelta(minutes=2)).hit
    for i in range(3):
        result = world.attack(KEY, 101, "boss", f"boss-{i}",
                              START + timedelta(minutes=3+i))
        assert result.hit and result.points > 0

    assert world.attack(KEY, 101, "siege", "siege-0",
                        START + timedelta(minutes=6)).hit

    at = START + timedelta(minutes=8)
    assert all(not quest.claimed for quest in economy.quests(KEY, 101, at))
    for key in ("throws", "rivals", "community"):
        assert "+20 points" in economy.claim_quest(KEY, 101, key, at).text
    assert all(q.claimed for q in economy.quests(KEY, 101, at))
    assert economy.present(KEY, 101, "one-present", at).source == "daily"
    assert economy.present(KEY, 101, "another-present", at).repeated
    assert economy.inventory(KEY, 101, at).quantities["cocoa"] >= 1
    assert "Guard activated" in economy.guard(KEY, 101, "on", "guard-on", at).text
    assert "Guard lowered" in economy.guard(KEY, 101, "off", "guard-off", at).text

    pre_arcade_score = combat.ledger_total(KEY, 101)
    assert pre_arcade_score > 60
    assert winter.encounter(KEY, 101, "souvenir", at).souvenir
    for mode in ("target", "dodge", "boss"):
        assert winter.play(KEY, 101, mode, f"arcade-{mode}", at).points > 0
    assert "unlocked" in winter.buy(KEY, 101, "snow_trail", "cosmetic-buy", at)
    assert "Equipped" in winter.equip(KEY, 101, "snow_trail", at)
    wardrobe = winter.shop(KEY, 101, at)
    assert wardrobe.equipped["trail"] == "snow_trail"
    assert wardrobe.encounter is not None
    assert combat.ledger_total(KEY, 101) == pre_arcade_score

    city = CommunityEngine(store).headquarters(KEY, 101, at)
    assert city.objective.completed
    trophies = AchievementEngine(store).cabinet(KEY, 101)
    assert trophies.records.pvp_hits == 2
    assert trophies.records.boss_attacks == 3
    assert trophies.records.siege_attacks == 1
    assert trophies.records.quests == 3

    audit = reconcile(store, KEY)
    assert audit["ok"], audit
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM quest_claims").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM cosmetic_purchases").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM arcade_events").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
