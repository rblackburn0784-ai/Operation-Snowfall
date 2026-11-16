# Operation Snowfall v0.1.6a — In-App Test Day Manager

## Changed from v0.1.6

v0.1.6 required a separate bot application/token and a separate server for practice. **v0.1.6a replaces that workflow** with host-managed tests inside the **existing** Discord application and server, in a channel nominated by the host. One Discord process and one `.env` token are used. Existing game mechanics and event dates remain unchanged.

## New commands

- `/snowadmin test-start day:<1..7> channel:#snowfall-testing confirmation:TEST` — starts that day in a disposable practice season and database, posts a prominent TEST notice.
- `/snowadmin test-status` — shows the active day, today's stage/perk, channel, participants and ending instructions.
- `/snowadmin test-day day:<1..7> confirmation:RESET_TEST_DAY` — clears all existing test actions/items/score state, retains test registrations and begins the chosen day.
- `/snowadmin test-end confirmation:END_TEST archive:false` — ends the practice session and deletes its SQLite files without restarting the bot.
- `/snowadmin test-end confirmation:END_TEST archive:true` — makes a verified local SQLite archive and deletes the active test database.
- `/snowadmin test-stop confirmation:END_TEST` — safe backwards-compatible alias that **ends practice**, never closes the Discord app.

## Data isolation and anti-accident safeguards

- Practice sessions use unique `rehearsal-<uuid>` season keys and `data/practice/day-<day>-<uuid>.sqlite3` files. They **never** use the production SQLite file.
- Command routing is *channel-scoped*: normal `/snow` commands in the test channel use practice; slash commands outside use production. Each interactive menu pins itself to the originating season to prevent cross-season changes. Stale test buttons become inactive after end/day switch.
- Production scheduled announcements and five-minute leaderboard updates retain original settings and SQLite store, with no test messages to the two live announcement channels.
- Tests cannot start in the actual leaderboard or announcement channel, or after production kickoff.
- Test dashboards are not persistent production button IDs. A TEST day uses ephemeral controls with unique IDs and a timeout, preventing old practice buttons from targeting live data after restart.
- Cleanup is limited to the specific practice SQLite database and its sidecars; archived copies are stored separately. Archive failures leave the session available instead of silently deleting its data.
- Restart drops any orphaned temporary practice databases and does not change production state.

## Verification

- Automated tests cover all seven event-day selections, the stage/theme, each day's boss/fort creation, practice registration, context-routed calls, reset, archive, orphan cleanup and production-database isolation.
- The existing combat/economy/broadcast/graphics regression suites still run.
- A live Discord smoke test in the actual event server is **still required**, including user permissions, one practice day per theme, and test end/cleanup before production launch.

## How to deploy

Back up `data/snowfall.sqlite3`, then in the existing PyCharm project:

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

No additional Discord application, server, token, `config.test.toml` or schema migration is needed. **The production schema stays at v6.** The `--test` command-line mode is retired; `/snowadmin test-start` starts the in-app rehearsal. For detail, see `docs/TEST_MODE_v0.1.6a.md`.
