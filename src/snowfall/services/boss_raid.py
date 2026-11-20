"""v0.2.4 cooperative Snow Don raid intelligence; entirely read-only.

The authoritative WorldEngine owns all HP, rolls, caps, echoes and awards.
Raid statistics are reconstructed from season/day-scoped immutable pve_events;
none of these honours produce new points, attempts, snowballs or prize rows.
"""
from __future__ import annotations

from dataclasses import dataclass

from snowfall.db.store import Store

MILESTONES = (25, 50, 75, 100)
PHASE_NAMES = (
    (75, "The Hat Falls"), (50, "The Frozen Underworld"),
    (25, "The Don's Last Stand"), (0, "The Final Snowfall"),
)


@dataclass(frozen=True)
class RaidMember:
    user_id: int
    name: str
    city: str
    shared_hits: int
    shared_damage: int
    attacks: int
    echo_attacks: int
    last_hit_at: str
    final_blow: bool


@dataclass(frozen=True)
class RaidCity:
    name: str
    damage: int
    raiders: int


@dataclass(frozen=True)
class RaidReport:
    day: int
    enabled: bool
    max_hp: int
    remaining_hp: int
    shared_damage: int
    hit_count: int
    misses: int
    contributors: int
    echo_attacks: int
    defeated: bool
    final_hitter: str | None
    members: tuple[RaidMember, ...]
    cities: tuple[RaidCity, ...]

    @property
    def progress(self) -> int:
        return min(100, (self.shared_damage * 100 // self.max_hp)) if self.max_hp > 0 else 0

    @property
    def phase(self) -> str:
        if not self.enabled:
            return "Boss disabled"
        if self.defeated:
            return "The Final Snowfall"
        percent = self.remaining_hp * 100 / self.max_hp if self.max_hp > 0 else 100
        for threshold, name in PHASE_NAMES[:-1]:
            if percent <= threshold:
                return name
        return "The Don Rules the Streets"

    @property
    def milestones(self) -> tuple[int, ...]:
        return tuple(value for value in MILESTONES if self.progress >= value)

    @property
    def next_milestone(self) -> int | None:
        return next((value for value in MILESTONES if value not in self.milestones), None)

    def member(self, user_id: int) -> RaidMember | None:
        return next((r for r in self.members if r.user_id == user_id), None)


class RaidEngine:
    def __init__(self, store: Store):
        self.store = store

    def report(self, season: str, day: int) -> RaidReport:
        if not 1 <= day <= 7:
            raise ValueError("Raid day must be 1–7.")
        with self.store.connect() as con:
            con.execute("BEGIN")  # One consistent read snapshot under concurrent hits.
            boss = con.execute(
                """SELECT w.boss_initial_hp,w.boss_hp,w.boss_defeated_at,
                    COALESCE(s.boss_enabled,1) AS enabled
                    FROM world_days w LEFT JOIN world_settings s
                    ON s.season_key=w.season_key
                    WHERE w.season_key=? AND w.day=?""", (season, day)).fetchone()
            if boss is None:
                raise ValueError("The Snow Don has not spawned for this day.")
            rows = con.execute(
                """SELECT e.attacker_id, p.mr_username, p.city, e.hit, e.echo,
                   e.damage, e.final_blow, e.effective_at_utc
                   FROM pve_events e JOIN players p
                     ON p.season_key=e.season_key
                    AND p.discord_user_id=e.attacker_id
                   WHERE e.season_key=? AND e.day=? AND e.kind='boss'
                   ORDER BY e.effective_at_utc ASC, e.happened_at_utc ASC, e.interaction_id ASC""", (season, day)).fetchall()

        # Mirror the actual saved shared HP. Damage totals are clamped by the
        # original boss attack transaction; echoes never enter shared totals.
        maximum = int(boss["boss_initial_hp"])
        remaining = int(boss["boss_hp"])
        enabled = bool(boss["enabled"])
        by_user: dict[int, dict] = {}
        by_city: dict[str, set[int]] = {}
        city_damage: dict[str, int] = {}
        shared_hits = misses = echoes = 0
        final_hitter = None
        for row in rows:
            uid, city = int(row["attacker_id"]), row["city"]
            if uid not in by_user:
                by_user[uid] = dict(
                    name=row["mr_username"], city=city, shared_hits=0,
                    shared_damage=0, attacks=0, echo_attacks=0, last_hit_at="",
                    final_blow=False,
                )
            record = by_user[uid]
            record["attacks"] += 1
            if row["echo"]:
                record["echo_attacks"] += 1
                echoes += 1
            elif row["hit"]:
                shared_hits += 1
                damage = max(0, int(row["damage"]))
                record["shared_damage"] += damage
                record["shared_hits"] += 1
                record["last_hit_at"] = row["effective_at_utc"]
                city_damage[city] = city_damage.get(city, 0) + damage
                by_city.setdefault(city, set()).add(uid)
            else:
                misses += 1
            if row["final_blow"] and not row["echo"]:
                record["final_blow"] = True
                final_hitter = row["mr_username"]

        members = tuple(sorted(
            (RaidMember(uid, **values) for uid, values in by_user.items()),
            key=lambda m: (-m.shared_damage, -m.shared_hits, m.name.casefold(), m.user_id)))
        cities = tuple(sorted(
            (RaidCity(city, damage, len(by_city.get(city, ())))
             for city, damage in city_damage.items()),
            key=lambda c: (-c.damage, c.name)))
        return RaidReport(
            day, enabled, maximum, remaining,
            max(0, maximum - remaining) if enabled else 0,
            shared_hits, misses, sum(m.shared_damage > 0 for m in members), echoes,
            enabled and bool(boss["boss_defeated_at"]) and remaining == 0,
            final_hitter, members, cities,
        )

    def final_result(self, season: str, day: int):
        """Recover the one genuine defeat for a replay-only GIF, no scoring."""
        report = self.report(season, day)
        if not report.enabled or not report.defeated:
            return None
        from snowfall.services.world import PveResult
        with self.store.connect() as con:
            row = con.execute("""SELECT interaction_id,kind,day,city,hit,damage,
                      points_awarded,theme_points,hp_after,max_hp,echo,final_blow
                FROM pve_events WHERE season_key=? AND day=? AND kind='boss'
                AND echo=0 AND final_blow=1 ORDER BY effective_at_utc ASC, happened_at_utc ASC, interaction_id ASC LIMIT 1""",
                (season, day)).fetchone()
        if row is None:
            return None
        return PveResult(row["interaction_id"], row["kind"], row["day"],
                         row["city"], bool(row["hit"]), row["damage"],
                         row["points_awarded"], row["theme_points"],
                         row["hp_after"], row["max_hp"],
                         bool(row["echo"]), bool(row["final_blow"]))
