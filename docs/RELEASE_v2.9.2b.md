# v2.9.2b — Staging raid compatibility and deeper validation

Snow Don raid queries used SQLite's rowid pseudo-column, unsupported by
PostgreSQL. Both raid history and final-result replay now sort by effective
timestamp, happened timestamp and interaction ID, for deterministic ordering.

The disposable PostgreSQL integration test now defeats a Snow Don, reads the
raid report and final result, and verifies replay-safe damage.

The optional separate Python staging smoke harness validates the migrated
SQLite snapshot, then creates a new disposable database in the same staging
PostgreSQL instance for fully isolated, populated gameplay and rollback tests.

Never merge or deploy this branch to the live Discord service before staging
sign-off. No Railway production variables or volumes were changed.
