"""Snow Don dramatic reactions; purely cosmetic, no attack or scoring changes."""
from __future__ import annotations

from snowfall.db.store import Store

# Reactions are ordered from healthier to more damaged. Each can post once
# per day from the existing announcement publisher's persisted message keys.
BOSS_PHASES = (
    (75, 'The Don Loses His Hat',
     "The Snow Don's hat has taken a direct hit. He's blaming the wind, but the mob knows better."),
    (50, 'The Don Is Losing His Cool',
     "Half his snow is gone and his Tommy Gun is icing over. Keep those snowballs coming."),
    (25, 'Last Stand at the Frozen Alley',
     "The Don is barely holding together. His guards have fled for hot chocolate."),
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
