"""v2.9.5: Read-only shared-QA launch audit without player/secret disclosure.

The audit deliberately cannot start the seven-day event, update scores,
reset accounts, issue awards or change Railway. It only checks the isolated
Snowfall staging database's ownership marker, identities and game invariants.
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlsplit

from snowfall.platform.unified_discord import QA_SEASON, verify_qa_database


class ReadinessError(ValueError):
    """Fail closed rather than inspecting a non-QA database."""


def audit_qa_database(dsn: str) -> dict:
    """Return aggregate QA readiness counts; never expose player IDs or names."""
    parts = urlsplit(dsn)
    if parts.scheme not in ("postgres", "postgresql") or parts.path != "/snowfall_web_qa":
        raise ReadinessError("Only the isolated snowfall_web_qa database can be inspected")

    verify_qa_database(dsn, season=QA_SEASON)

    import psycopg
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        scalar = lambda query, params=(): int(conn.execute(query, params).fetchone()[0])
        active = scalar("""SELECT COUNT(*) FROM players WHERE season_key=%s
                           AND review_state!='disqualified'""", (QA_SEASON,))
        retired = scalar("""SELECT COUNT(*) FROM players WHERE season_key=%s
                            AND review_state='disqualified'""", (QA_SEASON,))
        connected = scalar("""SELECT COUNT(*) FROM players p
                WHERE p.season_key=%s AND p.review_state!='disqualified'
                  AND EXISTS(SELECT 1 FROM snowfall_identity_links d
                    WHERE d.provider='discord' AND d.player_id=p.discord_user_id)
                  AND EXISTS(SELECT 1 FROM snowfall_identity_links u
                    WHERE u.provider='underworld' AND u.player_id=p.discord_user_id)""",
                           (QA_SEASON,))
        # QA seed NPCs legitimately have no Underworld login and are reported
        # as a warning. Production migration cannot silently treat them as
        # eligible prize players.
        unlinked_fixture_players = scalar("""SELECT COUNT(*) FROM players p
                WHERE p.season_key=%s AND p.review_state!='disqualified'
                  AND NOT EXISTS(SELECT 1 FROM snowfall_identity_links u
                    WHERE u.provider='underworld' AND u.player_id=p.discord_user_id)""",
                                        (QA_SEASON,))
        orphan_principals = scalar("""SELECT COUNT(*) FROM players p
                LEFT JOIN snowfall_identity_principals ident
                  ON ident.player_id=p.discord_user_id
                WHERE p.season_key=%s AND p.review_state!='disqualified'
                  AND ident.player_id IS NULL""", (QA_SEASON,))
        prize_rows = scalar("SELECT COUNT(*) FROM prize_awards WHERE season_key=%s",
                            (QA_SEASON,))
        orphan_resources = scalar("""SELECT COUNT(*) FROM player_resources r
                LEFT JOIN players p ON p.discord_user_id=r.discord_user_id
                    AND p.season_key=r.season_key
                WHERE r.season_key=%s AND p.id IS NULL""", (QA_SEASON,))
        bad_resources = scalar("""SELECT COUNT(*) FROM player_resources
                 WHERE season_key=%s AND
                 (snowballs NOT BETWEEN 0 AND 12 OR warmth NOT BETWEEN 0 AND 100
                  OR snowflakes NOT BETWEEN 0 AND 100
                  OR armour_hp NOT BETWEEN 0 AND 25)""", (QA_SEASON,))
        events = {
            table: scalar("SELECT COUNT(*) FROM " + table + " WHERE season_key=%s",
                          (QA_SEASON,))
            for table in ("score_ledger", "combat_events", "pve_events", "item_events")
        }
        present = scalar("SELECT COUNT(*) FROM season_state WHERE season_key=%s",
                         (QA_SEASON,))

    blockers = []
    warnings = []
    if not present:
        blockers.append("Missing season configuration")
    if prize_rows:
        blockers.append("QA contains prize awards; manual review required")
    if orphan_resources:
        blockers.append("Orphaned resource rows")
    if bad_resources:
        blockers.append("Resource values outside game limits")
    if orphan_principals:
        # The fictional, pre-provisioned QA NPC pool may have no canonical
        # principal. It is not a production-ready player population.
        warnings.append("QA includes registered NPCs or legacy noncanonical players")
    if unlinked_fixture_players:
        warnings.append("QA includes Discord-only / fictional unlinked players")
    if not connected:
        warnings.append("No registered player has both Underworld and Discord linked")
    return {
        "scope": "ISOLATED_QA_ONLY",
        "season": QA_SEASON,
        "status": ("blocked" if blockers else
                   "ready_with_warnings" if warnings else "ready"),
        "active_players": active,
        "retired_players": retired,
        "linked_registered_players": connected,
        "unlinked_or_fixture_players": unlinked_fixture_players,
        "noncanonical_active_players": orphan_principals,
        "orphan_resources": orphan_resources,
        "bad_resources": bad_resources,
        "prize_awards": prize_rows,
        "event_counts": events,
        "blockers": blockers,
        "warnings": warnings,
        "launch_boundary": (
            "These checks cover the shared QA database only; a real event "
            "requires separate prize policy, moderation, load and disaster recovery signoff."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Snowfall QA database audit")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    if args.confirm != "READ_ONLY_QA_AUDIT":
        parser.error("Use --confirm READ_ONLY_QA_AUDIT to audit isolated QA")
    dsn = os.getenv("SNOWFALL_DATABASE_URL", "")
    try:
        result = audit_qa_database(dsn)
    except Exception:
        # Do not print psycopg exceptions: the connection DSN can contain a
        # credential and is never permitted in stdout/production logs.
        print(json.dumps({"status": "blocked", "error": "QA audit unavailable"}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
