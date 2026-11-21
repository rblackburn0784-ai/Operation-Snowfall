"""Honorary six-city territory war: deterministic, season-scoped read models.

No database writes, new scoring categories, item grants or paid prizes.
Daily strongholds use existing city co-op missions. Daily frontiers award
display-only honours from qualified real events. Equal results stay neutral.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import sqlite3

from snowfall.core.clock import as_utc
from snowfall.db.store import CITIES, Store, _timestamp
from snowfall.services.community import _objective, _rivalries

# Original game-world districts, not claims about actual US city boundaries.
CITY_STYLE = {
    "Chicago": ("The Loop", "Gutter Saints", "#f07a74", "🎳"),
    "New York": ("Midnight Manhattan", "Empire Frost", "#85bafb", "🗽"),
    "Detroit": ("Motor Yard", "Steel Snow", "#c09bea", "⚙️"),
    "Philadelphia": ("Liberty Square", "Liberty Blizzard", "#edc479", "🔔"),
    "Las Vegas": ("Neon Boulevard", "Neon Icicles", "#e9a0d2", "🎲"),
    "Los Angeles": ("Sunset District", "West Coast Whiteout", "#84dcbb", "🌴"),
}
FRONTIERS = (
    ("North Frostline", "Midnight Crossing"),
    ("Icebound Exchange", "Winter Rail Yard"),
    ("Snowfall Boulevard", "Moonlit Docks"),
)


class TerritoryError(ValueError):
    """Invalid season, player or selected day."""


@dataclass(frozen=True)
class CityBanner:
    city: str
    home_district: str
    motto: str
    colour: str
    emblem: str
    registered: int
    active: int
    pve_hits: int
    quests: int
    rally_marks: int
    mission_name: str
    mission_progress: int
    mission_target: int
    mission_complete: bool
    stronghold_quorum: int


@dataclass(frozen=True)
class WarMatch:
    day: int
    slot: int
    city_a: str
    city_b: str
    rally_a: int
    rally_b: int
    hits_a: int
    hits_b: int
    throws_a: int
    throws_b: int
    damage_a: int
    damage_b: int
    kos_a: int
    kos_b: int
    rally_district: str
    duel_district: str
    rally_owner: str | None
    duel_owner: str | None

    def opponent(self, city: str) -> str | None:
        if city == self.city_a:
            return self.city_b
        if city == self.city_b:
            return self.city_a
        return None


@dataclass(frozen=True)
class TerritoryDistrict:
    key: str
    name: str
    kind: str
    owner: str | None
    contenders: tuple[str, ...]
    day: int


@dataclass(frozen=True)
class TerritoryMission:
    name: str
    description: str
    progress: int
    target: int
    complete: bool


@dataclass(frozen=True)
class TerritoryBoard:
    season_key: str
    day: int | None
    current_day: int | None
    phase: str
    viewer_city: str | None
    banners: tuple[CityBanner, ...]
    matches: tuple[WarMatch, ...]
    districts: tuple[TerritoryDistrict, ...]
    missions: tuple[TerritoryMission, ...]

    @property
    def contested(self) -> tuple[TerritoryDistrict, ...]:
        return tuple(d for d in self.districts if d.kind != "home")

    def banner(self, city: str) -> CityBanner:
        return next(b for b in self.banners if b.city == city)

    def match(self, city: str) -> WarMatch | None:
        return next((m for m in self.matches if m.opponent(city) is not None), None)

    def held(self, city: str) -> tuple[TerritoryDistrict, ...]:
        return tuple(d for d in self.districts if d.owner == city)

    @property
    def has_battles(self) -> bool:
        return self.day is not None


def schedule_for_day(day: int) -> tuple[tuple[str, str], ...]:
    """Five-round round-robin covers all 15 pairs, then two rematch rounds."""
    if not 1 <= day <= 7:
        raise TerritoryError("Day must be between 1 and 7.")
    rotation = list(CITIES)
    rounds = []
    for _ in range(5):
        rounds.append(tuple((rotation[i], rotation[-i-1]) for i in range(3)))
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    return rounds[(day-1) % 5]


def _winner(a: int, b: int, city_a: str, city_b: str) -> str | None:
    """Never manufacture victories from ties or zero participation."""
    if a == b:
        return None
    return city_a if a > b else city_b


def _dict_rows(con: sqlite3.Connection, query: str, params: tuple) -> list[sqlite3.Row]:
    return con.execute(query, params).fetchall()


def _daily_activity(con: sqlite3.Connection, season: str, day: int):
    """Only genuine, review-cleared actions can win honorary control."""
    active = {r["city"]: int(r["n"]) for r in _dict_rows(con, """
        SELECT p.city, COUNT(DISTINCT p.discord_user_id) n
        FROM score_ledger l JOIN players p ON p.season_key=l.season_key
          AND p.discord_user_id=l.player_id
        WHERE l.season_key=? AND l.day=? AND l.points>0
          AND p.review_state NOT IN ('flagged','disqualified')
        GROUP BY p.city""", (season, day))}
    pve = {r["city"]: int(r["n"]) for r in _dict_rows(con, """
        SELECT p.city, COUNT(*) n FROM pve_events e
        JOIN players p ON p.season_key=e.season_key
          AND p.discord_user_id=e.attacker_id
        WHERE e.season_key=? AND e.day=? AND e.hit=1 AND e.echo=0
          AND p.review_state NOT IN ('flagged','disqualified')
        GROUP BY p.city""", (season, day))}
    quests = {r["city"]: int(r["n"]) for r in _dict_rows(con, """
        SELECT p.city, COUNT(*) n FROM quest_claims q
        JOIN players p ON p.season_key=q.season_key
          AND p.discord_user_id=q.discord_user_id
        WHERE q.season_key=? AND q.day=?
          AND p.review_state NOT IN ('flagged','disqualified')
        GROUP BY p.city""", (season, day))}
    match_stats = {(r["attacker_city"], r["target_city"]): r
                   for r in _dict_rows(con, """
        SELECT a.city attacker_city, t.city target_city,
            COUNT(*) throws,
            COALESCE(SUM(CASE WHEN e.hit=1 AND e.points_awarded>0 THEN 1 ELSE 0 END),0) hits,
            COALESCE(SUM(CASE WHEN e.hit=1 AND e.points_awarded>0
                               THEN e.warmth_damage+e.armour_damage ELSE 0 END),0) damage,
            COALESCE(SUM(CASE WHEN e.hit=1 AND e.points_awarded>0
                               THEN e.knocked_out ELSE 0 END),0) kos
        FROM combat_events e
        JOIN players a ON a.season_key=e.season_key AND a.discord_user_id=e.attacker_id
        JOIN players t ON t.season_key=e.season_key AND t.discord_user_id=e.target_id
        WHERE e.season_key=? AND e.day=? AND a.city!=t.city
          AND a.review_state NOT IN ('flagged','disqualified')
          AND t.review_state NOT IN ('flagged','disqualified')
        GROUP BY a.city,t.city""", (season, day))}
    return active, pve, quests, match_stats


class TerritoryEngine:
    def __init__(self, store: Store):
        self.store = store

    def board(self, season: str, viewer: int, now: datetime,
              *, day: int | None = None) -> TerritoryBoard:
        if viewer is None:
            raise TerritoryError("Register first using /snow join.")
        return self._board(season, viewer, now, day=day)

    def public_board(self, season: str, now: datetime,
                     *, day: int | None = None) -> TerritoryBoard:
        """Read the same city aggregates without a player identity or personal missions."""
        return self._board(season, None, now, day=day)

    def _board(self, season: str, viewer: int | None, now: datetime,
               *, day: int | None = None) -> TerritoryBoard:
        state = self.store.season(season)
        if state is None:
            raise TerritoryError("Season is not configured.")
        phase = state.phase(as_utc(now))
        current = state.day(as_utc(now))
        if current is None and phase in ("closed", "finalized") and state.started_at:
            current = 7
        if day is not None and (not 1 <= day <= 7 or current is None or day > current):
            raise TerritoryError("That territory day is not available yet.")
        selected = day if day is not None else current
        with self.store.connect() as con:
            con.execute("BEGIN")  # Consistent multi-table snapshot; no writes.
            p = None
            if viewer is not None:
                p = con.execute("""SELECT city,review_state FROM players
                    WHERE season_key=? AND discord_user_id=?""", (season, viewer)).fetchone()
                if p is None:
                    raise TerritoryError("Register first using /snow join.")
                if p["review_state"] == "disqualified":
                    raise TerritoryError("Disqualified players cannot enter City Wars.")
            registered = {r["city"]: int(r["n"]) for r in con.execute("""
                SELECT city,COUNT(*) n FROM players WHERE season_key=?
                  AND review_state NOT IN ('flagged','disqualified') GROUP BY city
                """, (season,)).fetchall()}
            active, pve, quests, pvp = (
                _daily_activity(con, season, selected)
                if selected is not None else ({}, {}, {}, {}))
            # A review must not shrink the honorary crew quota retroactively.
            # Freeze the two-member maximum at the start of each event day.
            quorum = {city: 1 for city in CITIES}
            if selected is not None:
                day_row = con.execute(
                    "SELECT effective_start_utc FROM world_days "
                    "WHERE season_key=? AND day=?", (season, selected)).fetchone()
                cutoff = (day_row[0] if day_row is not None else
                          _timestamp(state.started_at + timedelta(days=selected-1)))
                original_roster = con.execute(
                    "SELECT city, COUNT(*) AS n FROM players WHERE season_key=? "
                    "AND joined_at_utc<=? GROUP BY city",
                    (season, cutoff)).fetchall()
                quorum.update({r["city"]: min(2, max(1, int(r["n"])))
                               for r in original_roster})
            city_banners = []
            for city in CITIES:
                home, motto, colour, emblem = CITY_STYLE[city]
                objective = _objective(con, season, selected, city, state.started_at) if (
                    selected is not None) else None
                active_n, pve_n, quest_n = (active.get(city, 0),
                                            pve.get(city, 0), quests.get(city, 0))
                # Team contribution rewards different legitimate behaviours.
                # This is display-only and is never inserted in score_ledger.
                marks = (4 * active_n + pve_n + quest_n
                         + (3 if objective and objective.completed else 0))
                city_banners.append(CityBanner(
                    city, home, motto, colour, emblem, registered.get(city, 0),
                    active_n, pve_n, quest_n, marks,
                    objective.name if objective else "Awaiting kickoff",
                    objective.progress if objective else 0,
                    objective.target if objective else 0,
                    bool(objective and objective.completed), quorum[city],
                ))
            banner_map = {b.city: b for b in city_banners}
            districts = [
                TerritoryDistrict(f"home:{c}", CITY_STYLE[c][0], "home",
                                  c if (banner_map[c].mission_complete and
                                        banner_map[c].active >= banner_map[c].stronghold_quorum)
                                  else None, (c,),
                                  selected or 0)
                for c in CITIES]
            matches = []
            if selected is not None:
                for slot, (a, b) in enumerate(schedule_for_day(selected)):
                    row_a = pvp.get((a, b))
                    row_b = pvp.get((b, a))
                    def metric(row, column):
                        return int(row[column] or 0) if row is not None else 0
                    rally_a, rally_b = banner_map[a].rally_marks, banner_map[b].rally_marks
                    hits_a, hits_b = metric(row_a, "hits"), metric(row_b, "hits")
                    rally_owner = _winner(rally_a, rally_b, a, b)
                    duel_owner = _winner(hits_a, hits_b, a, b)
                    rally_name, duel_name = FRONTIERS[slot]
                    matches.append(WarMatch(
                        selected, slot, a, b, rally_a, rally_b, hits_a, hits_b,
                        metric(row_a, "throws"), metric(row_b, "throws"),
                        metric(row_a, "damage"), metric(row_b, "damage"),
                        metric(row_a, "kos"), metric(row_b, "kos"),
                        rally_name, duel_name, rally_owner, duel_owner,
                    ))
                    districts.extend((
                        TerritoryDistrict(f"rally:{slot}", rally_name, "rally",
                                          rally_owner, (a, b), selected),
                        TerritoryDistrict(f"duel:{slot}", duel_name, "duel",
                                          duel_owner, (a, b), selected),
                    ))
            if p is None:
                return TerritoryBoard(
                    season, selected, current, phase, None,
                    tuple(city_banners), tuple(matches), tuple(districts), ())
            viewer_city = p["city"]
            my_banner = banner_map[viewer_city]
            my_match = next((m for m in matches if viewer_city in (m.city_a, m.city_b)), None)
            hits = (my_match.hits_a if my_match.city_a == viewer_city else my_match.hits_b) if my_match else 0
            roster = max(1, min(3, my_banner.registered))
            missions = (
                TerritoryMission(
                    "Rally the Crew",
                    "Have different eligible city members earn real individual points today.",
                    my_banner.active, roster, my_banner.active >= roster),
                TerritoryMission(
                    "Rival City Ambush",
                    f"Land scored snowballs on {my_match.opponent(viewer_city) or 'a rival'} today."
                    if my_match else "Wait for the daily rival pairing.",
                    hits, 2, hits >= 2),
                TerritoryMission(
                    "Local City Mission",
                    f"Complete {my_banner.mission_name} together.",
                    my_banner.mission_progress, max(1, my_banner.mission_target),
                    my_banner.mission_complete),
            ) if selected is not None else ()
            return TerritoryBoard(
                season, selected, current, phase, viewer_city,
                tuple(city_banners), tuple(matches), tuple(districts), missions)

    def rivalries(self, season: str, viewer: int, city: str):
        """Season-to-date head-to-head records for any of the six cities.

        A registered viewer may inspect city-wide public-style aggregates,
        never another individual's private identity or protected profile.
        """
        if city not in CITIES:
            raise TerritoryError("Unknown event city.")
        with self.store.connect() as con:
            con.execute("BEGIN")
            player = con.execute(
                "SELECT review_state FROM players WHERE season_key=? "
                "AND discord_user_id=?", (season, viewer)).fetchone()
            if player is None or player["review_state"] == "disqualified":
                raise TerritoryError("Register with /snow join to see City Wars.")
            return _rivalries(con, season, city, None)
