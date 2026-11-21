# v2.9.6a — Branding and Collector Headquarters

QA website only, based on v2.9.6. The main site uses the organiser's supplied
3:1 artwork at its natural aspect ratio. The Snow Don badge is used both as
navigation logo and favicon. The two web-optimised files must be added to
`src/snowfall/platform/static/`:

- `snowfall-site-banner.webp` (2048 × 682)
- `snowfall-site-icon.webp` (256 × 256)

The web tools report the assets' presence in `/v1/web/config` under
`branding`; missing files intentionally show the original fallback branding.
No broken image or fabricated artwork. Upload both before final deployment
of the complete branded release.

HQ uses original Discord portrait, frame, banner, trail and gear artwork.
The existing /v1/game/wardrobe read model, not local storage, determines what
appears; equipped slots are checked against owned items and allowed keys.
Purchasing does not automatically equip; equip in Winter Market. Refresh
HQ after changing appearance in Discord. All gameplay mutations, CSRF,
idempotency, linked identity, score and prize policy remain unchanged.
The QA verification tools are collapsible and automatically shown on
unlinked accounts and OAuth conflict/recovery callbacks.

## Checks

- Existing full CI and v2.9.5 replay checks; new v2.9.6a wardrobe checks.
- Confirm both branding flags true when files are uploaded; browser shows
  banner uncropped, icon in header and favicon. Check desktop and mobile.
- Sign in, verify same canonical ID, purchase and equip a frame/portrait,
  refresh HQ, and verify appearance after equipping from Discord.
- Ensure unowned items cannot display or be equipped; verify original
  NO REAL PRIZES gate and shared progress.

Only switch Snowfall-Web-QA. Leave Discord worker, Underworld and database
variables untouched. Roll back the web service to v2.9.6 (641dbe35bd253a4f26ee8bcb302d4b9fa234f631).
