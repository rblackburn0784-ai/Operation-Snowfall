# Schema migrations

The foundation DB currently bootstraps two tables with `CREATE TABLE IF NOT EXISTS`
in `store.py`. Before the full combat milestone, introduce numbered forward-only
migrations, add immutable score ledgers, and support backup-before-migrate.
