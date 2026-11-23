# v2.9.9c — Snowman Builder: Full Interactive Game

**Web-only QA release.** The third real Arcade 2.0 mini-game uses the same
canvas/input/sound/session host as Target Gallery and Frozen Safecracker.
The existing Discord games, three-start Classic limit, shared passport,
resources and paid prizes are **unchanged**.

## Gameplay

Players open Winter Arcade and choose **Build a Snowman · QA**. The screen
shows a snowman blueprint and a tray of parts. Drag a part from the tray
onto its translucent target, or tap a part then tap its matching target.
Keyboard access: keys 1–9, 0 and minus select tray items, arrow keys move
the placement cursor, Enter/Space places the selection, H toggles outlines
and Escape deselects. "Place selected part" and "Show / hide outlines"
also provide on-screen controls.

There are three progressively more complex snowmen in one **150-second**
run:

1. **First Snowfall** — four snowballs/parts: base, torso, head, hat.
2. **Frosty Friend** — seven parts, including scarf, carrot nose and
   left/right twig arms; one decoy in the tray.
3. **Blizzard Master** — nine parts, including accessories and coal
   buttons; two decoy items.

A total of **20 correctly placed parts** can be fitted per game. Build
stages, the current part tray, selected parts and score are shown in a
responsive 640×360 arcade canvas, with original snowman artwork used as
a subdued backdrop. Success, errors and complete blueprints have
immediate visual and optional audio cues.

Server scoring awards four points for each correct fit, plus milestone
bonuses of 4/6/10 for completed blueprints; wrong placements and decoys
cost three points, with a small completion-time adjustment. Scores are
capped at 100, and personal practice records are retained.

## Session state and integrity

The server independently generates the three blueprints and validates
the selected part against its current-round slot coordinates and drop
tolerance. Browser requests contain only a session ID, action sequence,
part ID and normalized coordinates, not points or a success assertion.

Placements are transactional, audit-logged, replay-safe and restricted to
the currently signed-in Underworld account. Out-of-order actions,
duplicates, rapid submissions and prior-day sessions are rejected.
The server owns the timer, stage transitions and score. Pausing,
navigation, a temporary disconnect and later reopening preserve
progress. Interrupted requests retry their original idempotency key,
without spending another attempt on a fabricated response.

**This is unlimited, unranked QA practice.** It does not award shared
Discord badges, alter Classic daily starts, change seasonal currency,
or insert into the official score/prize tables. Future competitive
adaptations require a separate balancing and security review.

## Explicit staging activation — disabled by default

The GitHub push adds code and tests but **does not perform** the database
migration or activate the game on Railway.

1. Back up the isolated Snowfall-Web-QA PostgreSQL database.
2. On a protected staging shell, use a private connection string for the
   **snowfall_web_qa** logical database, never the imported **railway**
   database. Set SNOWFALL_API_SEASON_KEY=web-qa-2026.
3. Run the additive, guarded installer:

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

   Its checks require the exact database name and QA project/season
   marker. Existing web-only arcade tables are left intact.
4. Verify web_arcade_snowman_sessions and web_arcade_snowman_actions
   exist. The canonical game schema version is unchanged.
5. Enable **SNOWFALL_ARCADE_V299C_ENABLED=1** on the **QA web service
   only**, then redeploy. The Gallery, Safecracker and basic drills have
   their own independent flags.
6. Test with a registered Underworld staging account on desktop and
   phone: drag, select/tap, keyboard, decoys, three blueprints, timer,
   interruption, refresh, save/resume and final results.

Do not enable this switch in the Discord worker or production. The
web service never automatically provisions the new tables.

## Regression commands

- python -m pytest -q tests/test_v299c_snowman.py
- python -m pytest -q tests/test_v299_arcade_postgres.py
- node --check src/snowfall/platform/static/arcade-snowman-v299c.js
- node --test tests/test_v299c_snowman_browser.mjs
- Full CI: Linux Python 3.12/3.13, Windows Python 3.13, browser
  regressions and isolated PostgreSQL integration.

## Next game

**v2.9.9d — Snowflake Catch** will use the same shared arcade host with
a movable catch basket, wind, falling snowflakes, hazards and time scoring.
