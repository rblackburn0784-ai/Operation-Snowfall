"""Real PostgreSQL identity tests ONLY on the disposable GitHub CI database.

This test creates an isolated database and drops it on completion. Never run
against a live service or a populated staging database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from snowfall.db.store import Store
from snowfall.db.migrate_postgres import MigrationError, migrate, verify
from snowfall.db.postgres import PostgresStore
from snowfall.platform.identity import IdentityConflict, IdentityError, IdentityRepository
from snowfall.platform.game import SharedGame


@pytest.mark.skipif(not os.getenv("SNOWFALL_PG_TEST_DSN") or
                    os.getenv("SNOWFALL_PG_TEST_CONFIRM") != "EMPTY_TEST_DATABASE",
                    reason="Disposable PostgreSQL CI database explicitly required")
def test_real_postgres_platform_principals_sessions_and_shared_scores(tmp_path):
    import psycopg
    admin_dsn = os.environ["SNOWFALL_PG_TEST_DSN"]
    url = urlsplit(admin_dsn)
    if url.hostname not in ("localhost", "127.0.0.1") or url.path != "/snowfall_test":
        pytest.fail("Refusing non-CI PostgreSQL host or database")
    test_dsn = urlunsplit(url._replace(path="/snowfall_v293_platform_test"))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute("CREATE DATABASE snowfall_v293_platform_test")
    try:
        source = tmp_path / "source.sqlite3"
        store = Store(source)
        store.initialize()
        start = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
        store.ensure_season("shared-test", start)
        store.register("shared-test", 101, "DiscordOriginal", "Chicago", start)
        with store.connect() as con:
            con.execute("""INSERT INTO score_ledger
                (season_key,day,player_id,city,category,points,source_key,created_at_utc)
                VALUES(?,?,?,?,?,?,?,?)""",
                ("shared-test", 1, 101, "Chicago", "manual", 9,
                 "original-progress", start.isoformat()))
        assert migrate(source, test_dsn, confirmation="OFFLINE_MIGRATE")["rows"] >= 3
        assert verify(source, test_dsn)["matching"]
        identities = IdentityRepository(test_dsn)
        with pytest.raises(IdentityError):
            identities.provision(confirm="wrong")
        identities.provision(confirm="INSTALL_IDENTITY_SCHEMA")
        identities.check()
        # External verified Discord login must reuse legacy game ID and score.
        assert identities.resolve_discord("101") == 101
        assert identities.principal_for_discord("101") == 101
        with pytest.raises(IdentityError):
            identities.principal_for_discord("404")
        game = SharedGame(PostgresStore(test_dsn, practice_root=tmp_path), "shared-test")
        assert game.me(101, now=start)["score"] == 9
        # Underworld account has exactly one character, no second identity.
        exp = datetime.now(timezone.utc) + timedelta(minutes=1)
        new_id = identities.resolve_underworld("underworld-acct-42", "character-5",
                                               "nonce-1", exp)
        assert new_id >= 6_000_000_000_000_000_000
        with pytest.raises(IdentityError, match="already used"):
            identities.resolve_underworld("underworld-acct-42", "character-5", "nonce-1", exp)
        assert identities.resolve_underworld("underworld-acct-42", "character-5",
                                             "nonce-2", exp) == new_id
        with pytest.raises(IdentityConflict, match="different character"):
            identities.resolve_underworld("underworld-acct-42", "character-6",
                                          "nonce-3", exp)
        with pytest.raises(IdentityConflict):
            identities.link_discord(new_id, "101")  # Existing player has history.
        identities.link_discord(new_id, "202")
        assert identities.resolve_discord("202") == new_id
        assert identities.principal_for_discord("202") == new_id
        assert identities.links(new_id) == [
            {"provider": "discord", "subject": "202"},
            {"provider": "underworld", "subject": "character-5"},
        ]
        session, csrf = identities.new_session(new_id)
        assert identities.session(session).player_id == new_id
        assert identities.session(session).csrf == csrf
        assert identities.csrf_ok(session, csrf)
        assert not identities.csrf_ok(session, "incorrect")
        oauth = identities.new_oauth_state("link", session, "pkce-verifier")
        assert identities.consume_oauth_state(oauth, session) == (
            "link", new_id, "pkce-verifier")
        with pytest.raises(IdentityError):
            identities.consume_oauth_state(oauth, session)
        identities.revoke(session)
        assert identities.session(session) is None
        # All channels now access exactly the same game ledger by principal ID.
        new_profile = game.register(new_id, "UnderworldTester", "New York", now=start)
        assert new_profile["player_id"] == str(new_id)
        assert game.me(new_id, now=start)["registered"]
        assert game.leaderboard()[0]["player_id"] == "101"
        with pytest.raises(IdentityConflict):
            identities.link_discord(new_id, "101")
        # Identity tables do not alter the imported game tables.
        with pytest.raises(MigrationError, match='differs'):
            verify(source, test_dsn)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("""SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                             WHERE datname='snowfall_v293_platform_test' AND pid<>pg_backend_pid()""")
            admin.execute("DROP DATABASE IF EXISTS snowfall_v293_platform_test")
