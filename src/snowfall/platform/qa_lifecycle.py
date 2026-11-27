"""Explicit, audited lifecycle changes for the isolated shared QA event only."""
from datetime import datetime, timedelta, timezone
import json

from snowfall.db.store import Store, _timestamp
from snowfall.platform.staging import QA_DB, STAGING_PROJECT

QA_SEASON = "web-qa-2026"
CONFIRMATIONS = {
    "restart": "RESTART QA EVENT",
    "day": "SELECT QA DAY",
    "extend": "EXTEND QA EVENT",
    "reset": "RESET QA GAMEPLAY",
}
# Child tables precede parents. Keep registrations, identity tables, staff audit,
# publication IDs and prize records. Never use CASCADE.
GAME_TABLES = (
    "web_arcade_gallery_shots", "web_arcade_safe_actions",
    "web_arcade_snowman_actions", "web_arcade_catch_actions",
    "web_arcade_trivia_answers", "web_arcade_gallery_sessions",
    "web_arcade_safe_sessions", "web_arcade_snowman_sessions",
    "web_arcade_catch_sessions", "web_arcade_trivia_sessions",
    "web_arcade_practice_sessions", "social_arcade_turns", "social_arcade_stamps",
    "social_arcade_runs", "wire_decisions", "wire_submissions",
    "combat_events", "score_ledger", "item_events", "quest_claims",
    "mystery_gifts", "world_sieges", "pve_events", "city_day_snapshots",
    "world_days", "world_settings", "launch_approvals", "player_titles",
    "cosmetic_unlocks", "cosmetic_equipped", "cosmetic_purchases",
    "encounter_events", "arcade_events", "mystery_clues", "mystery_guesses",
    "mystery_secrets", "player_inventory", "player_economy", "player_resources",
)


def _check_database(con, postgres):
    if postgres:
        if con.execute("SELECT current_database()").fetchone()[0] != QA_DB:
            raise ValueError("Lifecycle controls require the dedicated QA database")
        marker = con.execute(
            "SELECT project_id,season_key FROM snowfall_web_qa_marker WHERE singleton=1"
        ).fetchone()
        if marker is None or tuple(marker[i] for i in (0, 1)) != (STAGING_PROJECT, QA_SEASON):
            raise ValueError("Unverified isolated QA database")
    seasons = con.execute("SELECT season_key FROM season_state").fetchall()
    if [row[0] for row in seasons] != [QA_SEASON]:
        raise ValueError("Lifecycle controls require exactly one isolated QA season")


def _ensure_extension_column(con, postgres, raw):
    # Optional, QA-only additive field. Normal v11 stores and imported production
    # databases retain their original schema and behaviour.
    if "qa_extension_seconds" not in raw.keys():
        if postgres:
            con.execute("ALTER TABLE season_state ADD COLUMN IF NOT EXISTS "
                        "qa_extension_seconds INTEGER NOT NULL DEFAULT 0")
        else:
            con.execute("ALTER TABLE season_state ADD COLUMN "
                        "qa_extension_seconds INTEGER NOT NULL DEFAULT 0")


def _snapshot(season, now):
    end = season.projected_end(now)
    return {"phase": season.phase(now), "day": season.day(now),
            "started_at": _timestamp(season.started_at) if season.started_at else None,
            "projected_end": _timestamp(end) if end else None,
            "extension_seconds": season.qa_extension_seconds}


