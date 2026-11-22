"""v2.9.8h — Snowball Alley must show a rival's actual equipped cosmetics."""
from datetime import datetime, timezone

from snowfall.db.store import Store
from snowfall.platform.game import SharedGame
from snowfall.services.combat import CombatEngine

NOW = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


def _make_game(tmp_path):
    store = Store(tmp_path / "avatar_qa.sqlite3")
    store.initialize()
    store.ensure_season("qa", NOW)
    for uid, name, city in (
        (101, "Viewer", "Chicago"),
        (102, "ActualRival", "Detroit"),
        (103, "AnotherRival", "New York"),
    ):
        store.register("qa", uid, name, city, NOW)
    store.transition("qa", 900, "start", NOW, "QA")
    combat = CombatEngine(store)
    for uid in (101, 102, 103):
        combat.ready("qa", uid, NOW)
    return SharedGame(store, "qa")


def test_pvp_targets_expose_only_unlocked_equipped_cosmetics(tmp_path):
    game = _make_game(tmp_path)
    with game.store.connect() as con:
        for key, category in (
            ("frost_spectre", "portrait"),
            ("gold_frame", "frame"),
            ("midnight_banner", "banner"),
            ("scarf", "gear"),
            ("candy_trail", "trail"),
        ):
            con.execute(
                "INSERT INTO cosmetic_unlocks "
                "(season_key,discord_user_id,cosmetic_key,unlocked_at_utc) VALUES(?,?,?,?)",
                ("qa", 102, key, NOW.isoformat()),
            )
            con.execute(
                "INSERT INTO cosmetic_equipped "
                "(season_key,discord_user_id,category,cosmetic_key) VALUES(?,?,?,?)",
                ("qa", 102, category, key),
            )
        # An unowned item and a key assigned to an incorrect slot must be
        # rejected even if a legacy or damaged equipment record contains them.
        con.execute(
            "INSERT INTO cosmetic_equipped "
            "(season_key,discord_user_id,category,cosmetic_key) VALUES(?,?,?,?)",
            ("qa", 103, "frame", "ice_frame"),
        )
        con.execute(
            "INSERT INTO cosmetic_unlocks "
            "(season_key,discord_user_id,cosmetic_key,unlocked_at_utc) VALUES(?,?,?,?)",
            ("qa", 103, "scarf", NOW.isoformat()),
        )
        con.execute(
            "INSERT INTO cosmetic_equipped "
            "(season_key,discord_user_id,category,cosmetic_key) VALUES(?,?,?,?)",
            ("qa", 103, "banner", "scarf"),
        )

    targets = {entry["player_id"]: entry for entry in game.targets(101, now=NOW)}
    assert set(targets) == {"102", "103"}
    assert targets["102"]["appearance"] == {
        "portrait": "frost_spectre", "frame": "gold_frame",
        "banner": "midnight_banner", "gear": "scarf", "trail": "candy_trail",
    }
    assert targets["103"]["appearance"] == {}
    assert targets["102"]["mr_username"] == "ActualRival"
    assert targets["102"]["hits_remaining"] >= 0
    assert "unlocked" not in targets["102"]
    assert "inventory" not in targets["102"]
    assert "discord_user_id" not in targets["102"]
    with game.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM combat_events").fetchone()[0] == 0


def test_rival_wardrobe_preview_updates_after_equipment_change(tmp_path):
    game = _make_game(tmp_path)
    assert next(t for t in game.targets(101, now=NOW)
                if t["player_id"] == "102")["appearance"] == {}
    with game.store.connect() as con:
        for key in ("snow_trail", "candy_trail"):
            con.execute(
                "INSERT INTO cosmetic_unlocks "
                "(season_key,discord_user_id,cosmetic_key,unlocked_at_utc) VALUES(?,?,?,?)",
                ("qa", 102, key, NOW.isoformat()),
            )
        con.execute(
            "INSERT INTO cosmetic_equipped "
            "(season_key,discord_user_id,category,cosmetic_key) VALUES(?,?,?,?)",
            ("qa", 102, "trail", "snow_trail"),
        )
    first = next(t for t in game.targets(101, now=NOW)
                 if t["player_id"] == "102")
    assert first["appearance"] == {"trail": "snow_trail"}
    with game.store.connect() as con:
        con.execute(
            "UPDATE cosmetic_equipped SET cosmetic_key=? "
            "WHERE season_key=? AND discord_user_id=? AND category='trail'",
            ("candy_trail", "qa", 102),
        )
    second = next(t for t in game.targets(101, now=NOW)
                  if t["player_id"] == "102")
    assert second["appearance"] == {"trail": "candy_trail"}


def test_empty_eligible_targets_do_not_query_cosmetic_slots(tmp_path):
    store = Store(tmp_path / "no_rivals.sqlite3")
    store.initialize()
    store.ensure_season("qa", NOW)
    store.register("qa", 101, "Solo", "Chicago", NOW)
    store.transition("qa", 900, "start", NOW, "QA")
    CombatEngine(store).ready("qa", 101, NOW)
    assert SharedGame(store, "qa").targets(101, now=NOW) == []
