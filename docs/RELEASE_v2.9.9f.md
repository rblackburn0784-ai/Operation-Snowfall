# v2.9.9f — Arcade Hub 2.0

**QA website, default OFF.** This release finishes the five-game web
Arcade 2.0 experience by replacing the scattered launch buttons with one
clear, responsive game lobby. It is an additive usability layer, not a new
economic or Discord gameplay mode.

## Player-facing hub

The hub provides five original-artwork game cards with a one-line objective,
a duration/skill label, a prominent **Play free / Continue game** control,
an individual's **practice best out of 100**, count of finished practice
runs, and progress of any saved session.

The five fully interactive modes are:

1. **Snowball Target Gallery** — moving targets and timed snowballs.
2. **Frozen Safecracker** — rotate the dial through three code stages.
3. **Snowman Builder** — drag and fit increasingly complex snowmen.
4. **Snowflake Catch** — steer a basket through wind and icy hazards.
5. **Christmas Trivia** — 15 timed questions, gifts and scrambled words.

**Continue where you left off:** A "SAVE & RESUME" spotlight highlights
the most recently updated unfinished game; its button reuses the
server-owned session rather than starting an extra attempt. A finished
mode offers another free practice run. The hub searches games by name,
skill and description and can show **all five**, **saved games**, **not
played yet** or **completed games**.

The hub shows games not enabled on the QA service as **Not enabled**,
not as playable. It also shows how many full modes are active, saved
sessions, and separate unranked practice completions. It never displays
future question solutions, secret combinations or another account's
sessions. Statuses and personal bests come from a single authenticated
web endpoint rather than browser calculations.

**Classic Arcade remains intact** in a clearly named expandable section:
the original Discord-shared choice games, three daily starts *per game*,
existing passport, stamps, honorary rankings, and City Cup are
unchanged. The hub hides duplicated practice launch buttons from that
section when enabled, but falls back to the previous controls if the
new hub is unreachable.

## Navigation and layout

- Responsive two-column game cards on desktop, single-column on tablets,
  and portrait-friendly artwork/cards on narrow phones.
- Click/touch/keyboard-accessible filters and 44–48px minimum controls.
  Standard tab order, focus outlines and explicit screen-reader labels.
- Large touch-friendly **Play / Continue** buttons, clear saved progress
  indicators and optional reduced-motion styling.
- The new hub sits above the full game screens. Existing on-screen game
  controls remain unchanged; closing a game returns to the hub and
  refreshes the latest saved run.
- Player/account switches clear all cached hub state, active canvases
  and old-account pending actions. Requests verify the canonical player
  identifier before updating the UI.
- Errors show a recoverable message and leave Classic/previous launch
  actions available. Refresh does not spend daily starts.

## Server data and safety

New server projection: GET **/v1/game/arcade/hub**, authenticated,
no-store, default-off. It asks each enabled full mode about its existing
paused/active session and personal practice record, including
authoritatively settling any timer that expired. It never creates a game
or writes an official score, prize, resource, or shared Discord record.
Only explicitly enabled modes are queried (so disabled modes do not
require any extra database tables).

The hub does NOT add a table or change schema version. It reuses the
existing QA-only arcade tables from v2.9.9a–e. Player records remain
account-bound and separate from Classic passport records.

## Explicit QA activation — OFF by default

GitHub commit and CI **do not deploy to Railway**.

1. Back up the isolated **snowfall_web_qa** PostgreSQL database.
2. Ensure the five existing full game schema additions are installed.
   On a protected QA shell configured for database **/snowfall_web_qa**
   and SNOWFALL_API_SEASON_KEY=web-qa-2026, if needed run the
   idempotent guarded installer:

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

   v2.9.9f adds **no new database tables**, so this is only required
   when a previous arcade migration is still outstanding.
3. Enable **SNOWFALL_ARCADE_V299F_ENABLED=1** on **Snowfall-Web-QA** only.
   Each full game still uses its own independent flag:
   **SNOWFALL_ARCADE_V299A_ENABLED**, **V299B_ENABLED**, **V299C_ENABLED**,
   **V299D_ENABLED**, **V299E_ENABLED**. Enable those only after their
   migrations are present.
4. Redeploy the QA website; sign in using an existing Underworld QA
   account and test all five game cards on desktop and phone.
5. Check saved sessions (including after refresh or moving away),
   filters, full-screen canvas navigation, reconnect, account switching,
   auto expiry, practice personal records, and Classic passport limits.
6. Verify Classic official attempts, scores, rankings, prize tables
   and resources have not changed as a result of practice.

Never enable the hub or prior full games on the Discord worker without
a separate design and security review. This release is **unranked QA
practice**, not a production competitive launch.

## Validation

- python -m pytest -q tests/test_v299f_arcade_hub.py
- python -m pytest -q tests/test_v299_arcade_postgres.py
- node --check src/snowfall/platform/static/arcade-hub-v299f.js
- node --test tests/test_v299f_arcade_hub_browser.mjs
- Full GitHub Actions matrix (Linux Python 3.12/3.13, Windows Python
  3.13, browser regression suite, PostgreSQL integration).

## Next steps

**v2.9.9g — Arcade Atmosphere, Controls & Balancing:** across-game
feedback polish, clearer mobile instructions and refined game feel.

**v2.9.9h — End-to-End Release Hardening:** protected staging smoke
checks, cross-platform verification, abuse tests, audit and launch checklist.
