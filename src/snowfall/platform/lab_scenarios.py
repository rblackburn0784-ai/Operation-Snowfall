"""Real-engine simulations scoped exclusively to disposable PracticeStore sessions.

No shared Store or bot worker is accepted. Expected awarded points are compared
with recorded temporary ledger deltas; arcade is explicitly scoring-neutral.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
import json
import secrets
from uuid import uuid4

from snowfall.practice import PracticeStore
from snowfall.services.combat import CombatEngine
from snowfall.services.world import WorldEngine, THEMES
from snowfall.services.social_arcade import GAMES, SocialArcadeEngine
from snowfall.services.economy import EconomyEngine
from snowfall.services.daily_missions import missions_for_day

FIELDS = {"snowballs": (0, 12), "warmth": (0, 100),
          "armour_hp": (0, 25), "cooldown_seconds": (0, 30)}
OUTCOMES = {"random", "hit", "miss"}
QUESTS = {"throws", "rivals", "community"}
ARCADE_OUTCOMES = {"perfect", "miss"}


class _FixedRoll:
    def __init__(self, outcome):
        self.outcome = outcome
        self.counter = 0

    def random(self):
        if self.outcome == "miss":
            return 0.999999
        self.counter += 1
        # Noncritical successful hit; boss damage roll is predictably centred.
        return 0.0 if self.counter % 2 else 0.5


class LabScenarios:
    def __init__(self, session, ids):
        if not isinstance(session.store, PracticeStore):
            raise TypeError("Only disposable practice stores are allowed")
        self.s = session
        self.ids = ids

    def _ledger(self):
        with self.s.store.connect() as con:
            return int(con.execute(
                "SELECT COALESCE(SUM(points),0) FROM score_ledger WHERE season_key=?",
                (self.s.key,)).fetchone()[0])

    def _report(self, kind, day, expected, actual, detail, **values):
        return {"kind": kind, "day": day, "expected_points": int(expected),
                "actual_points": int(actual), "difference": int(actual)-int(expected),
                "passed": int(actual) == int(expected), "detail": detail, **values}

    def configure(self, opts: dict, now: datetime):
        accepted = set(FIELDS) | {"player_index", "boss_hp"}
        if not opts or set(opts) - accepted:
            raise ValueError("Choose valid test-only resource controls")
        player_index = opts.get("player_index", 0)
        if type(player_index) is not int or not 0 <= player_index < len(self.ids):
            raise ValueError("Choose a fictional test player")
        fields = {}
        for key, (low, high) in FIELDS.items():
            if key in opts:
                val = opts[key]
                if type(val) is not int or not low <= val <= high:
                    raise ValueError(f"{key} must be between {low} and {high}")
                fields[key] = val
        if "boss_hp" in opts and (type(opts["boss_hp"]) is not int
                                  or not 0 <= opts["boss_hp"] <= 100000):
            raise ValueError("Snow Don HP must be a nonnegative integer up to 100000")
        if not fields and "boss_hp" not in opts:
            raise ValueError("Select a resource or boss HP change")
        with self.s.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if fields:
                values = {k: v for k, v in fields.items() if k != "cooldown_seconds"}
                if "cooldown_seconds" in fields:
                    remaining = fields["cooldown_seconds"]
                    values["last_throw_at"] = ((now-timedelta(seconds=30-remaining)).isoformat()
                                               if remaining else None)
                if "armour_hp" in fields:
                    values["armour_expires_at"] = (
                        (now+timedelta(hours=1)).isoformat() if fields["armour_hp"] else None)
                if "warmth" in fields:
                    values["warmth_regen_at"] = now.isoformat()
                if "snowballs" in fields:
                    values["snowball_regen_at"] = now.isoformat()
                assigns = ",".join(f"{column}=?" for column in values)
                con.execute(f"UPDATE player_resources SET {assigns} WHERE "
                            "season_key=? AND discord_user_id=?",
                            (*values.values(), self.s.key, self.ids[player_index]))
            if "boss_hp" in opts:
                hp = opts["boss_hp"]
                row = con.execute("SELECT boss_initial_hp FROM world_days "
                                  "WHERE season_key=? AND day=?",
                                  (self.s.key, self.s.day)).fetchone()
                if row is None or hp > row[0]:
                    raise ValueError("Snow Don HP cannot exceed today's starting HP")
                con.execute("UPDATE world_days SET boss_hp=?,cleared_at_utc=NULL "
                            "WHERE season_key=? AND day=?",
                            (hp, self.s.key, self.s.day))
        return {"player_index": player_index, "settings": fields,
                "boss_hp": opts.get("boss_hp"), "scope": "test_only"}

    def _clear_throw(self, user):
        with self.s.store.connect() as con:
            con.execute("UPDATE player_resources SET last_throw_at=NULL "
                        "WHERE season_key=? AND discord_user_id=?", (self.s.key, user))

    def attack(self, kind: str, now: datetime, *, outcome="random", clear=False):
        if kind not in {"pvp", "boss", "siege"} or outcome not in OUTCOMES:
            raise ValueError("Unknown combat test scenario")
        if clear:
            self._clear_throw(self.ids[0])
        old = self._ledger()
        engine_rng = (secrets.SystemRandom() if outcome == "random"
                      else _FixedRoll(outcome))
        token = "test-" + uuid4().hex
        if kind == "pvp":
            CombatEngine(self.s.store).ready(self.s.key, self.ids[1], now)
            result = CombatEngine(self.s.store, rng=engine_rng).throw(
                self.s.key, self.ids[0], self.ids[1], "standard", token, now)
            expected = result.points_awarded + result.defense_points
        else:
            result = WorldEngine(self.s.store, rng=engine_rng).attack(
                self.s.key, self.ids[0], kind, token, now)
            expected = result.points + result.theme_points
        actual = self._ledger()-old
        if outcome != "random" and result.hit != (outcome == "hit"):
            raise AssertionError("Controlled hit/miss did not match the real engine")
        return self._report(kind, self.s.day, expected, actual,
                            "Real engine award compared with temporary score ledger",
                            scenario=outcome, hit=result.hit,
                            damage=(result.armour_damage+result.warmth_damage
                                    if kind == "pvp" else result.damage),
                            mechanics=asdict(result))

    def arcade(self, mode: str, now: datetime, *, scenario="perfect"):
        if mode not in GAMES or scenario not in ARCADE_OUTCOMES:
            raise ValueError("Choose a supported arcade game and outcome")
        old = self._ledger()
        engine = SocialArcadeEngine(self.s.store)
        session = engine.begin(self.s.key, self.ids[0], mode, now)
        expected_score = 0
        for index in range(session.total_rounds):
            with self.s.store.connect() as con:
                row = con.execute(
                    "SELECT puzzles_json FROM social_arcade_runs WHERE session_id=?",
                    (session.session_id,)).fetchone()
                puzzle = json.loads(row[0])[index]
            choice = (puzzle["answer"] if scenario == "perfect" else
                      next(v for v in puzzle["choices"] if v != puzzle["answer"]))
            move = engine.move(self.s.key, self.ids[0], session.session_id,
                               index, choice, "test-" + uuid4().hex, now)
            expected_score += move.delta
            session = move.session
        actual = self._ledger()-old
        return self._report("arcade", self.s.day, 0, actual,
                            "Arcade records must never add official score points",
                            mode=mode, scenario=scenario,
                            expected_arcade_score=expected_score,
                            actual_arcade_score=session.score,
                            arcade_passed=(expected_score == session.score),
                            finished=session.finished)

    def mission(self, quest: str, now: datetime):
        if quest not in QUESTS:
            raise ValueError("Choose throws, rivals or community mission")
        econ = EconomyEngine(self.s.store)
        selected = next(m for m in missions_for_day(self.s.day) if m.key == quest)
        prep = []
        # Fulfil missions through the original combat/PvE engines, not fake rows.
        for idx in range(9):
            current = next(q for q in econ.quests(self.s.key, self.ids[0], now)
                           if q.key == quest)
            if current.progress >= current.target:
                break
            if self.s.day == 1 and quest == "rivals":
                target = self.ids[1+(idx % 2)]
                self._clear_throw(self.ids[0])
                CombatEngine(self.s.store).ready(self.s.key, target, now)
                before = self._ledger()
                result = CombatEngine(self.s.store, _FixedRoll("hit")).throw(
                    self.s.key, self.ids[0], target, "standard",
                    "test-" + uuid4().hex, now)
                prep.append(self._report("mission_prep_pvp", self.s.day,
                            result.points_awarded+result.defense_points,
                            self._ledger()-before, "Mission preparation uses real PvP"))
            else:
                prep.append(self.attack("boss" if idx % 2 == 0 else "siege",
                                        now, outcome="hit", clear=True))
        current = next(q for q in econ.quests(self.s.key, self.ids[0], now)
                       if q.key == quest)
        if current.progress < current.target:
            raise ValueError(f"Mission could not be completed: {current.progress}/{current.target}")
        before = self._ledger()
        with self.s.store.connect() as con:
            had_theme = bool(con.execute(
                "SELECT 1 FROM score_ledger WHERE season_key=? AND player_id=? "
                "AND day=3 AND category='theme' AND source_key='theme:d3:quest'",
                (self.s.key, self.ids[0])).fetchone())
        result = econ.claim_quest(self.s.key, self.ids[0], quest, now)
        expected = 20 + (10 if self.s.day == 3 and not had_theme else 0)
        return self._report("mission", self.s.day, expected, self._ledger()-before,
                            "Approved quest reward and Day 3 theme bonus",
                            quest=quest, title=selected.title,
                            progress=current.progress, target=current.target,
                            reward=result.text, preparation_checks=prep)

    @staticmethod
    def simulate_week(create_session, actor: str, now: datetime, ids: tuple):
        """One coherent 7-day timeline on a fresh, disposable independent store."""
        sess = create_session(actor, 1, now)
        days = []
        try:
            for day in range(1, 8):
                when = now + timedelta(days=day-1)
                sess.day = day
                WorldEngine(sess.store).tick(sess.key, when)
                step = LabScenarios(sess, ids)
                checks = []
                # Exercise exact real mechanics, including day-specific themes.
                checks.append(step.attack("pvp", when, outcome="hit", clear=True))
                checks.append(step.attack("boss", when, outcome="hit", clear=True))
                checks.append(step.attack("siege", when, outcome="miss", clear=True))
                checks.append(step.mission("community", when))
                checks.append(step.arcade(list(GAMES)[(day-1) % len(GAMES)], when))
                if day == 7:
                    checks.append(step.arcade("trivia", when))
                with sess.store.connect() as con:
                    total = int(con.execute(
                        "SELECT COALESCE(SUM(points),0) FROM score_ledger WHERE season_key=? AND day=?",
                        (sess.key, day)).fetchone()[0])
                    awards = con.execute(
                        "SELECT COUNT(*) FROM prize_awards WHERE season_key=?",
                        (sess.key,)).fetchone()[0]
                days.append({"day": day, "theme": THEMES[day-1],
                             "checks": checks, "ledger_points": total,
                             "checks_passed": all(
                                 c["passed"] and c.get("arcade_passed", True)
                                 and all(x["passed"] for x in c.get("preparation_checks", []))
                                 for c in checks), "awards": awards})
            return {"days": days, "days_tested": 7,
                    "passed": all(d["checks_passed"] and d["awards"] == 0 for d in days),
                    "total_points": sum(d["ledger_points"] for d in days),
                    "official_awards": 0,
                    "scope": "DISPOSABLE_WEEK_SIMULATION",
                    "shared_game_unchanged": True}
        finally:
            sess.store.retire()
            sess.root.cleanup()
