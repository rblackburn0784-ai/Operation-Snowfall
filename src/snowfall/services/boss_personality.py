"""Snow Don dramatic reactions; purely cosmetic, no attack or scoring changes."""
from __future__ import annotations

import hashlib

from snowfall.db.store import Store

# Reactions are ordered from healthier to more damaged. Each can post once
# per day from the existing announcement publisher's persisted message keys.
BOSS_PHASES = (
    (75, 'The Don Loses His Hat',
     "A well-placed snowball sends the Don's fedora into the gutter. His icy lookouts scatter "
     "as the first cracks spread through his frosted suit."),
    (50, 'The Don Is Losing His Cool',
     "Half his snow is gone. His Tommy Gun freezes, the Chicago speakeasy lights flicker, "
     "and the Don demands to know which crew started this blizzard."),
    (25, 'Last Stand at the Frozen Alley',
     "The Don is barely standing. His hat is gone, his snow is crumbling, "
     "and his guards have fled for hot chocolate. This is the final assault."),
)


def crossed_phases(before: int, after: int, maximum: int) -> tuple[int, ...]:
    """Detect newly crossed thresholds on a successful shared boss hit."""
    if maximum <= 0 or before <= after:
        return ()
    return tuple(phase for phase, _, _ in BOSS_PHASES
                 if before * 100 > phase * maximum >= after * 100)


def reaction_for_result(result) -> str | None:
    """Per-attack boss line. Ignore echo and missed attacks."""
    if result.kind != 'boss' or result.echo or not result.hit or result.repeated:
        return None
    if result.final_blow:
        return "🎉 THE SNOW DON HAS FALLEN! Chicago's finest snowman has been iced."
    before = result.hp_after + result.damage
    crossed = crossed_phases(before, result.hp_after, result.max_hp)
    if not crossed:
        return None
    phase = crossed[-1]
    return next(f"☃️ **{title}!** {text}" for n, title, text in BOSS_PHASES if n == phase)


def phase_announcement(day: int, phase: int) -> str:
    if not 1 <= day <= 7:
        raise ValueError('Invalid event day')
    match = next(((title, text) for n, title, text in BOSS_PHASES if n == phase), None)
    if match is None:
        raise ValueError('Unknown Snow Don phase')
    title, text = match
    return (f"☃️ **SNOW DON — DAY {day}/7: {phase}% HEALTH!**\n"
            f"### {title}\n{text}\n"
            "Keep attacking! Each player keeps their six daily attempts; individual prizes only.")


def reached_phases(store: Store, season_key: str, day: int) -> tuple[int, ...]:
    """Read live *shared* boss HP. Disabled bosses never announce phases."""
    if not 1 <= day <= 7:
        return ()
    with store.connect() as con:
        row = con.execute('''SELECT w.boss_hp,w.boss_initial_hp,
            COALESCE(s.boss_enabled,1) AS enabled FROM world_days w
            LEFT JOIN world_settings s ON s.season_key=w.season_key
            WHERE w.season_key=? AND w.day=?''', (season_key, day)).fetchone()
    if not row or not row['enabled'] or row['boss_initial_hp'] <= 0:
        return ()
    return tuple(n for n, _, _ in BOSS_PHASES
                 if 100 * row['boss_hp'] <= n * row['boss_initial_hp'])


RAID_REACTIONS = {
    "miss": (
        "The Don brushes snow off his lapels. 'Is that all you got, pal?'",
        "A snowball sails past. The Don's cigar doesn't even wobble.",
        "'Tell your crew to take aim next time,' the Snow Don growls.",
    ),
    "hit": (
        "The Don staggers against the frozen speakeasy door.",
        "Snow explodes from his shoulder. 'Somebody find that wise guy!'",
        "His icy buttons rattle across the cobbles. The mob roars.",
    ),
    "echo": (
        "A snowbound training dummy takes the hit. The real Don is already down.",
        "The raiders practise against the Don's frozen shadow. No second victory is awarded.",
    ),
    "final": (
        "The last snowball finds its mark. The Don's empire breaks into a thousand flakes.",
    ),
}


def boss_banter(result) -> str | None:
    """Display-only, stable banter for every boss outcome.

    Uses the immutable Discord interaction ID, never WorldEngine's RNG.
    Repeated results reuse the same line, with no second award.
    """
    if result.kind != "boss":
        return None
    key = ("echo" if result.echo else "final" if result.final_blow else
           "hit" if result.hit else "miss")
    options = RAID_REACTIONS[key]
    digest = hashlib.blake2b(str(result.interaction_id).encode("utf-8"),
                             digest_size=4).digest()
    return options[int.from_bytes(digest, "big") % len(options)]


def phase_transitions(result) -> tuple[int, ...]:
    """All genuine crossed thresholds, excluding echoes, misses and replays."""
    if (result.kind != "boss" or result.echo or result.repeated or not result.hit
            or result.final_blow):
        return ()
    before = min(result.max_hp, result.hp_after + result.damage)
    return crossed_phases(before, result.hp_after, result.max_hp)


def phase_story(result) -> str | None:
    milestones = phase_transitions(result)
    if not milestones:
        return None
    titles = [next(title for num, title, _ in BOSS_PHASES if num == m)
              for m in milestones]
    return ("☃️ **BOSS PHASE TRANSITION:** " +
            " → ".join(f"{m}% — {title}" for m, title in zip(milestones, titles))
            + "\nThe next portrait reflects the Don's remaining shared health.")
