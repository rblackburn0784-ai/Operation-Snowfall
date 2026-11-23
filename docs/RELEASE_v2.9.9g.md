# v2.9.9g — Arcade Atmosphere, Controls & Balancing

**Scope:** Five full interactive mini-games only. Unranked QA web
practice remains separate from Classic Discord-shared attempts, event
resources, passports, leaderboards and prizes. Existing artwork is
retained, with an additional lightweight canvas snowfall effect.

## Shared UX and winter atmosphere

Every full mini-game now uses the common winter arcade controls:

- Expandable **How to play · controls & scoring** guide with real
  keyboard, pointer and touch instructions for that game.
- Opt-in **Sound on/off**, default off, still using small synthesised
  effects rather than external audio files.
- **Calm effects on/off** suppresses additional snowfall and passes a
  reduced-motion signal to the five mini-game renderers. System-level
  reduced motion is always honoured.
- **High contrast on/off** increases canvas visibility and HUD contrast.
  These visual controls cannot affect gameplay or scoring.
- Responsive 49–50px control buttons, focus outlines and accessible
  status announcements; clear urgency banner at 10 and 5 seconds.
- **End run** requires a deliberate second click within six seconds,
  protecting users against accidental forfeits. Pause and Save & close
  still preserve server-owned progress.

## Individual controls

| Mode | Improved player-facing controls |
| --- | --- |
| Gallery | Large **Throw snowball** button, plus tap/click and keyboard aim/shoot; three-wave timing explained |
| Safecracker | Clockwise +4 and Anticlockwise −4 on-screen buttons and clearer exact-click guidance; keyboard arrows still supported |
| Snowman | Touch drag and tap-to-place, correct number-key mapping, arrow/Enter placement and optional outlines explained |
| Catch | Touch/drag basket positioning, A/D, arrows, Home/End, centre and on-screen directions clearly documented |
| Trivia | Gift card and True/False navigation, numbered letter tiles, undo/clear, Enter and streak bonuses explained |

## QA-only balance changes

All four adjustments affect *new server-issued game schedules or
blueprints*, not old saved sessions. They never alter official
competitive scores or prize economy.

- **Target Gallery:** middle-wave visible time 1,730 → 1,840 ms;
  last-wave 1,450 → 1,600 ms. Golden targets still disappear 230 ms
  earlier. 45 seconds, three waves and 32 snowballs unchanged.
- **Snowflake Catch:** middle-wave fall time 2,110 → 2,220 ms and
  last-wave fall time 1,730 → 1,880 ms. All 45 objects, hazards,
  valid speed bounds and the 60-second round remain unchanged.
- **Frozen Safecracker:** faint/near proximity cues broaden from
  5/2 to 7/3 notches, while an exact notch match and a full turn are
  still mandatory for each successful tumbler.
- **Snowman Builder:** server-certified target radius grows by 2 px
  in round 2 and 4 px in round 3 to make touch placement fairer.
  The 20 required pieces, decoys and scoring formula do not change.
- **Christmas Trivia:** difficulty tiers, timers, answer secrecy and
  scoring remain unchanged; control guidance is clearer.

## Activation and staging QA

There is **no new database schema or v2.9.9g environment switch**.
The upgraded assets appear automatically with the next explicit QA
website deployment, provided the older Arcade Hub / mini-game feature
flags and guarded arcade migrations were already enabled. Keep QA
isolated in **snowfall_web_qa**, never the main imported railway
database. The WEB_QA_ONLY installer remains mandatory if any earlier
full-game tables are missing. Do not deploy or turn on new flags on
the Discord worker or production without separate authorisation.

For manual QA, check all five games on a real phone and desktop:
game guides, optional sound, reduced-motion, high contrast, touch
controls, last-10-second alert, Pause/Save & close, two-click early
finish and resuming after navigation. Test fresh seeded rounds and
already saved rounds separately; verify no practice actions touch
Classic Discord attempts, score ledger, stamps or prizes.

## Automated regressions

- python -m pytest -q tests/test_v299g_arcade_balance.py
- node --check src/snowfall/platform/static/arcade-v299.js
- node --test tests/test_v299g_arcade_polish_browser.mjs
- Full GitHub CI: Python 3.12 and 3.13 on Linux, Python 3.13 on
  Windows, 5-game browser regressions and PostgreSQL compatibility.

## Next milestone

**v2.9.9h — End-to-End Release Hardening:** QA smoke tests, replay
safety, staging data isolation, final security review and controlled
launch checklist.
