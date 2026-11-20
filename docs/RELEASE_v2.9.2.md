# Operation Snowfall v2.9.2 — Shared Database Upgrade

This release makes the existing **Discord game engine** capable of using a
PostgreSQL 16+ database. It includes an *offline*, transactional, read-only-source
migration from the complete **SQLite schema v11** and preserves event-history
triggers, anti-double-spend constraints, account records, scoring and resources.

**v2.9.2 does not build the web frontend, API or account linking.** Those are
future milestones. Do NOT point a web application directly at the database:
all state-changing actions must pass through the authoritative game engine.

## Default behaviour: no live change

The default is **SQLite**, even if a PostgreSQL URL is present. The existing
Railway /data volume and SQLite database continue to run unchanged unless you
set `SNOWFALL_DB_BACKEND=postgres` *and* supply `SNOWFALL_DATABASE_URL`.

A PostgreSQL target **must be empty**. Running the migrator against an existing
database (including Underworld's database) is refused. Nothing in this release
creates a PostgreSQL database, deploys a web process, or modifies Underworld.

## Verified offline migration procedure

1. In a staging environment, provision a **new, empty** PostgreSQL 16+ database
   exclusively for Snowfall. Enable managed backups and restrict external access.
2. Stop the **only live Discord worker** on Railway. Do not run the local bot
   against the same active event. Use a consistent source backup of
   `/data/snowfall.sqlite3` from the current volume (SQLite's online backup
   API). Transfer that standalone `.sqlite3` file securely to your local machine.
3. `python -m pip install -e ".[dev,postgres]"`
4. Inspect source: `python -m snowfall.db.migrate_postgres --sqlite PATH --inspect`
5. Supply the PostgreSQL DSN privately in environment variable
   `SNOWFALL_DATABASE_URL` (never put credentials in a command, screenshot,
   `.env` committed to GitHub or public logs).
6. Run the **destructive-to-empty-target only** offline copy:

   `python -m snowfall.db.migrate_postgres --sqlite PATH --migrate --confirm OFFLINE_MIGRATE`

7. Verify **all rows and all tables** independently:

   `python -m snowfall.db.migrate_postgres --sqlite PATH --verify`

   This reads both sides; it fails if anything in the authoritative source
   differs from the imported destination. The migration also verified before
   committing its single PostgreSQL transaction.
8. Test the new backend against a *separate staging Discord application and
   database*, not the prize-bearing live season. Use `SNOWFALL_DB_BACKEND=postgres`
   plus a Railway `${{Postgres.DATABASE_URL}}` reference on that staging worker.
9. Only after staging tests and recovery sign-off, stop the live worker, create
   one final consistent SQLite backup, import it into a **fresh empty target**,
   verify it, then change the single production worker to PostgreSQL and restart.
   Never split active players between two independently writable stores.

**Rollback:** Stop all PostgreSQL-backed workers before switching back to the
unchanged pre-cutover SQLite source. If game actions occurred on PostgreSQL after
the cutover, rolling back would lose those actions and is NOT automatic: first
reconcile the data and coordinate with the organiser.

## Immutable history and concurrency

- PostgreSQL tables, indexes, unique constraints and immutable event triggers
  are generated from the verified existing v11 SQLite schema.
- The arcade session progression trigger is ported as an explicit PostgreSQL
  function that rejects changes to identity fields or reductions in progress.
- Existing `BEGIN IMMEDIATE` game transactions use PostgreSQL transaction-level
  advisory locks. Both the Discord worker and future web API must share this
  adapter/lock key before any cross-platform writes are enabled.
- Historical Discord IDs remain unchanged as database keys in v2.9.2. v2.9.4
  introduces platform-independent account IDs and verified linking.

## Testing and operation

`python -m ruff check src tests --select E4,E7,E9,F`

`python -m pytest -q`

For real PostgreSQL integration tests use an empty **disposable** PostgreSQL
instance, not a shared production database, and set both:

- `SNOWFALL_PG_TEST_DSN` (temporary test database URL)
- `SNOWFALL_PG_TEST_CONFIRM=EMPTY_TEST_DATABASE`

The test will refuse a nonempty PostgreSQL target. An additional GitHub Actions
job provisions disposable PostgreSQL for automatic CI checks.

PostgreSQL backups must be configured separately (Railway volume backups plus
protected off-platform exports). The old SQLite backup loop is not run when the
PostgreSQL backend is selected. The local `/data` Railway volume remains mounted
for temporary practice test-day databases during v2.9.2.

## PostgreSQL grouping compatibility

The release also corrects the player leaderboard, social arcade leaderboard,
community daily ranking and Snowfall Wire's top-player query to group by the
primary key of the joined player. PostgreSQL requires this for non-aggregated
player fields; SQLite accepts both query forms. Rankings and prize calculations
remain unchanged.
