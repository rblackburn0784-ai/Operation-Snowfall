"""v2.9.9h — fail-closed QA arcade preflight, without credentials or mutations."""
from __future__ import annotations

from dataclasses import replace
import re
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from snowfall.platform.api import create_app
from snowfall.platform.arcade_hub import GAMES
from snowfall.platform.arcade_readiness import (
    ArcadeReadinessError, QA_TABLES, audit_arcade_qa, main, required_tables,
    safe_qa_dsn,
)
from snowfall.platform.staging import STAGING_PROJECT
from test_v293_platform import FakeIdentity, fake_settings

DSN = "postgresql://test:TOP_SECRET@localhost/snowfall_web_qa"
ENV = {"SNOWFALL_API_SEASON_KEY": "web-qa-2026"}
ALL_ON = {**ENV, **{g[5]: "1" for g in GAMES},
          "SNOWFALL_ARCADE_V299F_ENABLED": "1"}
BASE = {"status": "ready", "warnings": []}


class FakeReadOnlyConnection:
    def __init__(self, *, tables=(), marker=True, broken=None):
        self.tables = set(tables)
        self.marker = marker
        self.broken = broken or {}
        self.queries = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        self.queries.append((query, params))
        if query.startswith("SET TRANSACTION READ ONLY"):
            self.result = None
        elif "to_regclass" in query:
            table = str(params[0]).replace("public.", "")
            if table == "snowfall_web_qa_marker":
                self.result = (table if self.marker else None,)
            else:
                self.result = (table if table in self.tables else None,)
        elif query.startswith("SELECT project_id,season_key"):
            self.result = ((STAGING_PROJECT, "web-qa-2026")
                           if self.marker else None)
        else:
            match = re.search(r"FROM (web_arcade_[a-z_]+_sessions)", query)
            table = match.group(1) if match else ""
            kind = ("foreign_seasons" if "season_key<>%s" in query else
                    "orphans" if "LEFT JOIN players" in query else
                    "bad_scores" if "score NOT BETWEEN" in query else
                    "duplicate_active" if "HAVING COUNT(*)>1" in query else
                    "active" if "status IN ('active','paused')" in query else
                    "finished" if "status='finished'" in query else "sessions")
            self.result = (self.broken.get((table, kind), 0),)
        return self

    def fetchone(self):
        return self.result


def all_tables():
    return {name for values in QA_TABLES.values() for name in values}


def inspect(env, *, tables=(), marker=True, broken=None):
    connection = FakeReadOnlyConnection(tables=tables, marker=marker, broken=broken)
    result = audit_arcade_qa(DSN, env=env, connect=lambda: connection,
                             baseline=BASE)
    return result, connection.queries


def test_production_dsn_and_wrong_season_are_rejected_before_db_access():
    for dsn in (
        "postgresql://user:SECRET@localhost/railway",
        "postgresql://user:SECRET@localhost/snowfall_web_qa_2",
        "sqlite:///snowfall_web_qa",
        "https://user:SECRET@host/snowfall_web_qa",
        "not-a-connection-string",
    ):
        with pytest.raises(ArcadeReadinessError, match="isolated QA"):
            safe_qa_dsn(dsn, "web-qa-2026")
    with pytest.raises(ArcadeReadinessError, match="isolated QA"):
        safe_qa_dsn(DSN, "live-2026")
    safe_qa_dsn(DSN, "web-qa-2026")


def test_flags_only_require_tables_for_enabled_modes():
    assert required_tables(ENV) == ()
    assert required_tables({"SNOWFALL_ARCADE_V299D_ENABLED": "1"}) == ("catch",)
    assert required_tables(ALL_ON) == tuple(g[0] for g in GAMES)
    assert required_tables({"SNOWFALL_ARCADE_V299F_ENABLED": "1"}) == ()


def test_verified_all_five_schemas_produce_ready_read_only_report():
    report, queries = inspect(ALL_ON, tables=all_tables())
    assert report["status"] == "ready"
    assert report["version"] == "2.9.9h"
    assert report["enabled_modes"] == [g[0] for g in GAMES]
    assert report["hub_enabled"] and len(report["modes"]) == 5
    assert all(row["schema_ready"] and row["enabled"] for row in report["modes"])
    assert all(not row["sessions"] and not row["finished"] for row in report["modes"])
    assert queries[0][0] == "SET TRANSACTION READ ONLY"
    assert all(q.startswith(("SELECT", "SET TRANSACTION READ ONLY"))
               for q, _params in queries)
    assert "TOP_SECRET" not in str(report)


