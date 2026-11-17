"""v0.2.3 combat intelligence from immutable combat events.

Private, season-scoped read model only. Neither this module nor its UI can
consume ammunition, change RNG probabilities, create official score, or edit
combat_events. A revenge is a scored retaliatory HIT after the opponent's
latest scored hit against the player, not a reward or automatic attack.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from snowfall.db.store import Store, _parse


@dataclass(frozen=True)
class RivalRecord:
    user_id: int
    name: str
    city: str
    attacks: int
    hits: int
    received_attacks: int
    received_hits: int
    knockouts: int
    points: int
    revenges: int
    pending_revenge: bool
    last_incoming_hit: datetime | None
    last_event: int
    last_revenge_interaction: str | None = None

    @property
    def accuracy(self) -> float:
        return round(self.hits * 100 / self.attacks, 1) if self.attacks else 0.0


@dataclass(frozen=True)
class CombatIntel:
    current_streak: int
    best_streak: int
    total_attacks: int
    total_hits: int
    rivalries: tuple[RivalRecord, ...]

    @property
    def revenge_alerts(self) -> tuple[RivalRecord, ...]:
        return tuple(r for r in self.rivalries if r.pending_revenge)

    @property
    def revenge_count(self) -> int:
        return sum(r.revenges for r in self.rivalries)

    def rival(self, user_id: int) -> RivalRecord | None:
        return next((r for r in self.rivalries if r.user_id == user_id), None)


class CombatIntelEngine:
    def __init__(self, store: Store):
        self.store = store

    def snapshot(self, season: str, user: int) -> CombatIntel:
        # Read-only and transactional snapshot to avoid half-assembled battle recaps.
        with self.store.connect() as con:
            player = con.execute(
                "SELECT 1 FROM players WHERE season_key=? AND discord_user_id=? "
                "AND review_state!='disqualified'", (season, user)).fetchone()
            if player is None:
                raise ValueError("Register with /snow join to see your combat history.")
            rows = con.execute("""SELECT c.id, c.interaction_id, c.attacker_id,
                    c.target_id, c.hit, c.critical, c.knocked_out,
                    c.points_awarded, c.happened_at_utc,
                    p.mr_username AS rival_name, p.city AS rival_city
                FROM combat_events c JOIN players p
                ON p.season_key=c.season_key AND
                   p.discord_user_id=(CASE WHEN c.attacker_id=?
                                     THEN c.target_id ELSE c.attacker_id END)
                WHERE c.season_key=? AND (c.attacker_id=? OR c.target_id=?)
                ORDER BY c.id ASC""",
                (user, season, user, user)).fetchall()
        state: dict[int, dict] = {}
        current = best = attacks = hits = 0
        for ev in rows:
            outgoing = ev["attacker_id"] == user
            other = ev["target_id"] if outgoing else ev["attacker_id"]
            if other not in state:
                state[other] = dict(
                    name=ev["rival_name"], city=ev["rival_city"], attacks=0,
                    hits=0, received_attacks=0, received_hits=0,
                    knockouts=0, points=0, revenges=0, pending_revenge=False,
                    last_incoming_hit=None, last_event=0, last_revenge_interaction=None,
                )
            rival = state[other]
            rival["last_event"] = ev["id"]
            scored = bool(ev["hit"] and ev["points_awarded"] > 0)
            if outgoing:
                attacks += 1
                rival["attacks"] += 1
                # A miss breaks a streak. Officially unscored hits (cap reached)
                # do not count as scored-hit streaks either.
                current = current + 1 if scored else 0
                best = max(best, current)
                if scored:
                    hits += 1
                    rival["hits"] += 1
                    rival["points"] += ev["points_awarded"]
                    rival["knockouts"] += int(bool(ev["knocked_out"]))
                    if rival["pending_revenge"]:
                        rival["revenges"] += 1
                        rival["last_revenge_interaction"] = ev["interaction_id"]
                        rival["pending_revenge"] = False
            else:
                rival["received_attacks"] += 1
                if scored:
                    rival["received_hits"] += 1
                    rival["pending_revenge"] = True
                    rival["last_incoming_hit"] = _parse(ev["happened_at_utc"])
        rivals = tuple(sorted(
            (RivalRecord(other, **data) for other, data in state.items()),
            key=lambda r: (not r.pending_revenge, -r.last_event, r.name.casefold(), r.user_id)))
        return CombatIntel(current, best, attacks, hits, rivals)


def target_order(targets, intel: CombatIntel, mode: str = "smart"):
    """Rank only engine-approved targets; never add an ineligible player."""
    if mode not in ("smart", "revenge", "fresh", "vulnerable"):
        raise ValueError("Unknown target search mode.")
    by_id = {t.user_id: t for t in intel.rivalries}
    def key(t):
        revenge = by_id.get(t.discord_user_id)
        pending = bool(revenge and revenge.pending_revenge)
        if mode == "revenge":
            return (not pending, -t.hits_remaining, -t.warmth,
                    t.mr_username.casefold(), t.discord_user_id)
        if mode == "fresh":
            return (-t.hits_remaining, not pending, -t.warmth,
                    t.mr_username.casefold(), t.discord_user_id)
        if mode == "vulnerable":
            return (t.warmth, not pending, -t.hits_remaining,
                    t.mr_username.casefold(), t.discord_user_id)
        return (not pending, -t.hits_remaining, -t.warmth,
                t.mr_username.casefold(), t.discord_user_id)
    ordered = sorted(targets, key=key)
    return [t for t in ordered if by_id.get(t.discord_user_id) and
            by_id[t.discord_user_id].pending_revenge] if mode == "revenge" else ordered
