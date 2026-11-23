# v2.9.8l — Status & Resource Artwork Integration

## Scope

A web-only visual release of the exact six uploaded artwork sources. Every image is extracted from the supplied artwork and optimised into transparent WebP. The event rules, shared PostgreSQL data, resource quantities, regeneration, caps, Market prices, scoring, leaderboard order, prizes and independent Discord worker are **unchanged**.

### Asset placement

All 21 assets live at `src/snowfall/graphics/art/v290/status/v298l/` and are served through the existing authenticated Snowfall Web application’s `/art` static mount. The original transparent collage sheets are split into **four distinct files per resource**, rather than showing four pictures inside a single icon.

| Upload artwork | Render target | Four image stages |
|---|---|---|
| Wide winter street | Snowball Alley atmospheric banner | Decorative, with dark text scrim |
| Snowball piles | HQ snowballs, sticky player resource bar, Alley ammunition | 0–2 / 3–5 / 6–9 / 10–12 |
| Ornate horizontal warmth bars | HQ and sticky warmth display | 75–100 / 50–74 / 25–49 / 0–24 |
| Cold girl sequence | HQ warmth status and Alley exposure status | Comfortable / Chilly / Cold / Freezing; same warmth breakpoints |
| Gold snowflake coins | HQ spendable currency, Winter Market wallet, sticky currency | 0–24 / 25–74 / 75–149 / 150+ |
| Crystal snowflake piles | HQ total points, sticky points, city scoreboard rows | 0–99 / 100–299 / 300–599 / 600+ |

The four ranges for currencies/points are **display thresholds only**, not purchasable tiers, rewards, caps, economic prices or achievements. Exactly 12 is the current snowball inventory maximum; no unattainable stage of 13+ is used.

### Live data, accessibility, and edge cases

The resource artwork changes only when `showResourceArtwork()` receives the existing canonical `S.me.resources` and `S.me.score`. There is no new API call or client-side alternate ledger. The exact quantity remains in real text for accessibility and clarity. The cold status uses the actual warmth reading; zero snowballs dims the single-snowball illustration rather than presenting it as a positive balance. Missing/stale resources hide the corresponding image instead of inventing a value.

Leaderboard illustrations use the individual player’s **actual score**, not the viewing player’s score. All images use empty alt text when adjacent numbers/labels convey the value. The wide street scene has a descriptive accessible label.

### Operator checklist

1. Run the full Linux Python 3.12/3.13, Windows 3.13, Node browser, and PostgreSQL regression matrix. Confirm all 21 assets decode and return HTTP 200.
2. Sign into Snowfall-Web-QA and verify HQ snowball, warmth/cold, snowflake and points images with actual QA numbers.
3. Use the existing isolated Test Lab or fictional QA characters to inspect stage boundaries, particularly 0 and 12 snowballs, and 24/25, 49/50, 74/75 warmth.
4. Visit Snowball Alley for the new atmospheric banner and ammunition/cold indicators, Winter Market for the wallet, and City Wars for the score artwork.
5. Resize to 1100, 768, 390 and 320px, checking the numeric text is still visible, the original navigation works, and the persistent chat remains accessible.

**Deployment:** Merge after green CI; advance only the Railway Snowfall-Web-QA staging service branch. Do not deploy or restart the independent Discord worker. Manual visual acceptance remains a separate step after automated checks.
