# Operation Snowfall v2.9.1 — Railway Hosting Foundation

## Scope

A deployment-focused release for **the existing Discord game**. It does not
implement a web interface, HTTP API, PostgreSQL, account linking or Underworld
integration. All combat, progression, cosmetics, graphics and prize rules remain
in the established services.

## Implementation

- Replace the production Dockerfile's launch command with `python -m snowfall.railway`.
- Build a temporary `config.toml` from validated Railway service variables.
  `DISCORD_TOKEN` remains only in the process environment, not in the file.
- Require the **attached Railway persistent volume** before opening SQLite.
  The database is `VOLUME/snowfall.sqlite3`; backups and practice files are on
  the same volume and survive restarts.
- Read-only SQLite integrity check before opening existing data.
- Create verified, WAL-consistent prestart backup if the last backup is older
  than 12 hours; existing daily backups continue. A failed backup blocks boot.
- Advisory Linux file lock prevents accidentally running two workers against
  the same SQLite volume (does not prevent a copy on an independent machine).
- Add explicit validation command (`python -m snowfall.railway --check`).
- Add Railway-specific docs, environment template, `.dockerignore`, tests.
- Bump package version from `2.9.0a` to `2.9.1`.

## Non-goals

- **No live deployment** by the installer. You must connect GitHub to Railway
  and supply your credentials and server settings privately.
- **No public website or Railway domain** is needed for the Discord worker.
- **No database migration** and no independent second worker sharing SQLite.

## Release checks

Run the old 343-test suite and the new v2.9.1 tests locally and verify that
GitHub Actions passes on Linux and Windows. Do not run two live bots with the
same token. Keep off-platform copies of your database before moving hosting.

See `docs/RAILWAY_SETUP_v2.9.1.md` for the deployment walkthrough.
