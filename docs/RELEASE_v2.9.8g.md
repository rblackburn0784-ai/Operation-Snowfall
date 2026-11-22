# v2.9.8g — Responsive Navigation & Interface Polish

**Scope:** web interface only, isolated Railway staging site. No artwork replacements, database migrations, score changes, Discord bot code changes or changes to event mechanics.

## What players will see

A consolidated header with just four primary navigation choices:

| Top-level choice | Contents |
| --- | --- |
| **Headquarters** | Personal HQ and next actions |
| **Snowball Wars** | Snowball Alley, The Snow Don, City Wars |
| **Winter Fun** | Winter Market, Activities, Winter Arcade |
| **Community** | The Streets, Snowfall Wire, Open Streets Chat, and Event Control for verified staff |

The persistent chat shortcut remains available on extra-wide screens. Staff retain a prominent one-click Event Control shortcut on desktop and tablet layouts. On smaller phones Event Control is available through Community after verified staff sign-in.

## Responsive behaviour

- **Desktop (>1200px):** a one-line, three-column header keeps the original city artwork and logo left, four primary navigation choices centred, and account/staff actions right. Submenus are aligned below their trigger and are not squashed into a second row.
- **Tablet and small browser windows (<=1200px):** compact Menu button replaces the middle navigation bar. The expandable, scrollable menu opens beneath the header without moving the underlying game content.
- **Small screens (<=780px):** one-column menu choices, readable labels and generous touch targets.
- **Narrow screens (<=680px):** redundant staff/chat action buttons leave the header; the same actions remain available inside the menu, avoiding collisions with the logo and Sign In/Out.
- **320–380px:** compact brand and controls; no squeezed multi-row top navigation.

Group cards include a short description for each section. The selected section highlights its parent group. Menu entries remain real buttons with the same `data-nav` routes as prior releases, so deep links, ordinary page navigation and staff access checks remain unchanged.

## Accessibility and interaction

- `aria-expanded` and `aria-controls` on each group trigger.
- Keyboard opening with Enter/Space (native button behaviour) and Arrow Down (focuses first submenu entry).
- Escape closes and returns focus to the open menu trigger.
- Click outside closes open groups; selecting a page or opening chat also closes menus.
- Desktop resize clears stale mobile-menu state.
- Clear keyboard focus outlines and reduced-motion support.

## Regression and safety gates

- All original sections are still reachable and appear exactly once in the primary navigation.
- `#menuToggle`, `#staffShortcut`, `#staffNav`, `#streetsTopLink`, `data-nav` and chat actions remain compatible with existing controls.
- A hidden staff option is never made accessible by a cosmetic navigation change; server-side Discord OAuth allowlisting still controls authorisation.
- No engine settings, cosmetics, assets, prize policies, balance data or independent Discord worker changed.
- Test on desktop 1920/1366/1280, resized window 1150/980/768, and mobile 390/320px. Validate mouse, tap, keyboard Escape/Arrow Down and chat/Event Control shortcuts.

**Deployment:** CI must pass across Linux, Windows and PostgreSQL before merging. The Snowfall-Web-QA service follows `feature/v2.9.7-launch-readiness`; the separate Discord worker is pinned to its existing deployed commit. Release only the website branch.
