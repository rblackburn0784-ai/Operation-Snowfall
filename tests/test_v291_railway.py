"""v2.9.1 Railway worker configuration and safe local-disk lifecycle contracts."""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tomllib

import pytest

from snowfall import railway


@pytest.fixture
def valid_env(tmp_path):
    return {
        "DISCORD_TOKEN": "SUPER_SECRET_NOT_TO_BE_PRINTED",
        "SNOWFALL_GUILD_ID": "123456789123456789",
        "SNOWFALL_ADMIN_USER_IDS": "111111111111111111,222222222222222222",
        "SNOWFALL_STAFF_ROLE_IDS": "333333333333333333",
        "SNOWFALL_ANNOUNCEMENT_CHANNEL_ID": "444444444444444444",
        "SNOWFALL_LEADERBOARD_CHANNEL_ID": "555555555555555555",
        "SNOWFALL_STARTS_AT_UTC": "2026-12-20T19:00:00+00:00",
        "SNOWFALL_SEASON_KEY": "christmas-2026",
        "SNOWFALL_DATA_DIR": str(tmp_path),
    }


def test_config_round_trip_and_does_not_include_token(valid_env, tmp_path):
    config, db, backups, season = railway.configuration(valid_env)
    parsed = tomllib.loads(config)
    assert db == tmp_path / "snowfall.sqlite3"
    assert backups == tmp_path / "backups"
    assert season == "christmas-2026"
    assert parsed["discord"]["admin_user_ids"] == [111111111111111111, 222222222222222222]
    assert parsed["discord"]["staff_role_ids"] == [333333333333333333]
    assert parsed["event"]["identity_mode"] == "self_declaration"
    assert parsed["event"]["prize_mode"] == "individual_only"
    assert parsed["event"]["city_championship"] == "bragging_rights_only"
    assert parsed["storage"]["database_path"] == str(tmp_path / "snowfall.sqlite3")
    assert "SUPER_SECRET" not in config


def test_missing_token_and_admins_rejected(valid_env):
    for field in ("DISCORD_TOKEN", "SNOWFALL_ADMIN_USER_IDS", "SNOWFALL_GUILD_ID"):
        env = {**valid_env, field: ""}
        with pytest.raises(railway.RailwayConfigurationError):
            railway.configuration(env)


def test_railway_requires_volume_and_uses_attached_path(valid_env, tmp_path):
    env = {**valid_env, "RAILWAY_PROJECT_ID": "some-railway-project"}
    with pytest.raises(railway.RailwayConfigurationError, match="volume"):
        railway.configuration(env)
    env["RAILWAY_VOLUME_MOUNT_PATH"] = str(tmp_path)
    assert railway.configuration(env)[1] == tmp_path / "snowfall.sqlite3"
    env["SNOWFALL_DATA_DIR"] = str(tmp_path / "different")
    with pytest.raises(railway.RailwayConfigurationError, match="differs"):
        railway.configuration(env)


def test_channel_overlap_rejected(valid_env):
    env = {**valid_env, "SNOWFALL_LEADERBOARD_CHANNEL_ID": valid_env["SNOWFALL_ANNOUNCEMENT_CHANNEL_ID"]}
    with pytest.raises(railway.RailwayConfigurationError, match="different"):
        railway.configuration(env)


@pytest.mark.parametrize("bad_start", ["2026-12-20T19:00:00", "tomorrow", "2026-12-20T20:00:00+01:00"])
def test_start_date_must_be_utc(valid_env, bad_start):
    with pytest.raises(railway.RailwayConfigurationError, match="UTC"):
        railway.configuration({**valid_env, "SNOWFALL_STARTS_AT_UTC": bad_start})


def test_storage_check_does_not_create_or_modify_database(valid_env):
    _, db, _, _ = railway.configuration(valid_env)
    railway.check_storage(db)
    assert not db.exists()
    with closing(sqlite3.connect(db)) as con:
        con.execute("CREATE TABLE preserve_me (value INTEGER NOT NULL)")
        con.execute("INSERT INTO preserve_me VALUES (42)")
        con.commit()
    railway.check_storage(db)
    with closing(sqlite3.connect(db)) as con:
        assert con.execute("SELECT value FROM preserve_me").fetchone()[0] == 42


def test_empty_existing_database_rejected(valid_env):
    _, db, _, _ = railway.configuration(valid_env)
    db.touch()
    with pytest.raises(railway.RailwayConfigurationError, match="empty"):
        railway.check_storage(db)


def test_check_mode_hides_secret_and_does_not_start_discord(valid_env, monkeypatch, capsys):
    monkeypatch.setattr(os, "environ", valid_env)
    assert railway.main(["--check"]) == 0
    output = capsys.readouterr()
    assert "token=present (hidden)" in output.out
    assert valid_env["DISCORD_TOKEN"] not in output.out + output.err


def test_volume_lock_blocks_duplicate_worker(valid_env):
    data = Path(valid_env["SNOWFALL_DATA_DIR"])
    if os.name != "posix":
        pytest.skip("advisory lock is enforced by Linux Railway containers")
    with railway.one_instance(data):
        with pytest.raises(railway.RailwayConfigurationError, match="Another Snowfall worker"):
            with railway.one_instance(data):
                pass
    with railway.one_instance(data):
        pass


def test_bad_season_and_blank_csv_item_rejected(valid_env):
    for env in (
        {**valid_env, "SNOWFALL_SEASON_KEY": "../not-a-season"},
        {**valid_env, "SNOWFALL_ADMIN_USER_IDS": "123,"},
    ):
        with pytest.raises(railway.RailwayConfigurationError):
            railway.configuration(env)
