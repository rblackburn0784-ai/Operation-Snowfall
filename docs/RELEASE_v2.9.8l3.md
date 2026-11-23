# v2.9.8l3 — Snowball Card Spacing Tweak

A **CSS-only visual fix** for the Headquarters Snowballs resource card, based on the screenshot showing the stockpile touching the top of its display area.

- Increase the stockpile's top spacing from `clamp(10px,1.2vw,16px)` to `clamp(18px,2vw,26px)`.
- Use `object-fit: contain` and `object-position: center bottom` to keep the entire snowball artwork visible and centred.
- At widths up to 640px use `16px` top spacing; at widths up to 380px use `14px` to leave room for labels and counts.
- Refresh the CSS cache key from `298l-r2` to `298l-r3`; keep the JavaScript unchanged.

**Unchanged:** every other resource card, warmth thermometer, stage switching, event balance, snowball regeneration, scoring, API, database, marketplace, artwork asset, Discord worker and prizes.

**QA:** existing resource-card Node test updated to assert the new spacing and fixed image sizing. Run Linux, Windows, PostgreSQL and wheel-artifact checks, then deploy to Snowfall-Web-QA only. Visually verify at the user's browser width, at 640px and 320px.
