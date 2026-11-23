# v2.9.9 — Arcade 2.0: Interactive Game Engine

**Scope:** isolated QA web only. Discord, existing three-start competitive limit,
shared passport, official scores, economy, prizes and seasonal balance are unchanged.

## Implemented

- One reusable 640 × 360 canvas runtime shared by all five arcade modes, with
  pointer/touch and keyboard controls, animations, timers, hit feedback,
  optional synthesized sound, pause/resume and responsive layout.
- Five **unranked mechanics practice drills**. These are training previews,
  not the complete games planned for v2.9.9a–e: moving gallery target,
  turnable safe dial, snowman accessory drag/tap, basket and falling flake,
  and quiz answer cards.
- Separate web-only server sessions with ownership checks, one active
  session per player/mode, bounded checkpoints, optimistic revisions,
  replay-safe retries, saved elapsed time/position/angle and unlimited
  practice. Re-enter Practice on the same card to resume.
- Training scores are unranked and client-reported: the server bounds
  checkpoints but does NOT treat them as verified competitive scoring.
  Practice never writes social arcade runs, awards, ledgers or prizes.

## Required QA database installation (before enabling practice)

This is an **explicit additive PostgreSQL install**. It deliberately does not
alter the canonical Discord/game database version or existing arcade tables.

1. Back up the isolated staging PostgreSQL database.
2. On a protected staging shell, set SNOWFALL_DATABASE_URL to the QA private
   DSN and SNOWFALL_API_SEASON_KEY=web-qa-2026.
3. Run: python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY
4. Verify the new web_arcade_practice_sessions table and index, then set
   SNOWFALL_ARCADE_V299_ENABLED=1 on the QA web service and redeploy that
   service only. Do not run this against the production database.
5. Sign in with a registered Underworld QA character, choose Winter Arcade
   then Interactive practice under each game. Pause, reload, choose the same
   game again to resume the server checkpoint.

The feature gate is OFF by default: the new practice buttons read Coming soon
until the QA table is installed and the environment flag is enabled. The API
also rejects practice calls while the flag is off.

The installer checks the canonical game schema and QA season before creating
the separate practice table. Without the installation, new practice requests
will fail; the existing Classic browser and Discord arcade are unaffected.

## Validation

- python -m pytest -q tests/test_v299_arcade_practice.py
- node --check src/snowfall/platform/static/arcade-v299.js
- node --test tests/test_v299_arcade_browser.mjs
- Full GitHub CI on Linux, Windows, PostgreSQL.

Check mobile widths, touch drags, safe dial, keyboard access, background
pause, failed saves, refresh/re-entry, duplicate writes and cross-account
access before enabling staging practice. Competitive mini-games remain
Classic until each specific game is built and validated in v2.9.9a–e.
