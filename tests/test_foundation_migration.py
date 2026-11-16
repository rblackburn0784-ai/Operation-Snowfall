import sqlite3
from datetime import datetime, timezone

from snowfall.db.store import Store

T = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)


def test_unversioned_v010_database_migrates_without_losing_users(tmp_path):
    path = tmp_path / 'existing.sqlite3'
    con = sqlite3.connect(path)
    con.executescript('''
        CREATE TABLE players (id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_key TEXT NOT NULL, discord_user_id INTEGER NOT NULL,
            mr_username TEXT NOT NULL, mr_username_norm TEXT NOT NULL,
            city TEXT NOT NULL, joined_at_utc TEXT NOT NULL,
            review_state TEXT NOT NULL DEFAULT 'self_declared',
            UNIQUE(season_key,discord_user_id), UNIQUE(season_key,mr_username_norm));
        CREATE TABLE admin_audit (id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_key TEXT NOT NULL, actor_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL, action TEXT NOT NULL,
            reason TEXT NOT NULL, created_at_utc TEXT NOT NULL);
        INSERT INTO players(season_key,discord_user_id,mr_username,mr_username_norm,city,joined_at_utc)
            VALUES('2026',123,'TheDude','thedude','Chicago','2026-12-01T00:00:00+00:00');
    ''')
    con.close()
    db = Store(path)
    db.initialize()
    db.initialize()  # migration may be retried on restart
    assert db.schema_version() == 5
    assert db.get_player('2026', 123).mr_username == 'TheDude'
    assert db.ensure_season('2026', T).planned_start == T
    with db.connect() as con:
        assert con.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert con.execute('PRAGMA quick_check').fetchone()[0] == 'ok'


def test_migration_rejects_newer_schema(tmp_path):
    path = tmp_path / 'future.sqlite3'
    con = sqlite3.connect(path)
    con.execute('PRAGMA user_version=99')
    con.close()
    db = Store(path)
    try:
        db.initialize()
    except RuntimeError as exc:
        assert 'newer' in str(exc)
    else:
        raise AssertionError('Downgrading a newer schema must be refused')
