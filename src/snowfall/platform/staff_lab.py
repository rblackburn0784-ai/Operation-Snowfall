"""Disposable QA-only staff rehearsal. Never writes to the shared season.

A separate temporary SQLite PracticeStore exercises the same CombatEngine and
WorldEngine as Discord and the website. One ephemeral lab per verified Discord
staff ID; sessions are retired on reset/end and expire after 90 minutes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from uuid import uuid4

from snowfall.db.store import CITIES
from snowfall.practice import PracticeStore
from snowfall.services.world import WorldEngine, THEMES

TEST_IDS = tuple(910000000000000001 + n for n in range(6))
MAX_LABS = 6
TTL = timedelta(minutes=90)


@dataclass
class _Session:
    ident: str
    day: int
    key: str
    root: TemporaryDirectory
    store: PracticeStore
    created: datetime
    touched: datetime
    last_action: str = "Rehearsal ready"


class WebStaffTestLab:
    def __init__(self):
        self.lock = RLock()
        self.sessions: dict[str, _Session] = {}
        self.receipts: dict[tuple[str, str], tuple[tuple, dict]] = {}
        self.history: dict[str, list[dict]] = {}
        self.reports: dict[str, list[dict]] = {}
        self.week_reports: dict[str, dict] = {}

    @staticmethod
    def _now(now):
        return now or datetime.now(timezone.utc)

    def _retire(self, actor: str):
        session = self.sessions.pop(actor, None)
        if session:
            session.store.retire()
            session.root.cleanup()

    def _clean(self, now):
        for actor, sess in list(self.sessions.items()):
            if now - sess.touched >= TTL:
                self._retire(actor)
        # Requests carry unique IDs, but we keep only the last 1000 outcomes.
        while len(self.receipts) > 1000:
            self.receipts.pop(next(iter(self.receipts)))

    def _new(self, actor: str, day: int, now: datetime) -> _Session:
        if not 1 <= day <= 7:
            raise ValueError("Test day must be 1–7")
        if len(self.sessions) >= MAX_LABS:
            raise ValueError("All staff test slots are occupied")
        root = TemporaryDirectory(prefix="snowfall-staff-rehearsal-")
        path = Path(root.name) / "practice.sqlite3"
        store = PracticeStore(path)
        token = uuid4().hex
        key = "web-practice-" + token
        start = now - timedelta(days=day - 1, seconds=35)
        try:
            store.initialize()
            store.ensure_season(key, start)
            for uid, city in zip(TEST_IDS, CITIES):
                store.register(key, uid, "TEST" + city.replace(" ", ""), city,
                               start - timedelta(minutes=5))
            store.transition(key, int(actor), "start", start,
                             "Disposable isolated web QA test session")
            WorldEngine(store).tick(key, now)
        except Exception:
            store.retire()
            root.cleanup()
            raise
        return _Session(token, day, key, root, store, now, now)

    def _history(self, actor, action, reason, now, detail):
        items = self.history.setdefault(actor, [])
        items.insert(0, {"at": now.isoformat(), "action": action,
                         "reason": reason, "detail": detail})
        del items[20:]

    def _view(self, actor: str, now: datetime) -> dict:
        sess = self.sessions.get(actor)
        result = {
            "scope": "DISPOSABLE_WEB_TEST_LAB",
            "shared_game_unchanged": True, "discord_bot_unchanged": True,
            "official_prizes_enabled": False, "persistent": False,
            "ttl_minutes": 90, "history": list(self.history.get(actor, [])),
            "comparisons": list(self.reports.get(actor, [])),
            "weekly_report": self.week_reports.get(actor),
            "active": bool(sess),
        }
        if not sess:
            return result
        with sess.store.connect() as con:
            scores = [dict(row) for row in con.execute(
                """SELECT p.mr_username, p.city, p.discord_user_id,
                          COALESCE(SUM(l.points),0) score
                   FROM players p LEFT JOIN score_ledger l
                   ON l.season_key=p.season_key AND l.player_id=p.discord_user_id
                   WHERE p.season_key=? GROUP BY p.id
                   ORDER BY score DESC, p.id""", (sess.key,)).fetchall()]
            boss = con.execute(
                "SELECT boss_hp,boss_initial_hp FROM world_days WHERE season_key=? AND day=?",
                (sess.key, sess.day)).fetchone()
            siege = [dict(x) for x in con.execute(
                "SELECT city,hp,initial_hp FROM world_sieges WHERE season_key=? AND day=? ORDER BY city",
                (sess.key, sess.day)).fetchall()]
            resources = [dict(x) for x in con.execute(
                """SELECT discord_user_id,snowballs,warmth,armour_hp,last_throw_at,
                          knockout_until,shield_until
                   FROM player_resources WHERE season_key=? ORDER BY discord_user_id""",
                (sess.key,)).fetchall()]
            totals = {
                "pvp": con.execute("SELECT COUNT(*) FROM combat_events WHERE season_key=?",
                                   (sess.key,)).fetchone()[0],
                "pve": con.execute("SELECT COUNT(*) FROM pve_events WHERE season_key=?",
                                   (sess.key,)).fetchone()[0],
                "ledger": con.execute("SELECT COUNT(*) FROM score_ledger WHERE season_key=?",
                                      (sess.key,)).fetchone()[0],
                "awards": con.execute("SELECT COUNT(*) FROM prize_awards WHERE season_key=?",
                                      (sess.key,)).fetchone()[0],
            }
        return result | {
            "session_id": sess.ident, "day": sess.day,
            "theme": THEMES[sess.day - 1], "created_at": sess.created.isoformat(),
            "expires_at": (sess.touched + TTL).isoformat(),
            "last_action": sess.last_action,
            "boss": dict(boss) if boss else None,
            "sieges": siege,
            "players": [{**p, "discord_user_id": str(p["discord_user_id"])}
                        for p in scores],
            "resources": [{**p, "discord_user_id": str(p["discord_user_id"])}
                          for p in resources],
            "totals": totals,
        }

    def snapshot(self, actor: str, *, now=None) -> dict:
        now = self._now(now)
        with self.lock:
            self._clean(now)
            return self._view(actor, now)

    def act(self, actor: str, action: str, day: int | None, reason: str,
            confirmation: str, request_id: str, session_id: str | None, *,
            now=None, options: dict | None = None) -> dict:
        now = self._now(now)
        if not reason or len(reason.strip()) < 8 or len(reason) > 220:
            raise ValueError("A reason of 8–220 characters is required")
        if len(request_id) < 16 or len(request_id) > 96:
            raise ValueError("Invalid request identifier")
        if action not in {"start", "day", "pvp", "boss", "siege", "resupply", "end",
                          "configure", "arcade", "mission", "simulate_week", "reset_all"}:
            raise ValueError("Unknown QA test action")
        expected = {"start": "START TEST", "day": "RESET TEST DAY",
                    "resupply": "RESUPPLY TEST", "end": "END TEST",
                    "reset_all": "RESET ALL TEST DATA",
                    "simulate_week": "SIMULATE 7 DAYS"}
        if action in expected and confirmation != expected[action]:
            raise ValueError("Type " + expected[action] + " to confirm")
        options = options or {}
        if not isinstance(options, dict) or len(json.dumps(options)) > 900:
            raise ValueError("Invalid or oversized test settings")
        signature = (action, day, reason, confirmation, session_id,
                     json.dumps(options, sort_keys=True))
        with self.lock:
            self._clean(now)
            receipt_key = (actor, request_id)
            previous = self.receipts.get(receipt_key)
            if previous:
                if previous[0] != signature:
                    raise ValueError("Request identifier reused with different values")
                return previous[1]
            current = self.sessions.get(actor)
            from snowfall.platform.lab_scenarios import LabScenarios
            detail = None
            if action == "reset_all":
                # Erase only the caller's disposable games, logs and reports.
                self._retire(actor)
                self.history.pop(actor, None)
                self.reports.pop(actor, None)
                self.week_reports.pop(actor, None)
                for key in [k for k in self.receipts if k[0] == actor]:
                    self.receipts.pop(key, None)
                message = "All of your disposable test data has been erased"
            elif action == "simulate_week":
                report = LabScenarios.simulate_week(self._new, actor, now, TEST_IDS)
                self.week_reports[actor] = report
                detail = {"week": report}
                message = ("Seven-day simulation " +
                           ("PASS" if report["passed"] else "REVIEW") +
                           ": " + str(report["total_points"]) +
                           " temporary ledger points, zero official awards")
            elif action == "start":
                if current:
                    raise ValueError("Finish the previous test before starting another")
                current = self._new(actor, day or 1, now)
                self.sessions[actor] = current
                message = "Disposable Day " + str(current.day) + " rehearsal started"
            else:
                if not current:
                    raise ValueError("No active web test session")
                if session_id != current.ident:
                    raise ValueError("Test session changed; refresh the control centre")
                if action == "day":
                    if day is None or day == current.day:
                        raise ValueError("Choose a different test day (1–7)")
                    self._retire(actor)
                    current = self._new(actor, day, now)
                    self.sessions[actor] = current
                    message = "Previous test erased; now testing Day " + str(day)
                elif action == "end":
                    self._retire(actor)
                    message = "Test ended; disposable scores, resources and encounters erased"
                elif action == "resupply":
                    with current.store.connect() as con:
                        con.execute("BEGIN IMMEDIATE")
                        con.execute("""UPDATE player_resources
                            SET snowballs=12,warmth=100,last_throw_at=NULL,
                                knockout_until=NULL,shield_until=NULL
                            WHERE season_key=?""", (current.key,))
                    message = "Only test players were resupplied; existing test scores remain"
                elif action == "configure":
                    detail = LabScenarios(current, TEST_IDS).configure(options, now)
                    message = "Fictional test resources and boss HP configured"
                elif action in ("pvp", "boss", "siege"):
                    if set(options) - {"outcome"}:
                        raise ValueError("Only a test hit/miss outcome may be chosen")
                    detail = LabScenarios(current, TEST_IDS).attack(
                        action, now, outcome=options.get("outcome", "random"))
                    message = (action.upper()+" test: "+
                               ("hit" if detail["hit"] else "miss") +
                               ", ledger comparison " +
                               ("PASS" if detail["passed"] else "REVIEW"))
                elif action == "arcade":
                    if set(options) - {"mode", "scenario"}:
                        raise ValueError("Unknown arcade settings")
                    detail = LabScenarios(current, TEST_IDS).arcade(
                        options.get("mode", "gallery"), now,
                        scenario=options.get("scenario", "perfect"))
                    message = ("Arcade "+detail["mode"]+" "+
                               ("PASS" if detail["passed"] and
                                detail["arcade_passed"] else "REVIEW"))
                elif action == "mission":
                    if set(options) - {"quest"}:
                        raise ValueError("Unknown mission settings")
                    detail = LabScenarios(current, TEST_IDS).mission(
                        options.get("quest", "community"), now)
                    message = ("Mission "+detail["quest"]+" "+
                               ("PASS" if detail["passed"] else "REVIEW"))
                else:
                    raise ValueError("Unknown test action")
            if action != "reset_all":
                self._history(actor, action, reason.strip(), now, message)
            if detail is not None and action not in {"simulate_week", "configure"}:
                log = self.reports.setdefault(actor, [])
                log.insert(0, detail)
                del log[100:]
            if actor in self.sessions:
                self.sessions[actor].last_action = message
                self.sessions[actor].touched = now
            out = self._view(actor, now)
            out["action_result"] = {"action": action, "message": message,
                                    "comparison": detail}
            self.receipts[receipt_key] = (signature, out)
            return out
