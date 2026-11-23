"""v2.9.8f staff player inspection and tightly gated QA review operations.

All reads are season-scoped. Review writes modify only the pre-existing review
state and append to the canonical staff audit; never touch score or prize data.
There are deliberately no lifecycle, resource, identity-link or prize mutations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from snowfall.db.store import CITIES, Store


QA_SEASON = "web-qa-2026"
REVIEW_STATES = ("self_declared", "cleared", "flagged", "disqualified")
REVIEW_ACTIONS = {"flag": ("flagged", "FLAG QA PLAYER"),
                  "clear": ("cleared", "CLEAR QA PLAYER")}


def _qa(game):
    if game is None or game.season != QA_SEASON:
        raise ValueError("Staff operations are restricted to isolated QA")


def _link_status(store, con, player_id):
    # The identity table is attached only to the shared PostgreSQL backend.
    # Return providers, not their confidential account/character subjects.
    if getattr(store, "backend", "") != "postgres":
        return {"underworld": None, "discord": None}
    rows = con.execute(
        "SELECT provider FROM snowfall_identity_links WHERE player_id=?",
        (player_id,)).fetchall()
    providers = {r[0] for r in rows}
    return {"underworld": "underworld" in providers,
            "discord": "discord" in providers}


def player_directory(game, *, query="", city="all", state="all", page=1):
    _qa(game)
    query = query.strip()
    if len(query) > 60 or page < 1 or page > 100:
        raise ValueError("Invalid search length or page")
    if city != "all" and city not in CITIES:
        raise ValueError("Invalid city")
    if state != "all" and state not in REVIEW_STATES:
        raise ValueError("Invalid review filter")
    # Escape LIKE wildcards: staff are searching a literal name, never SQL.
    like = "%" + query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = ["p.season_key=?"]
    args = [game.season]
    if query:
        where.append("(LOWER(p.mr_username) LIKE ? ESCAPE '\\' OR CAST(p.discord_user_id AS TEXT)=?)")
        args.extend([like, query])
    if city != "all":
        where.append("p.city=?")
        args.append(city)
    if state != "all":
        where.append("p.review_state=?")
        args.append(state)
    filters = " AND ".join(where)
    with game.store.connect() as con:
        total = int(con.execute("SELECT COUNT(*) FROM players p WHERE " + filters,
                                tuple(args)).fetchone()[0])
        rows = con.execute(
            """SELECT p.discord_user_id,p.mr_username,p.city,p.review_state,
                      p.joined_at_utc,COALESCE(SUM(l.points),0) AS score
               FROM players p LEFT JOIN score_ledger l
                 ON l.season_key=p.season_key AND l.player_id=p.discord_user_id
               WHERE """ + filters + """
               GROUP BY p.id,p.discord_user_id,p.mr_username,p.city,
                        p.review_state,p.joined_at_utc
               ORDER BY score DESC,p.mr_username ASC
               LIMIT 25 OFFSET ?""", tuple(args + [(page-1)*25])).fetchall()
    return {
        "scope": "ISOLATED_QA_ONLY", "read_only": True,
        "page": page, "page_size": 25, "total": total,
        "has_more": page * 25 < total,
        "players": [{"player_id": str(r["discord_user_id"]),
                     "mr_username": r["mr_username"], "city": r["city"],
                     "review_state": r["review_state"], "score": int(r["score"]),
                     "joined_at": r["joined_at_utc"]} for r in rows],
    }


def player_dossier(game, player_id: int):
    _qa(game)
    if player_id <= 0:
        raise ValueError("Invalid player ID")
    store, season = game.store, game.season
    with store.connect() as con:
        row = con.execute(
            """SELECT p.discord_user_id,p.mr_username,p.city,p.review_state,
                      p.joined_at_utc,r.snowballs,r.warmth,r.snowflakes,
                      r.armour_hp,r.last_throw_at,r.last_scored_action_at,
                      COALESCE((SELECT SUM(points) FROM score_ledger l
                        WHERE l.season_key=p.season_key
                          AND l.player_id=p.discord_user_id),0) AS score
               FROM players p LEFT JOIN player_resources r
                ON r.season_key=p.season_key AND r.discord_user_id=p.discord_user_id
               WHERE p.season_key=? AND p.discord_user_id=?""",
            (season, player_id)).fetchone()
        if row is None:
            raise ValueError("Player is not registered in this QA event")
        profile = dict(row)
        profile["player_id"] = str(profile.pop("discord_user_id"))
        profile["score"] = int(profile["score"])
        links = _link_status(store, con, player_id)
        scores = [dict(r) for r in con.execute(
            """SELECT day,category,points,created_at_utc FROM score_ledger
               WHERE season_key=? AND player_id=?
               ORDER BY id DESC LIMIT 30""", (season, player_id)).fetchall()]
        combat = [dict(r) for r in con.execute(
            """SELECT day,attacker_id,target_id,style,hit,critical,points_awarded,
                      happened_at_utc FROM combat_events
               WHERE season_key=? AND (attacker_id=? OR target_id=?)
               ORDER BY id DESC LIMIT 15""",
            (season, player_id, player_id)).fetchall()]
        pve = [dict(r) for r in con.execute(
            """SELECT day,kind,hit,damage,points_awarded,echo,final_blow,
                      happened_at_utc FROM pve_events
               WHERE season_key=? AND attacker_id=?
               ORDER BY happened_at_utc DESC LIMIT 15""",
            (season, player_id)).fetchall()]
        history = [dict(r) for r in con.execute(
            """SELECT actor_id,action,reason,created_at_utc FROM admin_audit
               WHERE season_key=? AND subject_id=?
               ORDER BY id DESC LIMIT 20""", (season, player_id)).fetchall()]
        for r in history:
            r["actor_id"] = str(r["actor_id"])
        overcap = int(con.execute(
            """SELECT COUNT(*) FROM (SELECT day FROM score_ledger
               WHERE season_key=? AND player_id=?
                 AND category IN ('pvp','defense')
               GROUP BY day HAVING SUM(points)>300) c""",
            (season, player_id)).fetchone()[0])
        mismatches = int(con.execute(
            """SELECT COUNT(*) FROM combat_events c WHERE c.season_key=?
               AND c.attacker_id=? AND c.points_awarded<>COALESCE(
                 (SELECT SUM(l.points) FROM score_ledger l
                  WHERE l.season_key=c.season_key
                    AND l.player_id=c.attacker_id AND l.category='pvp'
                    AND l.source_key='combat:' || c.interaction_id),0)""",
            (season, player_id)).fetchone()[0])
    alerts = []
    if profile["review_state"] in ("flagged", "disqualified"):
        alerts.append("Account currently requires staff review")
    resources = ("snowballs", "warmth", "snowflakes", "armour_hp")
    limits = ((0, 12), (0, 100), (0, 100), (0, 25))
    if any(profile[k] is not None and not lo <= int(profile[k]) <= hi
           for k, (lo, hi) in zip(resources, limits)):
        alerts.append("Resource balance outside expected bounds")
    if overcap:
        alerts.append(f"PvP/defence ledger exceeds 300 points on {overcap} day(s)")
    if mismatches:
        alerts.append(f"{mismatches} PvP action(s) do not reconcile with ledger")
    return {
        "scope": "ISOLATED_QA_ONLY", "read_only": True,
        "profile": profile, "links": links,
        "alerts": alerts, "over_cap_days": overcap,
        "combat_mismatches": mismatches,
        "score_history": scores, "combat_history": combat,
        "pve_history": pve, "review_history": history,
        "note": "Signals are review leads, not findings of misconduct.",
    }


def apply_player_review(game, *, actor_id: int, player_id: int, action: str,
                        expected_state: str, confirmation: str, reason: str,
                        request_id: str, now=None):
    _qa(game)
    if action not in REVIEW_ACTIONS or expected_state not in REVIEW_STATES:
        raise ValueError("Unsupported review action or previous state")
    target, phrase = REVIEW_ACTIONS[action]
    if confirmation != phrase:
        raise ValueError("Typed confirmation does not match")
    if not 12 <= len(reason.strip()) <= 220:
        raise ValueError("Review reason must contain 12–220 characters")
    if player_id <= 0 or actor_id <= 0 or actor_id == player_id:
        raise ValueError("Invalid target or self-review")
    now = now or datetime.now(timezone.utc)
    with game.store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        # Retain idempotency markers in the existing append-only audit, so a
        # retry after a web worker restart cannot reverse an intervening review.
        prior = con.execute(
            """SELECT subject_id,action,after_json FROM admin_audit
               WHERE season_key=? AND actor_id=? AND action IN
               ('identity_review:flagged','identity_review:cleared')
               ORDER BY id DESC""", (game.season, actor_id)).fetchall()
        for item in prior:
            try:
                metadata = json.loads(item["after_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if metadata.get("request_id") == request_id:
                if int(item["subject_id"]) != player_id or item["action"] != "identity_review:" + target:
                    raise ValueError("Request ID was already used for a different action")
                return {"scope": "ISOLATED_QA_ONLY", "player_id": str(player_id),
                        "review_state": target, "replayed": True, "audit_written": False}
        ended = con.execute(
            "SELECT finalized_at_utc FROM season_state WHERE season_key=?",
            (game.season,)).fetchone()
        if ended is None or ended["finalized_at_utc"] is not None:
            raise ValueError("Review changes are disabled for finalized or missing seasons")
        player = con.execute(
            "SELECT review_state FROM players WHERE season_key=? AND discord_user_id=?",
            (game.season, player_id)).fetchone()
        if player is None:
            raise ValueError("Unknown registered QA player")
        old = player["review_state"]
        if old == "disqualified":
            raise ValueError("Disqualified players require separate staff handling")
        if old != expected_state:
            raise ValueError("Player review state changed: refresh the dossier before continuing")
        if old == target:
            raise ValueError("Player is already in that review state")
        con.execute(
            "UPDATE players SET review_state=? WHERE season_key=? AND discord_user_id=?",
            (target, game.season, player_id))
        Store._audit(con, game.season, actor_id, player_id,
                     "identity_review:" + target, reason.strip(), now,
                     {"review_state": old},
                     {"review_state": target, "request_id": request_id})
    return {"scope": "ISOLATED_QA_ONLY", "player_id": str(player_id),
            "review_state": target, "replayed": False, "audit_written": True}
