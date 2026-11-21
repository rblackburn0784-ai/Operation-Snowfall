"""v2.9.4b: the original /snow engine and website write the same PostgreSQL rows.

Runs only with a disposable localhost PostgreSQL CI fixture. No Railway access,
real Discord tokens, private account data or live guild connections are needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from snowfall.db.migrate_postgres import migrate
from snowfall.db.postgres import PostgresStore
from snowfall.platform.game import SharedGame
from snowfall.platform.identity import IdentityRepository
from snowfall.platform.staging import STAGING_PROJECT, StagingGame, _source_snapshot
from snowfall.platform.unified_discord import (
    QA_SEASON, UnifiedDiscordStore, verify_qa_database,
)
from snowfall.services.economy import EconomyEngine
from snowfall.services.world import WorldEngine


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable localhost PostgreSQL explicitly required")
def test_existing_snow_engines_share_website_progress(tmp_path):
    import psycopg
    from psycopg import sql

    admin_dsn = os.environ["SNOWFALL_PG_TEST_DSN"]
    parts = urlsplit(admin_dsn)
    if parts.hostname not in ("localhost", "127.0.0.1") or parts.path != "/snowfall_test":
        pytest.fail("Refusing any database except ephemeral localhost CI fixture")
    name = "snowfall_v294b_existing_bot_test"
    dsn = urlunsplit(parts._replace(path="/" + name))
    with psycopg.connect(admin_dsn, autocommit=True) as root:
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        source = tmp_path / "seed.sqlite3"
        _source_snapshot(source, QA_SEASON)
        migrate(source, dsn, confirmation="OFFLINE_MIGRATE")
        with psycopg.connect(dsn) as conn:
            conn.execute("""CREATE TABLE snowfall_web_qa_marker(
                singleton INT PRIMARY KEY CHECK(singleton=1),
                project_id TEXT NOT NULL, season_key TEXT NOT NULL)""")
            conn.execute(
                "INSERT INTO snowfall_web_qa_marker VALUES(1,%s,%s)",
                (STAGING_PROJECT, QA_SEASON))
            conn.execute("""CREATE TABLE snowfall_web_qa_bonus(
                player_id BIGINT PRIMARY KEY,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        ids = IdentityRepository(dsn)
        ids.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        verify_qa_database(dsn)
        actor = 123456789012345678
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        principal = ids.resolve_underworld(
            "one-underworld-account", "one-character", "one-login", expiry)
        web_store = PostgresStore(dsn, practice_root=tmp_path)
        web = StagingGame(SharedGame(web_store, QA_SEASON))
        web.register(principal, "LinkedSnowballer", "Chicago")
        ids.link_discord(principal, str(actor))

        # Original /snow handlers call the original EconomyEngine; the
        # database adapter maps the verified Discord ID to the high player ID.
        discord_store = UnifiedDiscordStore(dsn, practice_root=tmp_path)
        discord_store.initialize()
        beginning = web.progress(principal)
        assert beginning["player_id"] == str(principal)
        assert beginning["snowflakes"] == 60
        now = datetime.now(timezone.utc)
        legacy_inv = EconomyEngine(discord_store).inventory(QA_SEASON, actor, now)
        assert legacy_inv.snowflakes == beginning["snowflakes"]

        craft = EconomyEngine(discord_store).craft(
            QA_SEASON, actor, "cocoa", "discord-v294b-1001", now)
        assert not craft.repeated
        after_discord = web.progress(principal)
        assert after_discord["snowflakes"] == beginning["snowflakes"] - 8
        assert after_discord["inventory"]["cocoa"] == (
            beginning["inventory"]["cocoa"] + 1)
        duplicate = EconomyEngine(discord_store).craft(
            QA_SEASON, actor, "cocoa", "discord-v294b-1001", now)
        assert duplicate.repeated
        assert web.progress(principal) == after_discord

        # The web command is visible immediately to the *legacy* Discord
        # economy menus, without an ETL, second player or mirroring job.
        web_craft = web.craft(principal, "fort", "web-v294b-1002", now=now)
        assert not web_craft["repeated"]
        discord_inv = EconomyEngine(discord_store).inventory(QA_SEASON, actor, now)
        assert discord_inv.quantities["fort"] == (
            after_discord["inventory"]["fort"] + 1)
        assert discord_inv.snowflakes == after_discord["snowflakes"] - 10

        # Original /snow boss and the web share Snow Don HP, ammunition
        # and the authoritative ledger in this same season.
        boss = WorldEngine(discord_store).attack(
            QA_SEASON, actor, "boss", "discord-v294b-1003", now)
        status = web.progress(principal)
        assert status["boss_hp"] == boss.hp_after
        assert status["snowflakes"] == discord_inv.snowflakes
        assert status["player_id"] == str(principal)
        assert WorldEngine(discord_store).attack(
            QA_SEASON, actor, "boss", "discord-v294b-1003", now).repeated
        assert web.progress(principal) == status

        with psycopg.connect(dsn) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM players WHERE discord_user_id=%s",
                (principal,)).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM players WHERE discord_user_id=%s",
                (actor,)).fetchone()[0] == 0
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as root:
            root.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()", (name,))
            root.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
                sql.Identifier(name)))
