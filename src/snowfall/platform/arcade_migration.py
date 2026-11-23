"""Install the independent v2.9.9 practice table into isolated QA PostgreSQL.

Never runs at app startup. Run only against a verified STAGING database:
    python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY
"""
from __future__ import annotations

import argparse
import os

from snowfall.platform.interactive_arcade import install_practice_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Install isolated web arcade practice table")
    parser.add_argument("--confirm", required=True, choices=["WEB_QA_ONLY"])
    args = parser.parse_args()
    if args.confirm != "WEB_QA_ONLY" or os.environ.get(
            "SNOWFALL_API_SEASON_KEY") != "web-qa-2026":
        parser.error("Refusing non-QA environment; set SNOWFALL_API_SEASON_KEY=web-qa-2026")
    dsn = os.environ.get("SNOWFALL_DATABASE_URL", "")
    if not dsn.startswith(("postgres://", "postgresql://")):
        parser.error("SNOWFALL_DATABASE_URL must be a staging PostgreSQL URL")
    from snowfall.db.postgres import PostgresStore

    store = PostgresStore(dsn, practice_root=__import__("pathlib").Path.cwd())
    store.initialize()  # Verify existing canonical game schema, no game migrations.
    with store.connect() as con:
        season = con.execute("SELECT season_key FROM season_state WHERE season_key=?",
                             ("web-qa-2026",)).fetchone()
        if not season:
            parser.error("No web-qa-2026 season found; refusing to install")
        install_practice_schema(con)
    print("Installed v2.9.9 web practice schema in web-qa-2026 (no gameplay migration).")


if __name__ == "__main__":
    main()
