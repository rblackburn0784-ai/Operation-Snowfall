# v2.9.9b — Frozen Safecracker: Full Interactive Game

**Isolated QA web release.** This completes the second playable Arcade 2.0
mini-game on the reusable canvas, audio, input and session host.
The original Discord choice arcade, passport, three-start competitive cap,
player resources and official rewards remain unchanged.

## How to play

1. In the Winter Arcade choose **Crack the Frozen Safe · QA**.
2. Click **Start / resume**. Use a mouse or touch to grip the outer dial and
   rotate it in the direction shown. Keyboard: Right Arrow clockwise, Left
   Arrow anticlockwise, Shift+Arrow for four notches.
3. Complete at least one full forty-notch revolution, then fine-tune until
   the feedback changes from quiet to faint, near and a clear click.
4. Press **SET TUMBLER** (or Enter/Space) precisely on that number.
5. Complete all three combinations in order: clockwise, anticlockwise, then
   clockwise again. Each tumbler has its own hidden number.
6. Crack the safe in 90 seconds to reveal the combination, time-adjusted
   practice score, mistakes and personal best.

Wrong-direction rotations and premature Set presses cost a mistake. The
90-second timer freezes when paused; leaving the Arcade page auto-pauses.

A 40-notch brass dial, fixed pointer, three lock indicators, mechanical
proximity feedback, opt-in synthesized sound, responsive touch and keyboard
controls, resume and finished-vault presentation complete the gameplay.

## Server security and scoring

- Codes are generated and held in PostgreSQL per session and never
  provided to the browser until the round finishes.
- The server validates direction, revolutions, exact number alignment,
  action sequence, player ownership and elapsed playing time.
- Each action has an idempotency key. Reused actions, cross-account
  requests, impossible rotation speed, forged scores and out-of-order
  moves cannot mutate a competitive record.
- The client submits only signed dial movement or a Set action; it never
  submits a score, selected secret number or winning code.
- Scores are practice-only, independently audited, and bounded by the
  server. Early timeouts receive zero. Runs are unlimited and unranked,
  with no effect on Discord progress, event point ledgers or prizes.

## Explicit QA activation — OFF by default

GitHub commits do not automatically provision tables or enable this game.

1. Back up the isolated Snowfall-Web-QA PostgreSQL database.
2. Use the protected staging shell with a private PostgreSQL DSN pointing
   to the exact isolated database /snowfall_web_qa, NEVER the imported
   /railway database. Set SNOWFALL_API_SEASON_KEY=web-qa-2026.
3. Run the additive migration:

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

4. Verify web_arcade_safe_sessions and web_arcade_safe_actions exist,
   including their indexes. The installer requires the exact staging
   database and its verified project/season marker.
5. Set SNOWFALL_ARCADE_V299B_ENABLED=1 on the QA web service and redeploy.
   The Target Gallery and generic drills use independent feature switches
   SNOWFALL_ARCADE_V299A_ENABLED and SNOWFALL_ARCADE_V299_ENABLED.
6. Test a registered QA Underworld account on desktop and phone; verify
   touch drag, directional lock, audio, pause/resume, refresh, timer expiry
   and final score before considering wider exposure.

Do not enable this flag on the Discord worker or production. No migration
runs automatically during web startup.

## Regression commands

- python -m pytest -q tests/test_v299b_safecracker.py
- python -m pytest -q tests/test_v299_arcade_postgres.py
- node --check src/snowfall/platform/static/arcade-v299.js
- node --check src/snowfall/platform/static/arcade-safe-v299b.js
- node --test tests/test_v299b_safecracker_browser.mjs
- Full GitHub CI: Linux, Windows and isolated PostgreSQL.

## Next release

v2.9.9c — Snowman Builder will reuse the same input and scene runtime.
