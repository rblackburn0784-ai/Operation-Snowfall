"""Static integration contracts for the layered newspaper layout."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src/snowfall/platform/static"


def test_wire_art_is_decorative_not_standalone():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert 'id="wireEditionArt"' not in html
    assert 'el("wireEditionArt")' not in js
    assert '<div class="wire-edition-body">' in html
    assert '.wire-edition-body{' in css
    assert 'front_page_template.png' in css
    assert 'final_day_edition.png' in css
    assert 'data-edition="final"' in css
    assert 'snowfall_wire_masthead.png' in html
    assert 'el("wirePaper").dataset.edition=kind' in js
    for element in ("wireLead", "wireLeadDetail", "wireHeadlines", "wireNotice"):
        assert f'id="{element}"' in html
    assert 'v=297b' in html
