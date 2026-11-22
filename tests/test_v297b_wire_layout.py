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
    assert 'v=298g' in html


def test_wire_v297c_uses_calibrated_art_and_dynamic_issue():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert 'class="wire-lead-block"' in html
    assert 'snowfall-wire-frontpage.webp' in css
    assert 'aspect-ratio:4/5' in css
    assert 'class="wire-frontpage"' in html
    assert '.wire-paper.has-wire-template .wire-frontpage' in css
    assert 'top:12.95%' in css
    assert 'top:27.5%' in css
    assert 'top:55.8%' in css
    assert 'clip-path:inset(50%)' in css
    assert 'wireSlots(heads).map(wireHeadlineMarkup)' in js
    assert 'has-wire-template' in js
    assert 'id="wireEdition"' in html
    assert 'DAY "+w.day' in js
