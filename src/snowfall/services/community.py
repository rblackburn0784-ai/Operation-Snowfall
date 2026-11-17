"""Honorary city cooperation, rivalries and deterministic Snowfall Wire reporting.

All statistics derive from existing season-scoped, immutable event records.
No player points, snowflakes, prizes or city rankings are awarded here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import sqlite3

from snowfall.db.store import CITIES, Store, _timestamp
from snowfall.services.world import WorldEngine, THEMES


class CommunityError(ValueError):
    """Unregistered player, invalid day, or unpublished recap."""


@dataclass(frozen=True)
class CooperativeObjective:
    day: int
    name: str
    detail: str
    progress: int
    target: int
    unit: str
    completed: bool
    roster_scale: int


@dataclass(frozen=True)
class CityRivalry:
    opponent: str
    throws: int
    hits: int
    damage_dealt: int
    hits_received: int
    damage_received: int
    knockouts: int
    knockouts_received: int


@dataclass(frozen=True)
class CityHeadquarters:
    city: str
    day: int | None
    theme: str
    city_rank: int | None
    city_score_x100: int
    members: int
    participants_today: int
    city_wins: int
    siege_clears: int
    city_siege_hp: tuple[int, int] | None
    objective: CooperativeObjective | None
    leaders: tuple[tuple[str, int], ...]
    rivalries: tuple[CityRivalry, ...]
    is_practice: bool = False


@dataclass(frozen=True)
class WireReport:
    day: int
    theme: str
    top_player: str | None
    top_player_city: str | None
    top_points: int
    leading_city: str | None
    tied_cities: tuple[str, ...]
    city_score_x100: int
    players_scoring: int
    pvp_throws: int
    pvp_hits: int
    biggest_hit: int
    biggest_hitter: str | None
    boss_damage: int
    siege_clears: int
    quests: int
    gifts: int
    city_objectives_met: tuple[str, ...]
    fiercest_rivalry: tuple[str, str, int] | None


# Only cosmetic milestones; thresholds scale with a capped, fixed pre-day roster.
# The scale is computed at day kickoff so late registrations do not raise the goal.
DAILY_OBJECTIVES = {
    1: ("Opening Salvo", "Launch a city-wide snowball barrage", "throws", 2, "throws"),
    2: ("Fortress Breakers", "Chip away at a rival fortress together", "siege_damage", 12, "damage"),
    3: ("Whiteout Ambush", "Land successful throws as a city", "hits", 1, "hits"),
    4: ("Holiday Supply Run", "Open mystery presents across your city", "gifts", 1, "presents"),
    5: ("Don's Downfall", "Pile damage onto the shared Snow Don", "boss_damage", 12, "damage"),
    6: ("Blizzard Brigade", "Coordinate Snow Don and siege attacks", "pve", 2, "attacks"),
    7: ("The Final Push", "Claim your last daily quest rewards", "quests", 1, "quests"),
}


def _one(con: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    return int(con.execute(query, params).fetchone()[0] or 0)


def _city_progress(con: sqlite3.Connection, season: str, city: str, day: int,
                   key: str) -> int:
    if key in ("throws", "hits"):
        column = "COUNT(*)" if key == "throws" else "COALESCE(SUM(c.hit),0)"
        return _one(con, f"""SELECT {column} FROM combat_events c
            JOIN players p ON p.season_key=c.season_key
                AND p.discord_user_id=c.attacker_id
            WHERE c.season_key=? AND c.day=? AND p.city=?
                AND p.review_state NOT IN ('flagged','disqualified')""",
            (season, day, city))
    if key == "gifts":
        return _one(con, """SELECT COUNT(*) FROM mystery_gifts m
            JOIN players p ON p.season_key=m.season_key
                AND p.discord_user_id=m.discord_user_id
            WHERE m.season_key=? AND m.day=? AND p.city=?
                AND p.review_state NOT IN ('flagged','disqualified')""",
            (season, day, city))
    if key == "quests":
        return _one(con, """SELECT COUNT(*) FROM quest_claims q
            JOIN players p ON p.season_key=q.season_key
                AND p.discord_user_id=q.discord_user_id
            WHERE q.season_key=? AND q.day=? AND p.city=?
                AND p.review_state NOT IN ('flagged','disqualified')""",
            (season, day, city))
    if key in ("siege_damage", "boss_damage", "pve"):
        aggregate = "COUNT(*)" if key == "pve" else "COALESCE(SUM(e.damage),0)"
        kind = "" if key == "pve" else " AND e.kind=?"
        echo_filter = "" if key == "pve" else " AND e.echo=0"
        params = ((season, day, city) if key == "pve" else
                  (season, day, city, "siege" if key == "siege_damage" else "boss"))
        # Match the PvP/quest/gift eligibility rules: review-flagged accounts
        # cannot contribute to cooperative milestones through PvE either.
        return _one(con, f"""SELECT {aggregate} FROM pve_events e
            JOIN players p ON p.season_key=e.season_key
              AND p.discord_user_id=e.attacker_id
            WHERE e.season_key=? AND e.day=? AND e.city=?
              AND p.review_state NOT IN ('flagged','disqualified')
              {echo_filter}{kind}""", params)
    raise CommunityError("Unknown community objective")


def _objective(con: sqlite3.Connection, season: str, day: int, city: str,
               started_at: datetime) -> CooperativeObjective:
    if day not in DAILY_OBJECTIVES or city not in CITIES:
        raise CommunityError("Invalid city or day")
    name, detail, key, multiplier, unit = DAILY_OBJECTIVES[day]
    row = con.execute("""SELECT effective_start_utc FROM world_days
                         WHERE season_key=? AND day=?""", (season, day)).fetchone()
    if row:
        started_text = row[0]
    else:
        started_text = _timestamp(started_at + timedelta(days=day-1))
    roster = _one(con, """SELECT COUNT(*) FROM players WHERE season_key=? AND city=?
        AND joined_at_utc<=? AND review_state NOT IN ('flagged','disqualified')""",
        (season, city, started_text))
    scale = min(5, max(1, roster))
    target = multiplier * scale
    progress = _city_progress(con, season, city, day, key)
    return CooperativeObjective(day, name, detail, progress, target, unit,
                                progress >= target, scale)


def _rivalries(con: sqlite3.Connection, season: str, city: str,
              day: int | None) -> tuple[CityRivalry, ...]:
    if city not in CITIES:
        raise CommunityError("Invalid city")
    day_clause = " AND c.day=?" if day is not None else ""
    rows = con.execute(f"""SELECT c.target_city, COUNT(*) throws,
                SUM(c.hit) hits,
                SUM(c.warmth_damage+c.armour_damage) damage,
                SUM(c.knocked_out) kos
            FROM combat_events c JOIN players p ON p.season_key=c.season_key
                AND p.discord_user_id=c.attacker_id
            WHERE c.season_key=? AND p.city=?
                AND p.review_state NOT IN ('flagged','disqualified') {day_clause}
            GROUP BY c.target_city""",
            (season, city, day) if day is not None else (season, city)).fetchall()
    outgoing = {r["target_city"]: r for r in rows}
    rows = con.execute(f"""SELECT p.city attacker_city, SUM(c.hit) hits,
                SUM(c.warmth_damage+c.armour_damage) damage,
                SUM(c.knocked_out) kos
            FROM combat_events c JOIN players p ON p.season_key=c.season_key
                AND p.discord_user_id=c.attacker_id
            WHERE c.season_key=? AND c.target_city=?
                AND p.review_state NOT IN ('flagged','disqualified') {day_clause}
            GROUP BY p.city""",
            (season, city, day) if day is not None else (season, city)).fetchall()
    incoming = {r["attacker_city"]: r for r in rows}
    return tuple(CityRivalry(
        opponent=enemy,
        throws=int(outgoing[enemy]["throws"] or 0) if enemy in outgoing else 0,
        hits=int(outgoing[enemy]["hits"] or 0) if enemy in outgoing else 0,
        damage_dealt=int(outgoing[enemy]["damage"] or 0) if enemy in outgoing else 0,
        hits_received=int(incoming[enemy]["hits"] or 0) if enemy in incoming else 0,
        damage_received=int(incoming[enemy]["damage"] or 0) if enemy in incoming else 0,
        knockouts=int(outgoing[enemy]["kos"] or 0) if enemy in outgoing else 0,
        knockouts_received=int(incoming[enemy]["kos"] or 0) if enemy in incoming else 0,
    ) for enemy in CITIES if enemy != city)


class CommunityEngine:
    def __init__(self, store: Store):
        self.store = store

    def headquarters(self, season: str, user_id: int, now: datetime) -> CityHeadquarters:
        player = self.store.get_player(season, user_id)
        if player is None:
            raise CommunityError("Register first using My Player → Join / Register.")
        state = self.store.season(season)
        day = state.day(now)
        standings = (WorldEngine(self.store).standings(season, now)
                     if state.started_at is not None else [])
        city = player.city
        city_standing = next((s for s in standings if s.city == city), None)
        rank = next((i for i, s in enumerate(standings, 1)
                     if s.city == city and s.score_x100 > 0), None)
        with self.store.connect() as con:
            members = _one(con, """SELECT COUNT(*) FROM players
                WHERE season_key=? AND city=?
                AND review_state NOT IN ('flagged','disqualified')""", (season, city))
            if day is None:
                objective, active, top, hp = None, 0, (), None
            else:
                objective = _objective(con, season, day, city, state.started_at)
                active = _one(con, """SELECT COUNT(DISTINCT player_id) FROM score_ledger l
                    JOIN players p ON p.season_key=l.season_key AND p.discord_user_id=l.player_id
                    WHERE l.season_key=? AND l.day=? AND p.city=? AND l.points>0
                        AND p.review_state NOT IN ('flagged','disqualified')""", (season, day, city))
                rows = con.execute("""SELECT p.mr_username, SUM(l.points) score
                    FROM score_ledger l JOIN players p
                    ON p.season_key=l.season_key AND p.discord_user_id=l.player_id
                    WHERE l.season_key=? AND l.day=? AND p.city=?
                        AND p.review_state NOT IN ('flagged','disqualified')
                    GROUP BY l.player_id HAVING SUM(l.points)>0
                    ORDER BY score DESC,p.mr_username_norm ASC LIMIT 5""",
                    (season, day, city)).fetchall()
                top = tuple((r[0], int(r[1])) for r in rows)
                siege = con.execute("""SELECT hp,initial_hp FROM world_sieges
                    WHERE season_key=? AND day=? AND city=?""", (season, day, city)).fetchone()
                hp = (int(siege[0]), int(siege[1])) if siege else None
            rivalry = _rivalries(con, season, city, None)
        return CityHeadquarters(
            city=city, day=day, theme=THEMES[day-1] if day else "Awaiting kickoff",
            city_rank=rank, city_score_x100=city_standing.score_x100 if city_standing else 0,
            members=members, participants_today=active,
            city_wins=city_standing.daily_wins if city_standing else 0,
            siege_clears=city_standing.siege_clears if city_standing else 0,
            city_siege_hp=hp, objective=objective, leaders=top,
            rivalries=rivalry,
        )

    def rivalry_summary(self, season: str, user_id: int,
                        *, day: int | None = None) -> tuple[CityRivalry, ...]:
        player = self.store.get_player(season, user_id)
        if player is None:
            raise CommunityError("Register first using My Player → Join / Register.")
        if day is not None and not 1 <= day <= 7:
            raise CommunityError("Day must be 1–7")
        with self.store.connect() as con:
            return _rivalries(con, season, player.city, day)

    def recap(self, season: str, day: int, now: datetime) -> WireReport:
        if not 1 <= day <= 7:
            raise CommunityError("Day must be between 1 and 7")
        state = self.store.season(season)
        if state.started_at is None or state.effective_now(now) < state.started_at + timedelta(days=day):
            raise CommunityError("The day is not complete yet; its results are not final.")
        # The same world engine that locks official city results at rollover.
        WorldEngine(self.store).tick(season, now)
        with self.store.connect() as con:
            player = con.execute("""SELECT p.mr_username,p.city,SUM(l.points) score
                FROM score_ledger l JOIN players p ON p.season_key=l.season_key
                    AND p.discord_user_id=l.player_id
                WHERE l.season_key=? AND l.day=? AND p.review_state NOT IN ('flagged','disqualified')
                GROUP BY l.player_id HAVING SUM(l.points)>0
                ORDER BY score DESC, p.mr_username_norm ASC LIMIT 1""",
                (season, day)).fetchone()
            cities = con.execute("""SELECT city,score_x100 FROM city_day_snapshots
                WHERE season_key=? AND day=? AND qualified=1 AND score_x100>0
                ORDER BY score_x100 DESC,city ASC""", (season, day)).fetchall()
            top_score = int(cities[0]["score_x100"]) if cities else 0
            tied = tuple(r["city"] for r in cities if r["score_x100"] == top_score)
            participants = _one(con, """SELECT COUNT(DISTINCT l.player_id)
                FROM score_ledger l JOIN players p ON p.season_key=l.season_key
                    AND p.discord_user_id=l.player_id
                WHERE l.season_key=? AND l.day=? AND l.points>0
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season, day))
            pvp_throws, pvp_hits, best_hit = con.execute("""SELECT COUNT(*),
                COALESCE(SUM(hit),0), COALESCE(MAX(warmth_damage+armour_damage),0)
                FROM combat_events WHERE season_key=? AND day=?""", (season, day)).fetchone()
            best = con.execute("""SELECT p.mr_username FROM combat_events c JOIN players p
                ON p.season_key=c.season_key AND p.discord_user_id=c.attacker_id
                WHERE c.season_key=? AND c.day=? AND (c.warmth_damage+c.armour_damage)=?
                ORDER BY c.happened_at_utc ASC,c.id ASC LIMIT 1""",
                (season, day, best_hit)).fetchone() if best_hit else None
            damage = _one(con, """SELECT COALESCE(SUM(damage),0) FROM pve_events
                WHERE season_key=? AND day=? AND kind='boss' AND echo=0""", (season, day))
            clears = _one(con, """SELECT COUNT(*) FROM world_sieges
                WHERE season_key=? AND day=? AND cleared_at_utc IS NOT NULL""", (season, day))
            quests = _one(con, "SELECT COUNT(*) FROM quest_claims WHERE season_key=? AND day=?",
                          (season, day))
            gifts = _one(con, "SELECT COUNT(*) FROM mystery_gifts WHERE season_key=? AND day=?",
                         (season, day))
            completed = tuple(city for city in CITIES
                              if _objective(con, season, day, city, state.started_at).completed)
            matchup = con.execute("""SELECT CASE WHEN p.city<c.target_city THEN p.city ELSE c.target_city END as a,
                      CASE WHEN p.city<c.target_city THEN c.target_city ELSE p.city END as b,
                      COUNT(*) as n FROM combat_events c JOIN players p
                      ON p.season_key=c.season_key AND p.discord_user_id=c.attacker_id
                      WHERE c.season_key=? AND c.day=? AND p.city!=c.target_city
                      GROUP BY a,b ORDER BY n DESC,a ASC,b ASC LIMIT 1""",
                      (season, day)).fetchone()
        return WireReport(day, THEMES[day-1],
                          player[0] if player else None, player[1] if player else None,
                          int(player[2]) if player else 0,
                          cities[0]["city"] if cities else None, tied, top_score,
                          participants, int(pvp_throws), int(pvp_hits), int(best_hit),
                          best[0] if best else None, damage, clears, quests, gifts, completed,
                          (matchup[0], matchup[1], int(matchup[2])) if matchup else None)

    def latest_completed_day(self, season: str, now: datetime) -> int:
        state = self.store.season(season)
        if state.started_at is None:
            return 0
        elapsed = state.effective_now(now) - state.started_at
        return max(0, min(7, int(elapsed.total_seconds() // 86400)))


def _safe_name(value: str | None, limit: int = 32) -> str:
    """Keep self-declared names from injecting mentions, Markdown or extra lines."""
    name = " ".join(str(value or "Unknown").split())[:limit]
    for char in "\\*_~`<>|@":
        name = name.replace(char, "")
    return name or "Unknown"


def wire_story(report: WireReport, *, practice: bool = False) -> str:
    """A factual, deterministic noir recap; no invented events or player names."""
    header = ("🧪 **TEST WIRE — NO PRIZES**" if practice else
              "🗞️ **THE SNOWFALL WIRE**")
    story = [header, f"**DAY {report.day}/7 | {report.theme}**",
             "*America's coldest underworld dispatch.*", ""]
    if report.top_player:
        story.append(f"🏆 **TOP OF THE RACKET:** {_safe_name(report.top_player)} "
                     f"({_safe_name(report.top_player_city)}) collected "
                     f"**{report.top_points} points** during Day {report.day}.")
    else:
        story.append("🏆 **TOP OF THE RACKET:** No scoring players to report.")
    if report.leading_city:
        champion = ", ".join(report.tied_cities)
        story.append(f"🏙️ **CITY BUSINESS:** {champion} "
                     f"{'are tied for' if len(report.tied_cities)>1 else 'leads'} "
                     f"Day {report.day} with {report.city_score_x100 / 100:.2f} "
                     "honorary standings points. No city prizes.")
    else:
        story.append("🏙️ **CITY BUSINESS:** No city qualified for the day's standings.")
    story.append(f"❄️ **STREETS REPORT:** {report.players_scoring} scorers, "
                 f"{report.pvp_throws} throws, {report.pvp_hits} hits. "
                 f"The largest single strike dealt {report.biggest_hit} damage"
                 + (f" (by {_safe_name(report.biggest_hitter)})" if report.biggest_hitter else "") + ".")
    story.append(f"☃️ **SNOW DON & SIEGES:** {report.boss_damage} boss damage "
                 f"and {report.siege_clears} city fortresses cleared.")
    story.append(f"🎁 **ON THE SIDE:** {report.quests} quests claimed; "
                 f"{report.gifts} mystery presents opened.")
    if report.fiercest_rivalry:
        a, b, attempts = report.fiercest_rivalry
        story.append(f"🎯 **THE HOTTEST FEUD:** {a} vs {b} — "
                     f"{attempts} snowballs exchanged on the streets.")
    if report.city_objectives_met:
        story.append("🤝 **COOPERATIVE HONOURS:** "
                     + ", ".join(report.city_objectives_met) + " completed their city missions.")
    else:
        story.append("🤝 **COOPERATIVE HONOURS:** No city completed its side mission.")
    story.append("*The Wire reports logged game events, not real-world incidents. "
                 "All prizes remain individual-only.*")
    return "\n".join(story)
