# v2.9.6c — Snow Don Visual Sync & Boss Presentation

QA web-only release. The current day's persisted raid is read via
`GET /v1/web/boss` (no writes or initialisation). The website shares the bot's
integer health-stage function and exact 100–10% PNG artwork. At zero HP, use
`snow_don_0.webp` on the boss card and `final_defeat.webp` on the homepage.
Missing/disabled bosses are never portrayed as defeated.

The existing cinematic art is not an eleven-image matched sequence. Map the
four existing scenes to the bot's 75/50/25 narrative thresholds: phase_ice,
rage_tommy, rage_snowball, phase_frostfire; then final_defeat at zero.
The splash and boss card use one read snapshot, refreshed after actions and
every 30 seconds in a visible tab. A failed request labels the last known state
as refresh pending. Display current raid-day hits, contributors, misses and
recorded encounter results. Preserve frozen-echo actions, daily limits,
scoring, ownership, identities and account linking. No database migration.

Only Snowfall-Web-QA is deployed. Rollback: ae402184f4c01dc26960a16b7bf04c5c165d34c6.
