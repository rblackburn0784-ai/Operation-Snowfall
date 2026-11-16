# Operation Snowfall v0.1.6 — Start and Stop the Test Bot

**This is an isolated TEST bot, not a switch that touches the production Christmas event.**

The safest setup uses a **second Discord application/bot token**, **second Discord server**, **separate season key**, **separate SQLite database**, and **separate announcement channels**. The test and production bots can run at the same time because their credentials and servers differ. Code rejects same-token, same-server, same-season, same-database and reused production-channel IDs.

## One-time setup in PyCharm

1. Create a *second* Discord application (e.g. `Operation Snowfall TEST`) in Discord Developer Portal and install it into a **different TEST Discord server**, with `bot` and `applications.commands` scopes; grant View Channel, Send Messages, Read Message History, Embed Links and Attach Files in that test server.
2. Copy `config.test.example.toml` to `config.test.toml`. Change `guild_id` to the **test server ID**, `admin_user_ids` to your and Kat's **Discord user IDs**, and optionally add TEST-server channel IDs. **Do not put live channel IDs there.** Keep the unique `season_key`, separate `database_path`, and `starts_at_utc = "AUTO"`.
3. In your existing local `.env`, add `DISCORD_TEST_TOKEN=` followed by the TEST application's token. **Leave your production `DISCORD_TOKEN` as it was.** Never paste either token into a chat or commit them to GitHub.
4. Run `python -m pip install -e ".[dev]"`, then `python -m pytest -q`.

## Run a test version

Open a **second PyCharm terminal**, leave your production instance alone, then:

```powershell
python bot.py --test
```

Terminal displays `SANDBOX MODE` and the test season/database path after connecting. If test credentials or server/database overlap production, startup fails *before Discord login*. Existing production scores and registrations are not modified.

Inside the **TEST server**:

1. `/snowadmin status` — displays **TEST INSTANCE — NO REAL PRIZES**.
2. `/snowadmin start confirmation:START` — begin the test season. `AUTO` gives an immediately startable *test* kickoff; it is saved only once to the test database.
3. Join two or more TEST Discord accounts from different cities using `/snow join`, opt in with `/snow ready`, then try `/snow throw`, `/snow boss`, `/snow siege`, `/snow quests`, `/snow present`, and the dashboards.
4. Test the two TEST broadcast channels if configured. Never use production channel IDs for testing.

## Stop a test version

- In the TEST server run `/snowadmin test-stop confirmation:STOP_TEST` as a host. The bot acknowledges, then **closes only the test Discord client**. The production bot continues running.
- Or use **Ctrl+C** in the PyCharm terminal running `python bot.py --test`.
- `/snowadmin test-stop` **refuses to close the production bot**, even if the caller is a host.

Stopping the test bot **preserves** its test database. Restart `python bot.py --test` to continue exactly where it left off.

### Start a fresh test run

Stop the TEST process first, then change the test `season_key` (e.g. from `snowfall-sandbox-001` to `snowfall-sandbox-002`) in `config.test.toml` and restart. That starts a fresh isolated test season in the same TEST database. For a clean database, back up or rename *only* `data/test/snowfall-test.sqlite3` while the test process is fully stopped. **Never delete `data/snowfall.sqlite3` or your production `.env` / `config.toml`.**

## Test seven days without leaving the bot running for a week

```powershell
python bot.py --simulate
```

This executes 168 synthetic hours (18 fictional players, 126 PvP attacks, 252 PvE attempts, 42 city-day snapshots) in a **temporary** database and prints a scoring report. It does not load any Discord token or touch either real database. Run it before launch and after any changes to scoring.

## Before the real competition

Keep the TEST bot's server clearly labelled as TEST. Run `/snowadmin launch-check` in the production server, verify backup and dry run, and have Kat record `/snowadmin approve-launch confirmation:APPROVE reason:<detailed signoff>`. **The production `/snowadmin start` is blocked until approval is recorded**; the test server does not require that approval.
