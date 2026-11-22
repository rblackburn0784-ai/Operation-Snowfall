"""v2.9.8e full Test Lab 2.0 scenarios, isolation, replay, and score evidence."""
from datetime import datetime, timedelta, timezone

import pytest

from snowfall.db.store import Store
from snowfall.platform.staff_lab import WebStaffTestLab
from test_v298d_lab import STAFF, _client


NOW = datetime(2026, 12, 22, 19, tzinfo=timezone.utc)


def act(lab, action, *, day=None, confirmation="", options=None, key="X" * 30,
        session_id=None, actor=STAFF, now=NOW):
    return lab.act(actor, action, day, "v2.9.8e isolated acceptance",
                   confirmation, key, session_id, now=now, options=options)


def check_shared(shared, before):
    with shared.connect() as con:
        for table in ("players", "score_ledger", "combat_events", "pve_events",
                      "prize_awards", "quest_claims", "social_arcade_runs"):
            actual = con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            assert actual == before[table], table


def test_lab_advanced_combat_resources_and_score_comparisons(tmp_path):
    shared = Store(tmp_path / "shared.sqlite3")
    shared.initialize()
    shared.ensure_season("web-qa-2026", NOW)
    before = {}
    with shared.connect() as con:
        before = {t: con.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
                  for t in ("players", "score_ledger", "combat_events", "pve_events",
                            "prize_awards", "quest_claims", "social_arcade_runs")}
    lab = WebStaffTestLab()
    started = act(lab, "start", day=3, confirmation="START TEST")
    session_id = started["session_id"]
    boss_max = started["boss"]["boss_initial_hp"]
    configured = act(lab, "configure", session_id=session_id,
                     key="A"*30,
                     options={"player_index": 1, "snowballs": 4, "warmth": 80,
                              "armour_hp": 20, "cooldown_seconds": 0,
                              "boss_hp": max(10, boss_max//2)})
    assert configured["resources"][1]["armour_hp"] == 20
    assert configured["resources"][1]["warmth"] == 80
    assert configured["boss"]["boss_hp"] == max(10, boss_max//2)
    hit = act(lab, "pvp", session_id=session_id, key="B"*30,
              options={"outcome": "hit"})
    comparison = hit["action_result"]["comparison"]
    assert comparison["hit"] and comparison["passed"]
    assert comparison["expected_points"] == comparison["actual_points"]
    assert comparison["damage"] >= 0
    for candidate, settings in (({"snowballs": 13}, "snowballs"),
                                ({"armour_hp": -1}, "armour_hp"),
                                ({"boss_hp": boss_max+1}, "Snow Don HP"),
                                ({"player_index": 12,"warmth":50}, "fictional"),
                                ({"snowballs": True}, "snowballs")):
        with pytest.raises(ValueError, match=settings):
            act(lab, "configure", session_id=session_id,
                key="Z"*(20+len(settings)), options=candidate)
    missed = act(lab, "boss", session_id=session_id, key="C"*30,
                 options={"outcome": "miss"})
    assert not missed["action_result"]["comparison"]["hit"]
    assert missed["action_result"]["comparison"]["passed"]
    assert all(c["passed"] for c in missed["comparisons"])
    assert missed["totals"]["awards"] == 0
    check_shared(shared, before)


@pytest.mark.parametrize("mode", ["gallery", "safe", "snowman", "catch", "trivia"])
def test_every_arcade_game_is_scoring_neutral(mode):
    lab = WebStaffTestLab()
    start = act(lab, "start", day=1, confirmation="START TEST")
    res = act(lab, "arcade", session_id=start["session_id"], key="A"*30,
              options={"mode": mode, "scenario": "perfect"})
    evidence = res["action_result"]["comparison"]
    assert evidence["passed"] and evidence["arcade_passed"]
    assert evidence["finished"]
    assert evidence["expected_arcade_score"] == 100
    assert evidence["actual_arcade_score"] == 100
    assert evidence["actual_points"] == evidence["expected_points"] == 0
    assert res["totals"]["awards"] == 0


@pytest.mark.parametrize("day,quest", [(1, "rivals"), (2, "throws"),
                                        (3, "community"), (5, "rivals")])
def test_daily_mission_claim_uses_existing_rules(day, quest):
    lab = WebStaffTestLab()
    started = act(lab, "start", day=day, confirmation="START TEST")
    result = act(lab, "mission", session_id=started["session_id"],
                 key="M"*30, options={"quest": quest})
    check = result["action_result"]["comparison"]
    assert check["passed"] and check["progress"] >= check["target"]
    assert check["expected_points"] == (30 if day == 3 else 20)
    assert all(c["passed"] for c in check["preparation_checks"])
    assert result["totals"]["awards"] == 0


def test_full_week_is_coherent_read_only_and_reset_all_replay_safe(tmp_path):
    shared = Store(tmp_path / "real.sqlite3")
    shared.initialize()
    shared.ensure_season("web-qa-2026", NOW)
    shared.register("web-qa-2026", 101, "SnowDude", "Chicago",
                    NOW-timedelta(days=1))
    with shared.connect() as con:
        before = {t: con.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
                  for t in ("players", "score_ledger", "combat_events", "pve_events",
                            "prize_awards", "quest_claims", "social_arcade_runs")}
    lab = WebStaffTestLab()
    week = act(lab, "simulate_week", confirmation="SIMULATE 7 DAYS", key="W"*30)
    report = week["weekly_report"]
    assert report["days_tested"] == 7
    assert [x["day"] for x in report["days"]] == list(range(1, 8))
    assert report["passed"]
    assert report["total_points"] > 0
    assert report["official_awards"] == 0
    assert all(len(d["checks"]) >= 5 for d in report["days"])
    assert all(c["passed"] for d in report["days"] for c in d["checks"])
    assert week == act(lab, "simulate_week", confirmation="SIMULATE 7 DAYS",
                       key="W"*30)
    assert week["active"] is False
    with pytest.raises(ValueError, match="Type RESET ALL"):
        act(lab, "reset_all", key="R"*30)
    erased = act(lab, "reset_all", key="R"*30,
                 confirmation="RESET ALL TEST DATA")
    assert erased["history"] == []
    assert erased["comparisons"] == []
    assert erased["weekly_report"] is None
    assert not erased["active"]
    assert erased == act(lab, "reset_all", key="R"*30,
                         confirmation="RESET ALL TEST DATA")
    check_shared(shared, before)


def test_lab_api_discord_staff_only_and_never_leaks_answers(tmp_path):
    client, ids, shared = _client(tmp_path)
    with client:
        token, csrf = ids.new_session(6000000000000000001)
        client.cookies.set("snowfall_session", token)
        action = {"action": "simulate_week", "reason": "QA simulation export",
                  "confirmation": "SIMULATE 7 DAYS", "request_id": "a"*32}
        assert client.post("/v1/staff/lab/action", json=action).status_code == 403
        result = client.post("/v1/staff/lab/action", json=action,
                             headers={"X-Snowfall-CSRF": csrf})
        assert result.status_code == 200, result.text
        response = result.json()
        assert response["weekly_report"]["passed"]
        assert response["active"] is False
        assert "puzzles_json" not in result.text
        assert "answer" not in result.text
        assert client.get("/v1/staff/lab").json()["weekly_report"]["days_tested"] == 7
        with shared.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
