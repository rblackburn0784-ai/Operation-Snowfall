"""v2.9.4e1 — guarded ONE-worker cutover, lossless SQLite backup and rollback.

Fixtures never touch real Railway, Discord or database credentials.
"""
from __future__ import annotations

from contextlib import closing
import sqlite3

import pytest

from snowfall.ops import check_backup
from snowfall import railway
from snowfall.platform.unified_discord import (
    EXISTING_BOT_PROJECT, EXISTING_BOT_SERVICE, UnifiedConfigurationError,
    validate_unified_environment,
)


@pytest.fixture
def bot_env(tmp_path):
    return {
        "DISCORD_TOKEN": "fake-test-only-token-never-output",
        "RAILWAY_PROJECT_ID": EXISTING_BOT_PROJECT,
        "RAILWAY_SERVICE_ID": EXISTING_BOT_SERVICE,
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path),
        "SNOWFALL_GUILD_ID": "123456789123456789",
        "SNOWFALL_ADMIN_USER_IDS": "111111111111111111",
        "SNOWFALL_STARTS_AT_UTC": "2026-12-20T19:00:00+00:00",
        "SNOWFALL_SEASON_KEY": "web-qa-2026",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_SHARED_MODE": "qa",
        "SNOWFALL_DATABASE_URL":
            "postgresql://qa:password@junction.proxy.rlwy.net:21957/"
            "snowfall_web_qa?sslmode=require",
    }


def sqlite_game(tmp_path):
    db = tmp_path / "snowfall.sqlite3"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE sacred_original_state (text TEXT NOT NULL)")
        conn.execute("INSERT INTO sacred_original_state VALUES ('original SQLite safe')")
        conn.commit()
    return db


def test_qa_cross_project_proxy_requires_tls_and_exact_target(bot_env):
    assert validate_unified_environment(bot_env) == bot_env["SNOWFALL_DATABASE_URL"]
    assert railway.configuration(bot_env)[-1] == "web-qa-2026"
    bad_dsns = [
        "postgresql://qa:pw@postgres.internal/railway",
        "postgresql://qa:pw@junction.proxy.rlwy.net:21957/railway?sslmode=require",
        "postgresql://qa:pw@junction.proxy.rlwy.net:21957/snowfall_web_qa",
        "postgresql://qa:pw@junction.proxy.rlwy.net:21957/snowfall_web_qa?sslmode=disable",
        "postgresql://qa:pw@junction.proxy.rlwy.net:9999/snowfall_web_qa?sslmode=require",
        "postgresql://qa:pw@other.proxy.rlwy.net:21957/snowfall_web_qa?sslmode=require",
    ]
    for bad in bad_dsns:
        with pytest.raises(UnifiedConfigurationError):
            validate_unified_environment({**bot_env, "SNOWFALL_DATABASE_URL": bad})


def test_original_bot_refuses_unsafe_postgres_rollback(bot_env):
    bad = dict(bot_env)
    bad.pop("SNOWFALL_SHARED_MODE")
    with pytest.raises(railway.RailwayConfigurationError,
                       match="without guarded shared QA"):
        railway.configuration(bad)
    bad["SNOWFALL_DB_BACKEND"] = "sqlite"
    assert railway.configuration(bad)[-1] == "web-qa-2026"


def test_fresh_cutover_backup_is_verified_durable_and_never_overwritten(tmp_path):
    db = sqlite_game(tmp_path)
    backups = tmp_path / "backups"
    saved = railway.cutover_backup(db, backups)
    manifest = check_backup(saved)
    assert manifest["source_name"] == "snowfall.sqlite3"
    assert (backups / "v294e1-original-sqlite-backup.txt").read_text().strip() == saved.name
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("UPDATE sacred_original_state SET text='changed after cutoff'")
        conn.commit()
    saved_again = railway.cutover_backup(db, backups)
    assert saved_again == saved
    with closing(sqlite3.connect(saved)) as conn:
        original = conn.execute("SELECT text FROM sacred_original_state").fetchone()[0]
    assert original == "original SQLite safe"
    with closing(sqlite3.connect(db)) as conn:
        current = conn.execute("SELECT text FROM sacred_original_state").fetchone()[0]
    assert current == "changed after cutoff"
    # A failed, missing backup must NEVER silently be replaced after the
    # original profile has already been connected to Postgres.
    saved.unlink()
    with pytest.raises(railway.RailwayConfigurationError, match="missing"):
        railway.cutover_backup(db, backups)


def test_missing_or_corrupted_original_sqlite_is_not_an_acceptable_cutover(tmp_path):
    backups = tmp_path / "backups"
    with pytest.raises(railway.RailwayConfigurationError, match="missing"):
        railway.cutover_backup(tmp_path/"snowfall.sqlite3", backups)
    db = sqlite_game(tmp_path)
    backup = railway.cutover_backup(db, backups)
    backup.write_bytes(b"corrupted backup")
    with pytest.raises(ValueError):
        railway.cutover_backup(db, backups)


def test_qa_check_mode_never_opens_discord_or_logs_secret(bot_env, monkeypatch, capsys,
                                                         tmp_path):
    sqlite_game(tmp_path)
    called = []
    def fake_preflight(env):
        called.append(env["SNOWFALL_SEASON_KEY"])
    monkeypatch.setattr(railway, "verify_shared_qa_preflight", fake_preflight)
    monkeypatch.setattr(railway.os, "environ", bot_env)
    result = railway.main(["--check"])
    assert result == 0
    output = capsys.readouterr()
    assert "shared_qa=ready" in output.out
    assert "token=present (hidden)" in output.out
    assert "password" not in output.out+output.err
    assert bot_env["DISCORD_TOKEN"] not in output.out+output.err
    assert called == ["web-qa-2026"]
    assert not (tmp_path/"backups").exists()


def test_preflight_fails_closed_when_target_database_cannot_be_verified(bot_env,
                                                                       monkeypatch):
    from snowfall.platform import unified_discord
    def rejected(*args, **kwargs):
        raise RuntimeError("Sensitive connection string: fake password")
    monkeypatch.setattr(unified_discord, "verify_qa_database", rejected)
    with pytest.raises(railway.RailwayConfigurationError) as excinfo:
        railway.verify_shared_qa_preflight(bot_env)
    assert "password" not in str(excinfo.value)
    assert "Shared QA PostgreSQL connection or schema verification failed" in str(
        excinfo.value)


def test_original_bot_registers_shared_commands_in_same_single_client():
    import inspect
    from snowfall import app
    src = inspect.getsource(app.SnowfallBot.setup_hook)
    assert "self.tree.add_command(SnowBridgeGroup(" in src
    assert "self.unified_gateway" in src
    from snowfall.platform.discord_bridge import SnowBridgeGroup
    assert "verify" in {cmd.name for cmd in SnowBridgeGroup(None, 123456789123456789).commands}
