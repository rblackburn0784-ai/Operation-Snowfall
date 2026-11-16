"""Milestone F: auditable awards, reconciliations and offline-safe SQLite backups.

All award and score edits are transactions; tests and live season never share stores.
No function transfers MafiaReturns credits or perks automatically.
"""
from __future__ import annotations

import csv
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from snowfall.db.store import RegistrationError, Store, _timestamp
from snowfall.services.combat import CombatEngine


class OperationsError(ValueError):
    """A rejected organiser operation with no partial changes."""


def backup_sqlite(source: Path | str, directory: Path | str) -> Path:
    """Create an atomic, consistent WAL-aware backup with a SHA256 sidecar."""
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if not source.is_file():
        raise OperationsError("Database does not exist; cannot back it up")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"snowfall-{stamp}.sqlite3"
    fd, temp_name = tempfile.mkstemp(prefix=".snowfall-", suffix=".sqlite3", dir=directory)
    os.close(fd)
    staging = Path(temp_name)
    try:
        with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(staging)) as copied:
            original.backup(copied)
            result = copied.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise OperationsError(f"Backup integrity check failed: {result}")
        digest = sha256(staging.read_bytes()).hexdigest()
        manifest = {"sha256": digest, "size": staging.stat().st_size,
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "format": "sqlite3", "source_name": source.name}
        staging.replace(target)
        sidecar = Path(str(target) + ".json")
        sidecar.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return target
    finally:
        staging.unlink(missing_ok=True)


