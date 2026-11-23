"""Release consolidation contracts for the isolated staging build."""
from pathlib import Path

from snowfall.platform.release import VERSION, WEB_RELEASE


def test_release_contract_and_artwork():
    root = Path(__file__).resolve().parents[1]
    static = root / "src/snowfall/platform/static"
    assert VERSION == "2.9.7"
    assert WEB_RELEASE == "2.9.8k"
    html = (static / "index.html").read_text(encoding="utf-8")
    assert WEB_RELEASE in html
    assert "app.css?v=298k" in html and "app.js?v=298k" in html
    for name in ("snowfall-title.png", "snowfall-header-city.webp",
                 "snowfall-city-wallpaper.webp", "snowfall-wire-frontpage.webp"):
        assert (static / name).stat().st_size > 0
    smoke = (root / ".github/workflows/v297-live-release-smoke.yml").read_text(encoding="utf-8")
    assert 'cfg["version"]==expected["VERSION"]' in smoke
    assert 'cfg["web_artwork_version"]==expected["WEB_RELEASE"]' in smoke
    assert "QA Winter Player" in smoke
    assert 'route.abort()' in smoke
