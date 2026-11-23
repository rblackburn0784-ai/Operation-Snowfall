# v2.9.7a — Layered Winter Underworld branding

Web-only artwork update; the shared gameplay/API version remains 2.9.7. The QA config advertises web_artwork_version 2.9.7a.

Place the three generated assets in src/snowfall/platform/static/:
- snowfall-header-city.webp — full-width header backdrop
- snowfall-title.png — transparent title overlay
- snowfall-city-wallpaper.webp — fixed page backdrop

Assets are optional and checked by the config endpoint. Missing assets preserve the older branding or existing plain background. Atmosphere off suppresses the wallpaper. Mobile dock and primary nav remain unchanged.

QA: confirm all three config flags true, static files return 200, inspect 360/768/1440/2048px widths, menu and sign-out, and atmosphere on/off. Verify gameplay and shared identity via existing v2.9.7 smoke checks. No database migrations.