def _reset_gameplay(con, postgres, effective_now):
    if con.execute("SELECT COUNT(*) FROM prize_awards WHERE season_key=?",
                   (QA_SEASON,)).fetchone()[0]:
        raise ValueError("QA reset refused: prize records exist")
    existing = []
    for table in GAME_TABLES:
        present = (con.execute("SELECT to_regclass(?)", (table,)).fetchone()[0]
                   if postgres else con.execute(
                       "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (table,)).fetchone())
        if not present:
            if not table.startswith("web_arcade_"):
                raise ValueError("QA reset refused: missing gameplay table")
            continue
        if con.execute(f"SELECT COUNT(*) FROM {table} WHERE season_key<>?",
                       (QA_SEASON,)).fetchone()[0]:
            raise ValueError("QA reset refused: another season has gameplay records")
        existing.append(table)
    if postgres:
        # TRUNCATE is transactional, respects FK dependencies, and does not
        # disable the normal immutable-history triggers. No CASCADE or identities.
        con.execute("TRUNCATE TABLE " + ", ".join(existing))
    else:
        # Disposable SQLite rehearsal/test database only. Preserve all trigger
        # definitions; dropping and recreating them occurs inside this transaction.
        for table in existing:
            triggers = con.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                (table,)).fetchall()
            for trigger in triggers:
                name = trigger[0].replace('"', '""')
                con.execute(f'DROP TRIGGER "{name}"')
            con.execute(f"DELETE FROM {table} WHERE season_key=?", (QA_SEASON,))
            for trigger in triggers:
                con.execute(trigger[1])
    at = _timestamp(effective_now)
    con.execute("""INSERT INTO player_resources
        (season_key,discord_user_id,snowball_regen_at,warmth_regen_at)
        SELECT season_key,discord_user_id,?,? FROM players WHERE season_key=?""",
                (at, at, QA_SEASON))


def apply_qa_lifecycle(game, *, actor_id, action, confirmation, reason,
                       request_id, day=None, extension_days=None, now=None):
    if game is None or game.season != QA_SEASON:
        raise ValueError("Lifecycle controls are restricted to isolated QA")
    if action not in CONFIRMATIONS or confirmation != CONFIRMATIONS[action]:
        raise ValueError("Typed confirmation does not match the QA action")
    reason = reason.strip()
    if actor_id <= 0 or not 8 <= len(reason) <= 220 or not 16 <= len(request_id) <= 96:
        raise ValueError("Invalid actor, reason or request ID")
    if (action == "day") != (day is not None) or (day is not None and not 1 <= day <= 7):
        raise ValueError("Select a day from 1 to 7 only for day selection")
    if ((action == "extend") != (extension_days is not None)
            or (extension_days is not None and not 1 <= extension_days <= 7)):
        raise ValueError("Select 1 to 7 extra days only for event extension")
    now = now or datetime.now(timezone.utc)
    store = game.store
    postgres = getattr(store, "backend", "") == "postgres"
    signature = {"action": action, "day": day, "extension_days": extension_days,
                 "reason": reason}
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        _check_database(con, postgres)
        for row in con.execute(
                "SELECT after_json FROM admin_audit WHERE season_key=? AND actor_id=? "
                "AND action LIKE 'qa_lifecycle:%' ORDER BY id DESC",
                (QA_SEASON, actor_id)).fetchall():
            prior = json.loads(row[0] or "{}")
            if prior.get("request_id") == request_id:
                if prior.get("request") != signature:
                    raise ValueError("Request ID already used for a different QA action")
                return {"scope": "ISOLATED_QA_ONLY", "replayed": True, **prior["result"]}
        raw = con.execute("SELECT * FROM season_state WHERE season_key=?",
                          (QA_SEASON,)).fetchone()
        _ensure_extension_column(con, postgres, raw)
        old = store._make_season(raw)
        before = _snapshot(old, now)
        if old.finalized_at is not None and action != "restart":
            raise ValueError("Restart a finalized QA event before other lifecycle changes")
        if action in ("restart", "reset"):
            _reset_gameplay(con, postgres, now if action == "restart" else old.effective_now(now))
        if action in ("restart", "day"):
            start = now - timedelta(days=(day or 1) - 1)
            con.execute("""UPDATE season_state SET planned_start_utc=?,started_at_utc=?,
                paused_at_utc=NULL,paused_seconds=0,finalized_at_utc=NULL,
                qa_extension_seconds=0 WHERE season_key=?""",
                        (_timestamp(start), _timestamp(start), QA_SEASON))
        elif action == "extend":
            if old.started_at is None:
                raise ValueError("Start the QA event before extending it")
            elapsed = max(0, int((old.effective_now(now) - old.started_at).total_seconds()))
            # An already expired event receives the full requested extra time
            # from now. Days remain capped at 7; no new scoring day is invented.
            extension = max(old.qa_extension_seconds, elapsed - 7 * 86400 + 1)
            extension += extension_days * 86400
            if extension > 2_000_000_000:
                raise ValueError("QA extension exceeds supported duration")
            con.execute("UPDATE season_state SET qa_extension_seconds=? WHERE season_key=?",
                        (extension, QA_SEASON))
        updated = store._make_season(con.execute(
            "SELECT * FROM season_state WHERE season_key=?", (QA_SEASON,)).fetchone())
        result = {"action": action, "event": _snapshot(updated, now),
                  "gameplay_reset": action in ("restart", "reset"),
                  "accounts_preserved": True}
        Store._audit(con, QA_SEASON, actor_id, 0, "qa_lifecycle:" + action,
                     reason, now, before, {"request_id": request_id,
                                          "request": signature, "result": result})
    return {"scope": "ISOLATED_QA_ONLY", "replayed": False, **result}
