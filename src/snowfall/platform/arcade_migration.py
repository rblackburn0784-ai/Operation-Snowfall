"""Install independent v2.9.9/v2.9.9a arcade tables into isolated QA PostgreSQL.

Never runs at app startup. Run only against a verified STAGING database:
    python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY
"""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlsplit

from snowfall.platform.staging import QA_DB, STAGING_PROJECT

from snowfall.platform.interactive_arcade import install_practice_schema
from snowfall.platform.gallery_arcade import install_gallery_schema
from snowfall.platform.safecracker_arcade import install_safe_schema
from snowfall.platform.snowman_arcade import install_snowman_schema


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
    if urlsplit(dsn).path != "/" + QA_DB:
        parser.error("Refusing any database except the isolated /snowfall_web_qa database")
    from snowfall.db.postgres import PostgresStore

    store = PostgresStore(dsn, practice_root=__import__("pathlib").Path.cwd())
    store.initialize()  # Verify existing canonical game schema, no game migrations.
    with store.connect() as con:
        season = con.execute("SELECT season_key FROM season_state WHERE season_key=?",
                             ("web-qa-2026",)).fetchone()
        if not season:
            parser.error("No web-qa-2026 season found; refusing to install")
        marker = con.execute(
            "SELECT project_id,season_key FROM snowfall_web_qa_marker "
            "WHERE singleton=1").fetchone()
        if marker is None or tuple(marker) != (STAGING_PROJECT, "web-qa-2026"):
            parser.error("Refusing database without the verified Snowfall QA marker")
        install_practice_schema(con)
        install_gallery_schema(con)
        install_safe_schema(con)
        install_snowman_schema(con)
    print("Installed v2.9.9–v2.9.9c web-only arcade tables in web-qa-2026.")


if __name__ == "__main__":
    main()
