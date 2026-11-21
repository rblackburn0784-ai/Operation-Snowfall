"""v2.9.4b: one existing Discord client, isolated database and link-safe mapping."""
from __future__ import annotations

import pytest

from snowfall.platform.unified_discord import (
    EXISTING_BOT_PROJECT, EXISTING_BOT_SERVICE, MappedConnection, QA_SEASON,
    UnifiedConfigurationError, UnifiedDiscordStore, validate_unified_environment,
)
from snowfall.railway import configuration


def qa_env(tmp_path):
    return {
        "DISCORD_TOKEN": "the-existing-discord-token-never-reveal",
        "RAILWAY_PROJECT_ID": EXISTING_BOT_PROJECT,
        "RAILWAY_SERVICE_ID": EXISTING_BOT_SERVICE,
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path),
        "SNOWFALL_SHARED_MODE": "qa",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_DATABASE_URL":
            "postgresql://snowfall:private@postgres.internal/snowfall_web_qa",
        "SNOWFALL_GUILD_ID": "123456789123456789",
        "SNOWFALL_ADMIN_USER_IDS": "111111111111111111",
        "SNOWFALL_SEASON_KEY": QA_SEASON,
        "SNOWFALL_STARTS_AT_UTC": "2026-12-20T19:00:00+00:00",
    }


def test_qa_uses_existing_railway_worker_not_separate_bot(tmp_path):
    env = qa_env(tmp_path)
    assert validate_unified_environment(env) == env["SNOWFALL_DATABASE_URL"]
    content, db, backups, season = configuration(env)
    assert season == QA_SEASON
    assert db == tmp_path / "snowfall.sqlite3"
    assert "the-existing-discord-token-never-reveal" not in content
    assert "SNOWFALL_DISCORD_BRIDGE_TOKEN" not in content


@pytest.mark.parametrize("change", [
    {"RAILWAY_PROJECT_ID": "separate-qa-project"},
    {"RAILWAY_SERVICE_ID": "another-bot-service"},
    {"RAILWAY_ENVIRONMENT_NAME": "staging"},
    {"SNOWFALL_SEASON_KEY": "christmas-2026"},
    {"SNOWFALL_DB_BACKEND": "sqlite"},
    {"SNOWFALL_DATABASE_URL": "postgresql://snowfall:secret@localhost/railway"},
    {"SNOWFALL_DATABASE_URL":
        "postgresql://snowfall:secret@localhost/christmas_2026"},
    {"SNOWFALL_DISCORD_BRIDGE_ENABLED": "1"},
    {"SNOWFALL_DISCORD_BRIDGE_TOKEN": "second-bot-token"},
    {"SNOWFALL_SHARED_MODE": "production"},
])
def test_unified_mode_refuses_unsafe_cutovers(tmp_path, change):
    with pytest.raises(UnifiedConfigurationError):
        validate_unified_environment({**qa_env(tmp_path), **change})


def test_disabled_mode_is_backwards_compatible(tmp_path):
    env = qa_env(tmp_path)
    env.pop("SNOWFALL_SHARED_MODE")
    env["SNOWFALL_DB_BACKEND"] = "sqlite"
    env["SNOWFALL_SEASON_KEY"] = "christmas-2026"
    assert validate_unified_environment(env) is None
    assert configuration(env)[-1] == "christmas-2026"


class FakeCursor:
    def __init__(self, rows=()):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "snowfall_identity_links" in sql:
            return FakeCursor([
                ("123456789012345678", 6_000_000_000_000_000_003),
                ("234567890123456789", 6_000_000_000_000_000_004),
            ])
        return FakeCursor()


def test_sql_binding_maps_only_linked_discord_user_ids():
    db = FakeConnection()
    conn = MappedConnection(db)
    assert len(db.calls) == 1  # One authoritative mapping snapshot per transaction.
    conn.execute("SELECT * FROM players WHERE discord_user_id=?",
                 ("web-qa-2026", 123456789012345678, 910001))
    assert db.calls[-1][1] == ("web-qa-2026", 6_000_000_000_000_000_003, 910001)
    conn.execute("INSERT INTO score_ledger VALUES(?, ?, ?)",
                 (234567890123456789, "123456789012345678", True))
    assert db.calls[-1][1] == (
        6_000_000_000_000_000_004, "123456789012345678", True)
    conn.execute("SELECT %s", {"actor": 123456789012345678, "text": "123456789012345678"})
    assert db.calls[-1][1] == {
        "actor": 6_000_000_000_000_000_003, "text": "123456789012345678"}


def test_unified_store_does_not_mutate_base_web_adapter():
    from snowfall.db.postgres import PostgresStore
    assert issubclass(UnifiedDiscordStore, PostgresStore)
    assert UnifiedDiscordStore.unified_discord
    assert not getattr(PostgresStore, "unified_discord", False)
