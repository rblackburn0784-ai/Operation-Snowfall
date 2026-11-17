"""Deterministic, score-neutral combat broadcast text for v0.2.3."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from snowfall.services.combat import CombatResult
from snowfall.services.combat_intel import CombatIntel


@dataclass(frozen=True)
class FightBeat:
    headline: str
    reaction: str
    streak: int
    personal_best: int
    pair_hits: int
    pair_received: int
    revenge: bool
    repeat: bool


def _line(interaction_id: str, choices: tuple[str, ...]) -> str:
    # Selection cannot alter combat RNG and is stable across command retries.
    digest = hashlib.blake2b(interaction_id.encode("utf-8"), digest_size=4).digest()
    return choices[int.from_bytes(digest, "big") % len(choices)]


def fight_beat(result: CombatResult, intel: CombatIntel) -> FightBeat:
    rival = intel.rival(result.target_id)
    revenge = bool(
        not result.repeated and result.hit and result.points_awarded > 0
        and rival and rival.last_revenge_interaction == result.interaction_id)
    if result.repeated:
        headline = "PREVIOUSLY RECORDED"
        reactions = ("This throw was already settled. No second score or snowball spent.",)
    elif result.knocked_out:
        headline = "RIVAL KNOCKED OUT"
        reactions = (
            "A snow-covered getaway, and a rival is down for the count!",
            "Someone fetch the hot cocoa. That was a freezing finish!",
            "The winter streets have a new story to tell.",
        )
    elif result.critical:
        headline = "CRITICAL SNOWBALL"
        reactions = (
            "Bullseye! Even the lookouts felt that one.",
            "An ice-cold shot straight from the top shelf!",
            "The snowball found its mark like a seasoned marksman.",
        )
    elif result.hit:
        headline = "DIRECT HIT"
        reactions = (
            "A clean shot across enemy-city lines.",
            "That snowball arrived with a personal message.",
            "One rival caught out in the cold.",
        )
    else:
        headline = "SNOWBALL MISSED"
        reactions = (
            "The wind took that one. Reload and regroup.",
            "The rival ducks; the snowball decorates a nearby wall.",
            "The city gets a fresh coating of snow. Nothing else changes.",
        )
    return FightBeat(headline, _line(result.interaction_id, reactions),
                     intel.current_streak, intel.best_streak,
                     rival.hits if rival else 0, rival.received_hits if rival else 0,
                     revenge, result.repeated)
