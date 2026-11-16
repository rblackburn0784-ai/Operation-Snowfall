# v0.1.6 — Milestone F: Testing, Safety & Launch Preparation

## Implemented (six tickets + isolated test mode)

- **SNOW-026:** Finalised-only, staff-only individual prize CSV; audited manual reward description/status, immutable rank snapshot; city awards excluded.
- **SNOW-027:** Signed compensating score ledger entries with unique interaction IDs and reasons, fraud/claim reviews, score reconciliation; original game events never overwritten.
- **SNOW-028:** Consistent online SQLite backup via backup API, SHA256 manifest, daily automatic backups plus host/manual command, health diagnostics, explicitly confirmed offline restore with safety copy.
- **SNOW-029:** Disposable seven-effective-day simulator and integration tests for score caps, state persistence, migrations, privileges, idempotence and recovery.
- **SNOW-030:** Host `/snowadmin launch-check`, audited `/snowadmin approve-launch`, production start gate, dry-run and manual Kat sign-off checklist.
- **SNOW-031:** Explicit privacy, dispute and moderation document and `/snow privacy`. Kat must choose and publish the real retention date; deletion is manual.
- **New test controls:** `python bot.py --test` starts a separate Discord TEST application on a separate guild and separate database; `/snowadmin test-stop confirmation:STOP_TEST` stops **only TEST**, while Ctrl+C works too. `starts_at_utc = "AUTO"` in `config.test.toml` seeds an immediately startable test kickoff. `python bot.py --simulate` performs a seven-day offline dry run requiring no tokens.

**Schema version 6:** additive `launch_approvals` and `prize_awards` tables. Old game and player records are preserved. No adjustments to historical attack, item or PvE data.

## PyCharm update

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py --simulate
python bot.py
```

**Back up the live `data/snowfall.sqlite3` before running the new code.** Keep `.env` and `config.toml` local; never commit tokens or participant data.

## Test startup/shutdown

See [TEST_MODE_v0.1.6.md](TEST_MODE_v0.1.6.md) for the exact second Discord bot + second server setup, `DISCORD_TEST_TOKEN`, `config.test.toml`, start/stop commands and test-season rollover.

## New admin commands

`/snowadmin launch-check`, `approve-launch`, `test-stop`, `backup`, `reconcile`, `adjust-score`, `export-prizes`, `prize-status`.

- Test-stop is **hard-blocked on production**.
- Production `/snowadmin start` is blocked until an audited Kat/host approval exists; practice start is exempt.
- Final individual awards require a finalised season and passing reconciliation. Staff must manually deliver any MR perks/credits.
- `python bot.py --backup-now` creates a verified backup and exits. `python bot.py --restore PATH --confirm-restore RESTORE` performs an **offline-only** verified restore with pre-restore safety backup. Never use during a running instance.

## Remaining external gates

Discord gateway operation and message permissions must be verified on the actual servers. An organiser must approve dates, published retention schedule, individual prize values and rules. Passing CI is not a substitute for this signoff. Do not advertise prize completion or live Discord deployment until those steps are done.