def check_backup(path: Path | str) -> dict:
    path = Path(path).resolve()
    manifest_path = Path(str(path) + ".json")
    if not path.is_file() or not manifest_path.is_file():
        raise OperationsError("Backup and its .json SHA256 manifest must both exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if path.stat().st_size != manifest["size"] or sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise OperationsError("Backup checksum mismatch: restore refused")
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as con:
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise OperationsError("Backup database integrity check failed")
    return manifest


def restore_sqlite(backup: Path | str, destination: Path | str, *, confirmation: str) -> Path:
    """Offline-only restore. Explicit confirmation, checksum and safety copy required."""
    if confirmation != "RESTORE":
        raise OperationsError("Restore refused: pass --confirm-restore RESTORE, with bot STOPPED")
    backup, destination = Path(backup).resolve(), Path(destination).resolve()
    if backup == destination:
        raise OperationsError("Backup and target must differ")
    check_backup(backup)
    # An active WAL may hold uncheckpointed writes; never replace its database.
    if any(Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise OperationsError("WAL/SHM files exist. Stop the bot and checkpoint first; restore refused")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup_sqlite(destination, destination.parent / "pre_restore_backups")
    fd, temp_name = tempfile.mkstemp(prefix=".restore-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    staging = Path(temp_name)
    try:
        with closing(sqlite3.connect(backup)) as original, closing(sqlite3.connect(staging)) as target:
            original.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise OperationsError("Staged database integrity check failed")
        try:
            staging.replace(destination)
        except PermissionError as exc:
            raise OperationsError(
                "Restore target is locked. Stop the bot and close all SQLite connections "
                "before retrying. The original database was not overwritten."
            ) from exc
    finally:
        staging.unlink(missing_ok=True)
    return destination


def check_health(store: Store, season_key: str, backup_dir: Path | None = None) -> dict:
    with store.connect() as con:
        integrity = con.execute("PRAGMA quick_check").fetchone()[0]
        version = con.execute("PRAGMA user_version").fetchone()[0]
        players = con.execute("SELECT COUNT(*) FROM players WHERE season_key=?", (season_key,)).fetchone()[0]
        ledger = con.execute("SELECT COUNT(*) FROM score_ledger WHERE season_key=?", (season_key,)).fetchone()[0]
    recent = None
    if backup_dir and Path(backup_dir).is_dir():
        backups = sorted(Path(backup_dir).glob("snowfall-*.sqlite3"))
        recent = str(backups[-1]) if backups else None
    return {"sqlite_check": integrity, "schema_version": version,
            "players": players, "ledger_entries": ledger,
            "latest_backup": recent, "database": str(store.path)}


def approve_launch(store: Store, season_key: str, host: int, reason: str, now: datetime) -> None:
    if len(reason.strip()) < 10:
        raise OperationsError("Launch approval needs a reason of at least ten characters")
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM season_state WHERE season_key=?", (season_key,)).fetchone()
        if row is None or Store._make_season(row).phase(now) not in ("not_open", "registration", "ready"):
            raise OperationsError("Launch approval must occur before the real event starts")
        old = con.execute("SELECT * FROM launch_approvals WHERE season_key=?", (season_key,)).fetchone()
        con.execute("""INSERT INTO launch_approvals
            (season_key,host_id,approved_at_utc,planned_start_utc,reason) VALUES(?,?,?,?,?)
            ON CONFLICT(season_key) DO UPDATE SET host_id=excluded.host_id,
            approved_at_utc=excluded.approved_at_utc, planned_start_utc=excluded.planned_start_utc,
            reason=excluded.reason""", (season_key, host, _timestamp(now), row["planned_start_utc"], reason.strip()))
        store._audit(con, season_key, host, 0, "launch:approve", reason.strip(), now,
                     dict(old) if old else None, {"planned_start": row["planned_start_utc"]})


def is_approved(store: Store, season_key: str) -> bool:
    with store.connect() as con:
        return con.execute("""SELECT 1 FROM launch_approvals a JOIN season_state s
            ON s.season_key=a.season_key AND s.planned_start_utc=a.planned_start_utc
            WHERE a.season_key=?""", (season_key,)).fetchone() is not None


def adjust_personal_score(store: Store, season_key: str, host: int, user_id: int, day: int,
                          delta: int, reason: str, source_id: str, now: datetime) -> int:
    """Append one audited signed ledger correction; never rewrite historical records."""
    if not 1 <= day <= 7 or not -300 <= delta <= 300 or delta == 0:
        raise OperationsError("Use day 1–7 and a nonzero correction of at most 300 points")
    if len(reason.strip()) < 10 or not source_id or len(source_id) > 128:
        raise OperationsError("A specific 10+ character reason and unique action ID are required")
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        prior = con.execute("SELECT * FROM score_ledger WHERE season_key=? AND source_key=?",
                            (season_key, "admin:" + source_id)).fetchone()
        if prior:
            if prior["player_id"] == user_id and prior["points"] == delta and prior["day"] == day:
                return prior["points"]
            raise OperationsError("Correction ID was already used for another adjustment")
        state = con.execute("SELECT * FROM season_state WHERE season_key=?", (season_key,)).fetchone()
        if not state or Store._make_season(state).phase(now) not in ("live", "paused", "closed"):
            raise OperationsError("Corrections permitted only after kickoff and before finalization")
        player = con.execute("SELECT * FROM players WHERE season_key=? AND discord_user_id=?",
                             (season_key, user_id)).fetchone()
        if player is None:
            raise RegistrationError("Unknown player")
        today = con.execute("SELECT COALESCE(SUM(points),0) FROM score_ledger WHERE season_key=? "
                            "AND player_id=? AND day=?", (season_key, user_id, day)).fetchone()[0]
        if today + delta < 0:
            raise OperationsError("Cannot reduce a player's day total below zero")
        con.execute("""INSERT INTO score_ledger
            (season_key,day,player_id,city,category,points,source_key,created_at_utc)
            VALUES(?,?,?,?,?,?,?,?)""", (season_key, day, user_id, player["city"],
                                          "admin_adjustment", delta, "admin:" + source_id,
                                          _timestamp(now)))
        store._audit(con, season_key, host, user_id, "score:adjust", reason.strip(), now,
                     {"day": day, "day_total": today},
                     {"day": day, "day_total": today + delta, "delta": delta})
        return delta


def reconcile(store: Store, season_key: str) -> dict:
    """Compare raw PvP events against immutable score ledger, not cached totals."""
    with store.connect() as con:
        rows = con.execute("""SELECT c.interaction_id,c.attacker_id,c.points_awarded,
            COALESCE((SELECT SUM(l.points) FROM score_ledger l WHERE
              l.season_key=c.season_key AND l.player_id=c.attacker_id AND l.category='pvp'
              AND l.source_key='combat:' || c.interaction_id),0) AS credited
            FROM combat_events c WHERE c.season_key=?""", (season_key,)).fetchall()
        mismatches = [r["interaction_id"] for r in rows if r["credited"] != r["points_awarded"]]
        caps = con.execute("""SELECT player_id,day,SUM(points) AS score FROM score_ledger
            WHERE season_key=? AND category IN ('pvp','defense') GROUP BY player_id,day
            HAVING score>300""", (season_key,)).fetchall()
        quest_duplicates = con.execute("""SELECT COUNT(*) FROM (
            SELECT player_id,day,SUM(points) AS score FROM score_ledger
            WHERE season_key=? AND category='quests' GROUP BY player_id,day HAVING score>70)""",
            (season_key,)).fetchone()[0]
        ledger_count = con.execute("SELECT COUNT(*) FROM score_ledger WHERE season_key=?",
                                   (season_key,)).fetchone()[0]
    return {"ok": not mismatches and not caps and not quest_duplicates,
            "combat_events": len(rows), "ledger_entries": ledger_count,
            "mismatched_combat_ids": mismatches[:20],
            "pvp_over_cap": [dict(r) for r in caps], "quest_over_cap_count": quest_duplicates}


def capture_final_awards(store: Store, season_key: str, host: int, now: datetime,
                         places: int = 3) -> list[dict]:
    """Snapshot immutable standings only after finalization; no city awards."""
    if not 1 <= places <= 10:
        raise OperationsError("Choose between 1 and 10 individual places")
    with store.connect() as con:
        state = con.execute("SELECT * FROM season_state WHERE season_key=?", (season_key,)).fetchone()
        if not state or Store._make_season(state).phase(now) != "finalized":
            raise OperationsError("Final individual awards require a finalized event")
        recorded = con.execute("SELECT COUNT(*) FROM prize_awards WHERE season_key=?", (season_key,)).fetchone()[0]
        if recorded:
            return [dict(r) for r in con.execute("SELECT * FROM prize_awards WHERE season_key=? "
                                                 "ORDER BY place", (season_key,))]
    # Standings are computed from the same immutable ledger as /snow leaderboard.
    leaders = CombatEngine(store).leaderboard(season_key, places + 20)
    # `flagged` accounts remain visible in the public list but cannot receive payouts.
    with store.connect() as con:
        eligible = []
        for name, city, user, score in leaders:
            row = con.execute("SELECT review_state FROM players WHERE season_key=? AND "
                              "discord_user_id=?", (season_key, user)).fetchone()
            if row and row["review_state"] not in ("flagged", "disqualified") and score > 0:
                eligible.append((name, city, user, score))
            if len(eligible) >= places:
                break
    if not reconcile(store, season_key)["ok"]:
        raise OperationsError("Score reconciliation failed; correct disputes before awards")
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        before = con.execute("SELECT COUNT(*) FROM prize_awards WHERE season_key=?", (season_key,)).fetchone()[0]
        if before:
            return [dict(r) for r in con.execute("SELECT * FROM prize_awards WHERE season_key=? "
                                                 "ORDER BY place", (season_key,))]
        for place, (name, city, user, score) in enumerate(eligible, 1):
            con.execute("""INSERT INTO prize_awards
                (season_key,place,discord_user_id,mr_username,city,points,reward,status)
                VALUES(?,?,?,?,?,?,?,?)""", (season_key, place, user, name, city, score,
                                              "Awaiting Kat's prize assignment", "pending"))
        store._audit(con, season_key, host, 0, "prizes:snapshot", "Final individual rankings",
                     now, None, {"winners": len(eligible), "city_prizes": 0})
        return [dict(r) for r in con.execute("SELECT * FROM prize_awards WHERE season_key=? "
                                             "ORDER BY place", (season_key,))]


def mark_prize(store: Store, season_key: str, host: int, place: int, reward: str,
               status: str, reason: str, now: datetime) -> None:
    if status not in ("pending", "paid") or not 1 <= place <= 10:
        raise OperationsError("Use a valid place and status: pending or paid")
    if not reward.strip() or len(reason.strip()) < 10:
        raise OperationsError("A reward description and an audit reason are required")
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM prize_awards WHERE season_key=? AND place=?",
                          (season_key, place)).fetchone()
        if row is None:
            raise OperationsError("No recorded award for that place")
        if row["status"] == "paid" and status != "paid":
            raise OperationsError("Paid awards cannot be reverted to pending")
        con.execute("UPDATE prize_awards SET reward=?,status=?,updated_at_utc=? "
                    "WHERE season_key=? AND place=?",
                    (reward.strip(), status, _timestamp(now), season_key, place))
        store._audit(con, season_key, host, row["discord_user_id"], "prizes:status",
                     reason.strip(), now, dict(row), {"reward": reward, "status": status})


def award_csv(rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("place", "discord_user_id", "mr_username", "city", "points",
                     "reward", "status"))
    for r in rows:
        writer.writerow((r["place"], r["discord_user_id"], r["mr_username"], r["city"],
                         r["points"], r["reward"], r["status"]))
    return output.getvalue().encode("utf-8-sig")
