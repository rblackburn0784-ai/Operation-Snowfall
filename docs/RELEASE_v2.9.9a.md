# v2.9.9a — Snowball Target Gallery: Full Interactive Game

**Web-only QA release.** The Target Gallery now uses a complete 45-second
shooting-game scene rather than the old three-choice quiz. The v2.9.9 canvas
host remains reusable by Safecracker, Snowman Builder, Snowflake Catch and
Trivia. Discord's existing arcade and shared prize/score economy are unchanged.

## How to play

- In Winter Arcade, choose **Play full Target Gallery · QA**.
- Start a game, then aim with mouse/trackpad, touch or arrow keys. Tap, click,
  Space or Enter to throw a snowball.
- Three escalating 15-second waves of animated targets: slower opening
  movement, then faster pop-ups and shorter exposure intervals.
- 32 snowballs, moving bullseyes (+7), golden targets (+15), decoy targets
  (−9), misses (−2), combo bonuses and a score capped at 100.
- Visible shot feedback, an ammunition counter, wave progression, running
  time, accuracy, combo, results panel and practice personal best.
- Pausing, leaving the page, closing the game or browser refresh preserves
  server-side progress; select the full gallery again to reopen. Completing a
  round permits another unlimited practice run.
- Sound effects are opt-in, with no audio asset downloads. Layout is
  responsive and uses original bundled arcade artwork.

## Scoring and integrity

The server issues and persists each run's target schedule, then **recomputes
hit detection** using authoritative server elapsed time and shot coordinates.
The browser cannot submit awarded points or target IDs. Each shot is audited,
has a unique idempotency key, must follow the correct shot index and timing,
and cannot reuse a consumed target or exceed the 32-ball limit.
Concurrent requests, replay changes, wrong identities, stale sessions and
rapid-fire submissions are rejected. Interrupted responses retry the same
shot with the original key.

**These are still QA-only, unranked practice scores**. They do not count
towards Classic Discord arcade daily starts, passports, city rankings, paid
prizes, snowball resources or event points. Gameplay data is separate in
web_arcade_gallery_sessions and web_arcade_gallery_shots. The original
five button-choice games remain playable. Public competitive rankings and
shared start limits will not be changed without a later balancing/release gate.

## Required QA activation (do not run against production)

The game is **OFF by default**. GitHub commits do not perform the database
migration or turn on this feature automatically.

1. Take a backup of the isolated Railway Snowfall-Web-QA PostgreSQL database.
2. In the protected staging environment, set
   SNOWFALL_API_SEASON_KEY=web-qa-2026 and SNOWFALL_DATABASE_URL to the
   existing **QA** PostgreSQL DSN. Validate that the target is the isolated
   QA database before executing.
3. Rerun the additive installer (safe if the v2.9.9 practice table already
   exists):

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

4. Confirm the new web_arcade_gallery_sessions and
   web_arcade_gallery_shots tables and their indexes exist.
5. Enable SNOWFALL_ARCADE_V299A_ENABLED=1 in the **QA web service only**.
   The earlier generic practice drills still separately require
   SNOWFALL_ARCADE_V299_ENABLED=1.
6. Redeploy the QA web service. Sign in with a registered Underworld test
   character, open Winter Arcade and use the separate full Target Gallery
   button. Verify at 320px, 640px and desktop sizes with pointer and touch.

Do not enable this flag on the Discord worker or production website. This
release does not automatically provision the new tables at startup.

## Tests

- python -m pytest -q tests/test_v299a_gallery.py
- python -m pytest -q tests/test_v299_arcade_postgres.py
- node --check src/snowfall/platform/static/arcade-v299.js
- node --check src/snowfall/platform/static/arcade-gallery-v299a.js
- node --test tests/test_v299a_gallery_browser.mjs
- Full GitHub CI on Linux, Windows and isolated PostgreSQL

Manual QA still required for responsiveness, real touch response times,
real browser audio, interrupted network connections and smooth gameplay.
