"""v2.9.9h: read-only, fail-closed five-game Arcade 2.0 QA preflight.

Run only after the guarded migrations on /snowfall_web_qa. This checks
database ownership, account linking, isolated session/action schemas, index
integrity and risk indicators without writing, resetting or starting play.
No SQL exception, URL, credential or player identity is printed on failure.
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlsplit

from snowfall.platform.arcade_hub import GAMES
from snowfall.platform.launch_audit import audit_qa_database
from snowfall.platform.staging import QA_DB, require_staging
from snowfall.platform.unified_discord import QA_SEASON, verify_qa_database

PRACTICE_FLAG = "SNOWFALL_ARCADE_V299_ENABLED"
HUB_FLAG = "SNOWFALL_ARCADE_V299F_ENABLED"
QA_TABLES = {
    "gallery": ("web_arcade_gallery_sessions", "web_arcade_gallery_shots",
                "idx_web_gallery_active"),
    "safe": ("web_arcade_safe_sessions", "web_arcade_safe_actions",
             "idx_web_safe_active"),
    "snowman": ("web_arcade_snowman_sessions", "web_arcade_snowman_actions",
                "idx_web_snowman_active"),
    "catch": ("web_arcade_catch_sessions", "web_arcade_catch_actions",
              "idx_web_catch_active"),
    "trivia": ("web_arcade_trivia_sessions", "web_arcade_trivia_answers",
               "idx_web_trivia_active"),
}
CLASSIC_TABLE = "web_arcade_practice_sessions"


class ArcadeReadinessError(ValueError):
    """Misconfigured QA boundary, schema or ownership; no secrets in messages."""


def safe_qa_dsn(dsn: str, season: str) -> None:
    """Reject production URLs and wrong season before opening any connection."""
    try:
        url = urlsplit(dsn)
        good = (url.scheme in ("postgres", "postgresql") and
                url.hostname and url.path == "/" + QA_DB and
                not url.fragment and season == QA_SEASON)
    except (TypeError, ValueError):
        good = False
    if not good:
        raise ArcadeReadinessError("Arcade preflight restricted to isolated QA database/season")


def required_tables(env: dict) -> tuple[str, ...]:
    """Only enabled modes require their schema; Hub may display locked games."""
    selected = [
        mode for mode, _name, _desc, _skill, _duration, flag, _table, _ms in GAMES
        if env.get(flag) == "1"
    ]
    return tuple(selected)


def _table_info(con, table: str) -> dict:
    # Identifiers come only from QA_TABLES literals above.
    present = con.execute(
        "SELECT to_regclass(%s)", ("public." + table,)
    ).fetchone()[0] is not None
    if not present:
        return {"present": False, "sessions": 0, "active": 0,
                "finished": 0, "foreign_seasons": 0,
                "orphans": 0, "bad_scores": 0, "duplicate_active": 0}
    sessions = con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
    active = con.execute(
        "SELECT COUNT(*) FROM " + table + " WHERE status IN ('active','paused')"
    ).fetchone()[0]
    finished = con.execute(
        "SELECT COUNT(*) FROM " + table + " WHERE status='finished'"
    ).fetchone()[0]
    foreign = con.execute(
        "SELECT COUNT(*) FROM " + table + " WHERE season_key<>%s",
        (QA_SEASON,),
    ).fetchone()[0]
    orphan = con.execute(
        "SELECT COUNT(*) FROM " + table + " s "
        "LEFT JOIN players p ON p.season_key=s.season_key "
        "AND p.discord_user_id=s.player_id WHERE p.id IS NULL"
    ).fetchone()[0]
    scores = con.execute(
        "SELECT COUNT(*) FROM " + table +
        " WHERE score NOT BETWEEN 0 AND 100 "
        "OR status NOT IN ('active','paused','finished')"
    ).fetchone()[0]
    duplicates = con.execute(
        "SELECT COUNT(*) FROM (SELECT season_key,player_id,day "
        "FROM " + table + " WHERE status IN ('active','paused') "
        "GROUP BY season_key,player_id,day HAVING COUNT(*)>1) d"
    ).fetchone()[0]
    return {
        "present": True, "sessions": int(sessions), "active": int(active),
        "finished": int(finished), "foreign_seasons": int(foreign),
        "orphans": int(orphan), "bad_scores": int(scores),
        "duplicate_active": int(duplicates),
    }


def audit_arcade_qa(dsn: str, *, env=None, connect=None, baseline=None) -> dict:
    """Read-only QA inspection. Tests may inject a compatible connection.

    Real calls verify the signed QA database marker and account linking
    before running read-only queries. A caller cannot bypass safety checks
    by making the URL point to a different database or season.
    """
    env = dict(os.environ if env is None else env)
    safe_qa_dsn(dsn, env.get("SNOWFALL_API_SEASON_KEY", ""))
    real_database = connect is None
    if real_database:
        verify_qa_database(dsn, season=QA_SEASON)
        import psycopg

        def open_verified_qa():
            return psycopg.connect(dsn, connect_timeout=10)

        connect = open_verified_qa
    enabled = required_tables(env)
    blockers = []
    warnings = []
    modes = []
    with connect() as con:
        con.execute("SET TRANSACTION READ ONLY")
        if con.execute("SELECT to_regclass(%s)",
                       ("public.snowfall_web_qa_marker",)).fetchone()[0] is None:
            blockers.append("QA ownership marker unavailable")
        else:
            from snowfall.platform.staging import STAGING_PROJECT

            marker = con.execute(
                "SELECT project_id,season_key FROM snowfall_web_qa_marker "
                "WHERE singleton=1").fetchone()
            if marker is None or tuple(marker) != (STAGING_PROJECT, QA_SEASON):
                blockers.append("QA ownership marker does not match")

        for key, _label, _description, _skill, _time, flag, _table, _ms in GAMES:
            sessions, actions, index = QA_TABLES[key]
            detail = _table_info(con, sessions)
            have_actions = con.execute(
                "SELECT to_regclass(%s)", ("public." + actions,)
            ).fetchone()[0] is not None
            have_index = con.execute(
                "SELECT to_regclass(%s)", ("public." + index,)
            ).fetchone()[0] is not None
            fully_installed = detail["present"] and have_actions and have_index
            if key in enabled and not fully_installed:
                blockers.append(key + " enabled without complete QA schema")
            if detail["present"]:
                for reason, label in (
                    ("foreign_seasons", "unexpected season rows"),
                    ("orphans", "orphan player records"),
                    ("bad_scores", "invalid score/status"),
                    ("duplicate_active", "duplicate active sessions"),
                ):
                    if detail[reason]:
                        blockers.append(key + " has " + label)
            modes.append({
                "key": key, "enabled": key in enabled,
                "schema_ready": bool(fully_installed),
                "sessions": detail["sessions"], "active": detail["active"],
                "finished": detail["finished"],
            })
        if env.get(PRACTICE_FLAG) == "1":
            exists = con.execute("SELECT to_regclass(%s)",
                                 ("public." + CLASSIC_TABLE,)).fetchone()[0]
            if exists is None:
                blockers.append("legacy interactive practice enabled without QA schema")
    if baseline is None and real_database:
        baseline = audit_qa_database(dsn)
    if baseline is not None:
        if baseline.get("status") == "blocked":
            blockers.append("Base QA launch audit reports blockers")
        warnings.extend(baseline.get("warnings", []))
    if env.get(HUB_FLAG) == "1" and not enabled:
        warnings.append("Arcade Hub enabled but all five full modes are disabled")
    if not enabled and env.get(HUB_FLAG) != "1":
        warnings.append("All full game flags and Arcade Hub are disabled")
    return {
        "scope": "ISOLATED_QA_ONLY",
        "version": "2.9.9h",
        "season": QA_SEASON,
        "status": ("blocked" if blockers else
                   "ready_with_warnings" if warnings else "ready"),
        "enabled_modes": list(enabled),
        "hub_enabled": env.get(HUB_FLAG) == "1",
        "modes": modes,
        "blockers": blockers,
        "warnings": warnings,
        "release_boundary": "Code/QA inspection only; not Railway deployment or live approval.",
    }


def require_arcade_schema(dsn: str, *, env=None) -> None:
    """Fail staging web startup if any enabled full-game schema is missing."""
    env = dict(os.environ if env is None else env)
    if not required_tables(env) and env.get(PRACTICE_FLAG) != "1":
        return
    result = audit_arcade_qa(dsn, env=env)
    if result["status"] == "blocked":
        raise ArcadeReadinessError(
            "Arcade QA activation refused: protected preflight detected blockers")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only QA arcade release preflight")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    if args.confirm != "READ_ONLY_ARCADE_QA":
        parser.error("Use --confirm READ_ONLY_ARCADE_QA on isolated staging")
    env = dict(os.environ)
    try:
        require_staging(env)
        result = audit_arcade_qa(env.get("SNOWFALL_DATABASE_URL", ""), env=env)
    except Exception:
        # Never print URLs, DB credentials, raw exception text or player IDs.
        print(json.dumps({"scope": "ISOLATED_QA_ONLY", "status": "blocked",
                          "error": "Arcade QA preflight unavailable or unsafe"}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