def test_disabled_games_can_be_absent_without_crashing_hub():
    report, _ = inspect(ENV)
    assert report["status"] == "ready_with_warnings"
    assert all(not row["enabled"] and not row["schema_ready"]
               for row in report["modes"])
    report, _ = inspect({**ENV, "SNOWFALL_ARCADE_V299F_ENABLED": "1"})
    assert report["status"] == "ready_with_warnings"
    assert any("all five" in text for text in report["warnings"])


def test_enabled_game_missing_schema_or_unique_index_is_blocked():
    for missing in ("web_arcade_gallery_sessions",
                    "web_arcade_gallery_shots", "idx_web_gallery_active"):
        report, _ = inspect({**ENV, "SNOWFALL_ARCADE_V299A_ENABLED": "1"},
                            tables=all_tables()-{missing})
        assert report["status"] == "blocked"
        assert "gallery enabled without complete QA schema" in report["blockers"]


@pytest.mark.parametrize("defect", [
    "foreign_seasons", "orphans", "bad_scores", "duplicate_active",
])
def test_integrity_failures_block_even_when_mode_flag_is_off(defect):
    table = QA_TABLES["trivia"][0]
    report, _ = inspect(ENV, tables=all_tables(), broken={(table, defect): 1})
    assert report["status"] == "blocked"
    assert any(text.startswith("trivia has") for text in report["blockers"])


def test_web_qa_with_second_discord_bridge_is_blocked():
    result, _ = inspect({**ALL_ON, "SNOWFALL_DISCORD_BRIDGE_ENABLED": "1"},
                        tables=all_tables())
    assert result["status"] == "blocked"
    assert any("second Discord bridge" in text for text in result["blockers"])


def test_wrong_marker_and_base_launch_audit_block_release():
    report, _ = inspect(ALL_ON, tables=all_tables(), marker=False)
    assert report["status"] == "blocked"
    assert any("marker" in msg for msg in report["blockers"])
    report = audit_arcade_qa(
        DSN, env=ENV,
        connect=lambda: FakeReadOnlyConnection(tables=all_tables()),
        baseline={"status": "blocked", "warnings": []},
    )
    assert report["status"] == "blocked"
    assert "Base QA launch audit reports blockers" in report["blockers"]


def test_cli_refuses_unconfirmed_and_hides_credentials(capsys, monkeypatch):
    with pytest.raises(SystemExit):
        main([])
    monkeypatch.setenv("SNOWFALL_DATABASE_URL",
                       "postgresql://admin:SECRET_EXAMPLE@localhost/railway")
    assert main(["--confirm", "READ_ONLY_ARCADE_QA"]) == 2
    captured = capsys.readouterr().out
    assert "SECRET_EXAMPLE" not in captured
    assert '"blocked"' in captured


def test_qa_api_rejects_discord_only_writes_but_allows_its_read_session(monkeypatch):
    identity = FakeIdentity()
    game = Mock()
    game.gallery_start.return_value = {"mode": "gallery", "session_id": "a"*32}
    game.arcade_hub.return_value = {
        "version": "2.9.9f", "player_id": "101", "modes": [],
    }
    cfg = replace(fake_settings(), season_key="web-qa-2026")
    with TestClient(create_app(cfg, identity=identity, game=game),
                    base_url="https://snowfall.example") as client:
        token, csrf = identity.new_session(101)
        client.cookies.set("snowfall_session", token)
        monkeypatch.setenv("SNOWFALL_ARCADE_V299A_ENABLED", "1")
        headers = {"X-Snowfall-CSRF": csrf, "X-Snowfall-Player": "101"}
        monkeypatch.setattr(identity, "links", lambda _pid: [
            {"provider": "discord", "subject": "123456789012345678"}])
        assert client.post("/v1/game/arcade/gallery/start",
                           headers=headers).status_code == 403
        game.gallery_start.assert_not_called()
        assert client.get("/v1/auth/session").status_code == 200
        monkeypatch.setattr(identity, "links", lambda _pid: [
            {"provider": "underworld", "subject": "character-one"}])
        assert client.post("/v1/game/arcade/gallery/start",
                           headers=headers).status_code == 200
        game.gallery_start.assert_called_once_with(101)
        assert client.post("/v1/game/arcade/gallery/start",
                           headers={**headers, "X-Snowfall-Player": "202"}).status_code == 409
        assert client.post("/v1/game/arcade/gallery/start",
                           headers={"X-Snowfall-CSRF": "invalid",
                                    "X-Snowfall-Player": "101"}).status_code == 403
        game.gallery_start.assert_called_once_with(101)
