# v2.9.9d — Snowflake Catch: Full Interactive Game

**Web-only QA release.** Snowflake Catch is the fourth full Arcade 2.0
mini-game using the existing canvas, animation, sound, input and session
lifecycle host from v2.9.9. The original Discord Winter Arcade, shared
resource pool, city rankings, classic three-start limit and prizes are
unchanged.

## Gameplay

Open Winter Arcade and select **Play Snowflake Catch · QA**.

- Move the basket left or right using pointer/trackpad drag, touchscreen
  movement, Left/Right arrows, A/D keys or large on-screen buttons.
- Catch normal white snowflakes (+3), blue crystals (+6) and golden
  snowflakes (+10). Catch streaks add small escalating bonus points.
- Avoid falling icy shards (−12 and reset the streak).
- Three 20-second waves: light snowfall, gusty flurries and a faster
  blizzard finale. Falling objects drift in wind and sway; a wind
  direction indicator helps players aim ahead.
- The **60-second** round ends automatically and shows total score,
  caught objects, icy hits, best combo and saved personal best.
- Responsive wide/mobile canvas, simple controls, generated opt-in audio
  cues and low-motion support remain part of the shared arcade system.

Practice rounds are unlimited, unranked and scored 0–100. No competitive
or economic record is modified.

## Server-validated physics and integrity

The server creates 45 falling objects with a deterministic schedule,
including start and impact times, wave, wind velocity, sway and type. It
calculates each object's x/y trajectory and resolves **every object at
its impact timestamp** against the basket position known to the server.

The browser does not report "hit", "hazard avoided", a selected flake ID,
a score or a score multiplier. It can only submit a bounded basket
position and the next action index. Server constraints include a maximum
plausible basket movement speed, sequential input, unique idempotency
keys, account/session ownership and a maximum input rate. Inputs and
resolved events are recorded independently in the new web arcade tables.

Unreported hazards are still resolved when the server advances the game,
so simply suppressing a hazard-hit request does not avoid penalties.
For this QA release, session updates use interpolation between accepted
basket samples rather than treating client-rendered hit tests as prizes.
A future ranked variant would require additional anti-automation work
before any reward or leaderboard integration.

Interrupted responses retain the same idempotency key and action body
on retry. A pause freezes game elapsed time; switching away from the
arcade auto-pauses. The complete round is stored server-side and can be
resumed after reconnecting.

## Protected staging activation (off by default)

Pushing to GitHub **does not deploy this game** to Railway and does not
create the database tables in the running staging environment.

1. Back up the isolated **snowfall_web_qa** PostgreSQL database.
2. Enter a protected staging shell with its private QA database DSN
   and set SNOWFALL_API_SEASON_KEY=web-qa-2026. The DSN must target
   exactly /snowfall_web_qa, not the production/imported /railway DB.
3. Run the additive guarded installer:

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

   This verifies both the database name and the QA project/season marker.
4. Check web_arcade_catch_sessions and web_arcade_catch_actions tables and
   indexes were created without changes to the canonical game schema.
5. Enable SNOWFALL_ARCADE_V299D_ENABLED=1 on **Snowfall-Web-QA only** and
   redeploy the QA website. Other arcade games have their own flags:
   SNOWFALL_ARCADE_V299A_ENABLED (Target Gallery),
   SNOWFALL_ARCADE_V299B_ENABLED (Safecracker),
   SNOWFALL_ARCADE_V299C_ENABLED (Snowman Builder) and
   SNOWFALL_ARCADE_V299_ENABLED (generic practice drills).
6. Test using a registered Underworld staging character, on desktop and
   phone. Check touch drag, buttons, keyboard movement, three waves, wind,
   icy-shard penalties, bonuses, resume/reconnect and end-of-timer records.

Do **not** enable this feature on the production website or Discord worker.
No web startup action automatically installs its tables.

## Automated checks

- python -m pytest -q tests/test_v299d_catch.py
- python -m pytest -q tests/test_v299_arcade_postgres.py
- node --check src/snowfall/platform/static/arcade-catch-v299d.js
- node --test tests/test_v299d_catch_browser.mjs
- Full GitHub Actions CI across Linux Python 3.12/3.13, Windows Python 3.13
  and isolated PostgreSQL integration.

## Next mini-game

**v2.9.9e — Christmas Trivia**: fully playable quiz rounds with timed
questions, themed challenges, streaks and server-validated results.
