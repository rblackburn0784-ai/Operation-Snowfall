"""Explicit PostgreSQL identity schema installer, separate from game migration."""
from __future__ import annotations

import argparse
import os

from snowfall.platform.identity import IdentityRepository


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Provision Snowfall v2.9.3 identity tables")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--dsn-env", default="SNOWFALL_DATABASE_URL")
    args = parser.parse_args(argv)
    dsn = os.getenv(args.dsn_env, "")
    if not dsn:
        parser.error("PostgreSQL DSN environment variable not configured")
    if args.install and os.getenv("SNOWFALL_PLATFORM_ENV") != "staging" and (
        os.getenv("SNOWFALL_ALLOW_IDENTITY_BOOTSTRAP_PRODUCTION") != "1"
    ):
        parser.error("Identity provisioning requires SNOWFALL_PLATFORM_ENV=staging")
    try:
        repo = IdentityRepository(dsn)
        if args.install:
            repo.provision(confirm=args.confirm)
        repo.check()
    except Exception as exc:
        parser.exit(2, "IDENTITY SETUP FAILED: " + type(exc).__name__ + "\n")
    print("IDENTITY SCHEMA v1 verified; v11 game schema retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
