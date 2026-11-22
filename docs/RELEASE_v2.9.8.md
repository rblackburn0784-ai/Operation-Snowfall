# v2.9.8 — The Complete Player Experience

Adds Winter Activities to the web UI: daily assignment claims, existing daily and bonus presents, inventory use, guard mode, earned titles, ordinary encounters, seven mystery cases, secret encounters and casebook. Uses the existing canonical player ID, existing engines and original artwork. Existing arcade gameplay remains Discord-only until v2.9.8a; staff controls and live community features remain scoped to later releases.

The API compatibility identifier remains 2.9.7; web release revision becomes 2.9.8. New authenticated routes use existing session, CSRF, expected player checks and idempotency. Only discovered clue text and earned conclusions are returned; daily action day is validated against authoritative event day. Existing reward limits and game rules remain unchanged. No migration or worker restart required for these web-only additions.

QA: test authenticated/unauthenticated access, daily rollover, repeated choices, cross-platform case records, inventory and rewards, paused/closed event and mobile dossier. All CI and live browser results must be reviewed before launch.
