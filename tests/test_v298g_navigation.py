"""v2.9.8g: compact grouped header navigation and safety regression."""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/snowfall/platform/static"


class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.depth = 0
        self.current_group = None
        self.groups = {}
        self.routes = {}
        self.triggers = []

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "nav" and props.get("id") == "primaryNav":
            self.inside = True
            self.depth = 1
            return
        if not self.inside:
            return
        if tag == "nav":
            self.depth += 1
        if "data-nav-group" in props:
            self.current_group = props["data-nav-group"]
            self.groups[self.current_group] = set()
        if "data-nav" in props:
            name = props["data-nav"]
            self.routes[name] = self.routes.get(name, 0) + 1
            if self.current_group:
                self.groups[self.current_group].add(name)
        if "nav-group-trigger" in props.get("class", "").split():
            self.triggers.append((props.get("aria-controls"), props.get("aria-expanded")))

    def handle_endtag(self, tag):
        # The nav groups contain exactly one wrapping <div> and inner popover.
        # Reset the group after the popover is closed; no nested groups exist.
        if self.inside and tag == "nav":
            self.depth -= 1
            if self.depth == 0:
                self.inside = False


def test_every_event_section_remains_reachable_without_duplicate_nav_links():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    parsed = NavigationParser()
    parsed.feed(html)
    expected = {"home", "combat", "boss", "cities", "shop", "activities",
                "arcade", "wire", "community", "staff"}
    assert set(parsed.routes) == expected
    assert all(value == 1 for value in parsed.routes.values())
    assert len(parsed.triggers) == 3
    assert {group for group in parsed.groups} == {
        "combat boss cities", "shop activities arcade", "wire community staff"}
    # Confirm each control's accessible expansion target actually exists.
    for target, expanded in parsed.triggers:
        assert target and f'id="{target}"' in html
        assert expanded == "false"
    assert 'id="menuToggle"' in html
    assert 'id="staffShortcut"' in html
    assert 'id="streetsTopLink"' in html
    assert 'data-chat-open' in html
    assert 'id="staffNav"' in html
    assert 'data-nav="combat"' in html and 'data-nav="cities"' in html


def test_mobile_header_bypasses_old_overlapping_wrap_layout():
    css = (ROOT / "app.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    new_css = css[css.index("/* v2.9.8g"): ]
    assert "grid-template-columns:minmax(0,auto) minmax(0,1fr) auto" in new_css
    assert "@media(max-width:1200px)" in new_css
    assert "display:none!important" in new_css
    assert ".topnav.open" in new_css
    assert "max-height:min(76vh,680px)" in new_css
    assert "@media(max-width:780px)" in new_css
    assert "@media(max-width:380px)" in new_css
    assert "#staffShortcut{display:none!important}" in new_css
    assert "prefers-reduced-motion:reduce" in new_css
    assert "closeNavigationMenus({restoreFocus:true})" in js
    assert 'event.key==="ArrowDown"' in js
    assert "reflectNavigationGroup(name)" in js
    assert "Snowball Wars" in html and "Winter Fun" in html
    assert "Open Streets Chat" in html
    assert "2.9.8l" in html
    assert "app.css?v=298l" in html and "app.js?v=298l" in html
