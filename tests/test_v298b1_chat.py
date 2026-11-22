"""The Streets chat must remain opt-in, in-site, and exact-channel-scoped."""
from pathlib import Path
from snowfall.platform.release import WEB_RELEASE

ROOT = Path(__file__).resolve().parents[1] / "src/snowfall/platform/static"

def test_live_chat_uses_guarded_third_party_frame():
    html = (ROOT/"index.html").read_text(encoding="utf-8")
    js = (ROOT/"app.js").read_text(encoding="utf-8")
    assert WEB_RELEASE == "2.9.8d"
    assert 'id="streetsChatFrame"' in html
    assert 'referrerpolicy="no-referrer"' in html
    assert 'id="streetsChatEnable"' in html
    assert "https://e.widgetbot.io" in js
    assert 'frame.removeAttribute("src")' in js
    assert "S.streetsChatOpen=true" in js
    assert "S.session&&S.me?.registered&&hasPlayIdentity" in js
    assert 'data-nav="community"' in html
    assert "Chat opens in Discord" not in html
    assert "Sign in to enter chat" in js
    assert "authModal();return" in js
    assert 'id="streetsChatDock"' in html
    assert html.count('id="streetsChatFrame"') == 1
    assert html.index('id="streetsChatDock"') > html.index('<aside class="sidebar"')
    assert 'id="streetsChatLauncher"' in html
    assert 'data-chat-open' in html
    assert 'position:sticky' in (ROOT/"app.css").read_text(encoding="utf-8")
    assert 'community-chat-shortcut' not in html
    assert 'side-card streets-card' not in html
    assert 'id="streetsChatDock"' in html
    assert 'id="streetsChatLauncher"' in html

def test_csp_only_allows_named_widget_frame():
    api = (ROOT.parent/"api.py").read_text(encoding="utf-8")
    assert 'frame-src https://e.widgetbot.io' in api
    assert "script-src 'self'" in api
    assert "connect-src 'self'" in api
