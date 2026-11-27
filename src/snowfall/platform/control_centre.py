"""Read-only isolated-QA staff event control centre.

This module uses the authoritative game ledger and existing reconciliation.
It never issues prizes, edits scores, changes phases or advances world ticks.
Only the server-side, identity-verified staff route may call this projection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from snowfall.services.combat import CombatEngine
from snowfall.ops import reconcile


def _iso(dt):
    return dt.isoformat() if hasattr(dt, "isoformat") else dt


def control_centre_view(game, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    store, key = game.store, game.season
    season = store.season(key)
    phase = season.phase(now)
    day = season.day(now)
    if key != "web-qa-2026" and key != "qa":
        raise ValueError("Control centre is isolated QA only.")

    with store.connect() as con:
        def count(query, params=(key,)):
            return int(con.execute(query, params).fetchone()[0])

        players = [dict(r) for r in con.execute(
            """SELECT p.discord_user_id, p.mr_username, p.city, p.review_state,
               COALESCE(SUM(l.points),0) AS score
               FROM players p LEFT JOIN score_ledger l
                 ON l.season_key=p.season_key AND l.player_id=p.discord_user_id
               WHERE p.season_key=?
               GROUP BY p.id,p.season_key,p.discord_user_id,
                        p.mr_username,p.city,p.review_state
               ORDER BY score DESC,p.mr_username ASC LIMIT 60""", (key,)).fetchall()]
        # Prize exclusions apply to every registered player, not only the
        # first 60 characters in the visible staff registry.
        flagged_ids = {int(r[0]) for r in con.execute(
            """SELECT discord_user_id FROM players WHERE season_key=?
               AND review_state IN ('flagged','disqualified')""", (key,)).fetchall()}
        totals = {
            "players": count("SELECT COUNT(*) FROM players WHERE season_key=?"),
            "flagged": count("SELECT COUNT(*) FROM players WHERE season_key=? AND review_state='flagged'"),
            "disqualified": count("SELECT COUNT(*) FROM players WHERE season_key=? AND review_state='disqualified'"),
            "score_rows": count("SELECT COUNT(*) FROM score_ledger WHERE season_key=?"),
            "combat": count("SELECT COUNT(*) FROM combat_events WHERE season_key=?"),
            "boss_siege": count("SELECT COUNT(*) FROM pve_events WHERE season_key=?"),
            "claims": count("SELECT COUNT(*) FROM quest_claims WHERE season_key=?"),
            "arcade": count("SELECT COUNT(*) FROM social_arcade_runs WHERE season_key=? AND status='finished'"),
            "award_rows": count("SELECT COUNT(*) FROM prize_awards WHERE season_key=?"),
            "audit_rows": count("SELECT COUNT(*) FROM admin_audit WHERE season_key=?"),
            "unlinked": count("""SELECT COUNT(*) FROM players p
                WHERE p.season_key=? AND NOT EXISTS (
                  SELECT 1 FROM snowfall_identity_links u
                  WHERE u.player_id=p.discord_user_id AND u.provider='underworld')""")
                if getattr(store, "backend", "") == "postgres" else None,
            "invalid_balances": count("""SELECT COUNT(*) FROM player_resources
                WHERE season_key=? AND
                 (snowballs NOT BETWEEN 0 AND 12 OR warmth NOT BETWEEN 0 AND 100
                  OR snowflakes NOT BETWEEN 0 AND 100 OR armour_hp NOT BETWEEN 0 AND 25)"""),
        }
        days = [dict(r) for r in con.execute(
            """SELECT day, category, SUM(points) AS points,COUNT(*) AS entries
               FROM score_ledger WHERE season_key=?
               GROUP BY day,category ORDER BY day,category""", (key,)).fetchall()]
        audit = [dict(r) for r in con.execute(
            """SELECT action,reason,created_at_utc,subject_id,actor_id
               FROM admin_audit WHERE season_key=? ORDER BY id DESC LIMIT 20""",
            (key,)).fetchall()]
        boss = con.execute("""SELECT day,boss_initial_hp,boss_hp,theme
                             FROM world_days WHERE season_key=? AND day=?
                             """, (key, day or 0)).fetchone()
        sieges = [dict(r) for r in con.execute(
            """SELECT city,initial_hp,hp FROM world_sieges
               WHERE season_key=? AND day=? ORDER BY city""",
            (key, day or 0)).fetchall()]
        excess_arcade = count("""SELECT COUNT(*) FROM (
            SELECT discord_user_id,day,mode FROM social_arcade_runs
            WHERE season_key=? GROUP BY discord_user_id,day,mode
            HAVING COUNT(*)>3)""")
        recent = [dict(r) for r in con.execute(
            """SELECT p.mr_username,p.city,p.review_state,p.discord_user_id,
                      COALESCE(r.snowballs,0) AS snowballs,
                      COALESCE(r.warmth,0) AS warmth
               FROM players p LEFT JOIN player_resources r
               ON r.season_key=p.season_key AND r.discord_user_id=p.discord_user_id
               WHERE p.season_key=? AND p.review_state IN ('flagged','disqualified')
               ORDER BY p.joined_at_utc DESC LIMIT 25""", (key,)).fetchall()]
    # Canonical reconciliation and prize-sort order, not a second score engine.
    checked = reconcile(store, key)
    leaders = CombatEngine(store).leaderboard(key, limit=100)
    ineligible = flagged_ids
    preview = []
    for name, city, pid, points in leaders:
        if pid not in ineligible and int(points) > 0:
            preview.append({"place": len(preview) + 1, "name": name,
                            "city": city, "points": int(points),
                            "player_id": str(pid)})
        if len(preview) == 3:
            break
    risk = {
        "flagged_players": totals["flagged"],
        "invalid_balances": totals["invalid_balances"],
        "pvp_ledger_mismatches": len(checked["mismatched_combat_ids"]),
        "pvp_over_cap": len(checked["pvp_over_cap"]),
        "quest_over_cap": checked["quest_over_cap_count"],
        "quest_unbacked": checked["quest_unbacked_count"],
        "quest_missing": checked["quest_missing_count"],
        "defense_mismatches": checked["defense_mismatch_count"],
        "arcade_over_limit": excess_arcade,
    }
    for p in players:
        p["player_id"] = str(p.pop("discord_user_id"))
        p["score"] = int(p["score"])
    for p in recent:
        p["player_id"] = str(p.pop("discord_user_id"))
    for a in audit:
        a["actor_id"] = str(a["actor_id"])
        a["subject_id"] = str(a["subject_id"])
    return {
        "scope": "ISOLATED_QA_ONLY", "read_only": True,
        "official_prizes_enabled": False, "game_day": day, "phase": phase,
        "season": key, "server_time": _iso(now),
        "schedule": {
            "registration_opens": _iso(season.registration_opens()),
            "planned_start": _iso(season.planned_start),
            "started_at": _iso(season.started_at),
            "paused_at": _iso(season.paused_at),
            "projected_end": _iso(season.projected_end(now)),
            "pause_seconds": int(season.paused_seconds),
            "qa_extension_seconds": season.qa_extension_seconds,
        },
        "totals": totals, "risks": risk, "reconciliation_ok": checked["ok"],
        "days": days, "boss": dict(boss) if boss else None,
        "sieges": sieges, "players": players, "review_queue": recent,
        "audit": audit, "prize_preview": preview,
        "prize_policy": "Provisional individual top-three only. No allocations, exports or payouts; flagged/disqualified excluded; QA fixture identities still need verification.",
        "staff_actions": "This projection is read-only. Explicitly authorised hosts can use the separate shared QA lifecycle controls.",
    }
