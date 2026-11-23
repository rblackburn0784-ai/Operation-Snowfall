"""Read-only community bulletin; no Discord message ingestion or player identities."""
from dataclasses import asdict
from datetime import datetime, timezone

from snowfall.db.store import CITIES
from snowfall.services.community import CommunityEngine, _objective
from snowfall.services.world import THEMES
from snowfall.services.territory import schedule_for_day


def community_view(game, now=None):
    now = now or datetime.now(timezone.utc)
    season, store = game.season, game.store
    state = store.season(season)
    if state is None:
        raise ValueError("Season not configured.")
    phase = state.phase(now)
    current = state.day(now)
    day = current or (CommunityEngine(store).latest_completed_day(season, now) or None)
    pairs = schedule_for_day(day) if day is not None else ()
    rivals = {a: b for a, b in pairs} | {b: a for a, b in pairs}
    cities, updates = [], []
    totals = dict(throws=0, hits=0, boss_damage=0, siege_damage=0,
                  quests=0, gifts=0, arcade=0)
    # Read existing records, never tick the world or create rewards from a GET.
    with store.connect() as con:
        con.execute("BEGIN")
        for city in CITIES:
            values = dict.fromkeys(totals, 0)
            members = con.execute("""SELECT COUNT(*) FROM players
                WHERE season_key=? AND city=? AND review_state NOT IN ('flagged','disqualified')""",
                (season, city)).fetchone()[0]
            objective = None
            if day is not None:
                objective = asdict(_objective(con, season, day, city, state.started_at))
                args = (season, day, city)
                eligible = " AND p.review_state NOT IN ('flagged','disqualified')"
                r = con.execute("""SELECT COUNT(*) n, COALESCE(SUM(c.hit),0) hits,
                    MAX(c.happened_at_utc) latest FROM combat_events c JOIN players p
                    ON p.season_key=c.season_key AND p.discord_user_id=c.attacker_id
                    WHERE c.season_key=? AND c.day=? AND p.city=?""" + eligible, args).fetchone()
                values["throws"], values["hits"] = int(r["n"]), int(r["hits"])
                if r["n"]:
                    updates.append({"city": city, "kind": "combat", "count": int(r["n"]),
                                    "unit": "snowball throws", "latest": r["latest"]})
                rows = con.execute("""SELECT e.kind, COALESCE(SUM(e.damage),0) damage,
                    COUNT(*) n, MAX(e.happened_at_utc) latest FROM pve_events e JOIN players p
                    ON p.season_key=e.season_key AND p.discord_user_id=e.attacker_id
                    WHERE e.season_key=? AND e.day=? AND p.city=? AND e.echo=0""" + eligible +
                    " GROUP BY e.kind", args).fetchall()
                for row in rows:
                    if row["kind"] in ("boss", "siege"):
                        key = row["kind"] + "_damage"
                        values[key] = int(row["damage"])
                        updates.append({"city": city, "kind": row["kind"], "count": int(row["damage"]),
                                        "unit": "damage", "latest": row["latest"]})
                for key, table, stamp, extra, unit in (
                    ("quests", "quest_claims", "claimed_at_utc", "", "assignments claimed"),
                    ("gifts", "mystery_gifts", "claimed_at_utc", "", "presents opened"),
                    ("arcade", "social_arcade_runs", "finished_at_utc",
                     " AND e.status='finished'", "arcade runs completed"),
                ):
                    r = con.execute(f"""SELECT COUNT(*) n, MAX(e.{stamp}) latest FROM {table} e
                        JOIN players p ON p.season_key=e.season_key AND p.discord_user_id=e.discord_user_id
                        WHERE e.season_key=? AND e.day=? AND p.city=?""" + extra + eligible,
                        args).fetchone()
                    values[key] = int(r["n"])
                    if r["n"]:
                        updates.append({"city": city, "kind": key, "count": int(r["n"]),
                                        "unit": unit, "latest": r["latest"]})
            for k, v in values.items():
                totals[k] += v
            cities.append({"city": city, "rival": rivals.get(city), "members": int(members),
                           "objective": objective, "activity": values})
    # Datetime objects or ISO strings are supported by the existing adapters.
    updates.sort(key=lambda row: str(row["latest"] or ""), reverse=True)
    # Expose aggregated updates, not individual action times or exact identities.
    for update in updates:
        update.pop("latest", None)
    return {"phase": phase, "day": day, "archived": phase in ("closed", "finalized"),
            "theme": THEMES[day-1] if day else "Awaiting kickoff",
            "server_time": now, "totals": totals, "cities": cities,
            "updates": updates[:18], "objectives_met": sum(bool(c["objective"] and
                c["objective"]["completed"]) for c in cities),
            "verified_only": True, "chat_relay": False}
