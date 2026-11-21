"""v2.9.6 QA visual integration: original artwork and optional safe Discord link."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from snowfall.platform.api import APISettings
from snowfall.platform.staging import (
    QA_CONFIRM, STAGING_ENVIRONMENT, STAGING_PROJECT,
)
from snowfall.platform.staging_web import attach_web_ui, safe_streets_url


def web_app(*, streets="", game=None):
    env = {
        "RAILWAY_PROJECT_ID": STAGING_PROJECT,
        "RAILWAY_ENVIRONMENT_ID": STAGING_ENVIRONMENT,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "SNOWFALL_WEB_QA_CONFIRM": QA_CONFIRM,
        "SNOWFALL_API_ENABLED": "1",
        "SNOWFALL_DB_BACKEND": "postgres",
        "SNOWFALL_WEB_DEMO_ACCESS_CODE": "private-test-code-with-at-least-32-chars",
        "SNOWFALL_DISCORD_STREETS_URL": streets,
    }
    cfg = APISettings("postgresql://unused/db", "web-qa-2026", "https://qa.example")
    return attach_web_ui(FastAPI(), None, cfg, env=env, game=game)


def test_v296_web_uses_existing_artwork_without_changing_gameplay():
    with TestClient(web_app(), base_url="https://qa.example") as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "NO PRIZES" in page.text
        assert 'id="menuToggle"' in page.text
        assert 'id="bossPortrait"' in page.text
        assert 'id="hqCityArt"' in page.text
        assert 'id="hqPortraitWell"' in page.text
        assert '<section class="hero" id="snowDonHero"' in page.text
        assert 'THE COLD<br><em>NEVER</em>' in page.text
        header = page.text.split("</header>", 1)[0]
        assert 'id="siteBanner"' in header
        assert 'id="brandIcon"' in header
        assert 'id="siteBanner"' not in page.text.split("</header>", 1)[1]
        assert 'id="streetsLink"' in page.text
        assert 'src="/art/v290/cities/map/six_city_territory_map.png"' in page.text
        assert client.get("/v1/web/config").json()["version"] == "2.9.6g"
        assert client.get("/v1/web/config").json()["streets_url"] == ""
        for path, mime in (
            ("/art/v290/boss/phase_ice.webp", "image/webp"),
            ("/art/v290/cosmetics/backgrounds/shop.webp", "image/webp"),
            ("/art/boss/snow_don_60.png", "image/png"),
            ("/art/v290/cities/crests/chicago_crest.png", "image/png"),
            ("/art/v290/cities/map/six_city_territory_map.png", "image/png"),
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers["content-type"].startswith(mime), path
        assert client.get("/art/not-present.webp").status_code == 404
        assert client.get("/static/favicon.svg").status_code == 200
        branding = client.get("/v1/web/config").json()["branding"]
        mime = "image/webp" if branding["icon"] else "image/svg+xml"
        assert client.get("/favicon.ico").headers["content-type"].startswith(mime)
        for flag, filename in (("banner", "snowfall-site-banner.webp"),
                               ("icon", "snowfall-site-icon.webp")):
            response = client.get("/static/" + filename)
            assert response.status_code == (200 if branding[flag] else 404)
            if branding[flag]:
                assert response.headers["content-type"].startswith("image/webp")


@pytest.mark.parametrize("url", [
    "http://discord.com/channels/123456789012345678/123456789012345678",
    "https://discord.com.evil.test/channels/123456789012345678/123456789012345678",
    "https://discord.com@evil.test/channels/123456789012345678/123456789012345678",
    "https://discord.com/channels/123456789012345678/123456789012345678?token=a",
    "https://discord.com/channels/123456789012345678/123456789012345678#fragment",
    "https://discord.com/channels/@me/123456789012345678",
    "https://discord.com/channels/not-a-snowflake/123456789012345678",
    "javascript:alert(1)",
    "//discord.com/channels/123456789012345678/123456789012345678",
    "https://discord.com:443/channels/123456789012345678/123456789012345678",
    "",
])
def test_v296_discord_channel_url_rejects_untrusted_destinations(url):
    assert safe_streets_url(url) == ""


def test_v296_discord_channel_link_is_explicit_and_safe():
    channel = "https://discord.com/channels/123456789012345678/234567890123456789"
    assert safe_streets_url(channel) == channel
    with TestClient(web_app(streets=channel), base_url="https://qa.example") as client:
        assert client.get("/v1/web/config").json()["streets_url"] == channel


def test_v296_reuses_only_committed_artwork():
    root = Path(__file__).resolve().parents[1] / "src" / "snowfall" / "graphics" / "art"
    for asset in ("cities/chicago.webp", "cities/las_vegas.webp",
                  "v290/boss/snow_don_0.webp",
                  "v290/cosmetics/frames/ice_frame.png",
                  "v290/portraits/frost_spectre_m.webp"):
        assert (root / asset).is_file(), asset


def test_v296c_public_boss_visual_route_is_read_only():
    from unittest.mock import patch
    game = object()
    expected = {"day": 4, "hp": 75, "max_hp": 150, "tier": 50,
                "state": "wounded", "splash": "/art/v290/boss/rage_snowball.webp"}
    with TestClient(web_app(game=game), base_url="https://qa.example") as client:
        with patch("snowfall.platform.boss_visuals.current_boss", return_value=expected) as read:
            response = client.get("/v1/web/boss")
            assert response.status_code == 200
            assert response.json() == expected
            assert response.headers["cache-control"] == "no-store"
            read.assert_called_once_with(game)
        assert client.post("/v1/web/boss").status_code == 405


def test_v296f_public_city_aggregates_no_player_identity():
    from unittest.mock import Mock, patch
    from types import SimpleNamespace
    game = SimpleNamespace(store=object(), season="qa")
    board = SimpleNamespace(day=2, current_day=2, phase="live", banners=(),
                            matches=(), districts=(), viewer_city="private", missions=())
    with TestClient(web_app(game=game), base_url="https://qa.example") as client:
        with patch("snowfall.services.territory.TerritoryEngine") as engine:
            read = Mock(return_value=board)
            engine.return_value.public_board = read
            response = client.get("/v1/web/territory?day=2")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.json() == {"day": 2, "current_day": 2, "phase": "live",
                                       "banners": [], "matches": [], "districts": [],
                                       "honorary_only": True}
            assert read.call_args.args[0] == "qa"
            assert read.call_args.kwargs["day"] == 2
        assert client.get("/v1/web/territory?day=8").status_code == 422
        assert client.post("/v1/web/territory").status_code == 405


def test_v296g_wire_route_only_public_verified_data():
    from unittest.mock import patch
    result = {"day": 1, "verified_only": True, "headlines": [], "available_days": [1]}
    game = object()
    with TestClient(web_app(game=game), base_url="https://qa.example") as client:
        with patch("snowfall.platform.wire_view.wire_view", return_value=result) as read:
            response = client.get("/v1/web/wire?day=1")
            assert response.status_code == 200
            assert response.json() == result
            assert response.headers["cache-control"] == "no-store"
            read.assert_called_once_with(game, day=1)
        assert client.post("/v1/web/wire").status_code == 405
        assert client.get("/v1/web/wire?day=8").status_code == 422
