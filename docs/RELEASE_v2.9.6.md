# Operation Snowfall v2.9.6 — Website Experience & Visual Integration

**Branch:** `feature/v2.9.6-website-visual-integration`  
**Based on:** `feature/v2.9.5b-live-qa-smoke-repair` at `b504c0ab31758dc0b713323b3406d405e4eae6e0`  
**Scope:** Isolated Snowfall-Web-QA staging interface only. **NO REAL PRIZES.**

## Website improvements

- Replace the temporary CSS Snow Don silhouette with bundled original Discord event artwork.
- Show the player's home-city scene at headquarters, personalize a simple suggested next action from current snowball count, and make navigation actions clearer.
- Show the matching Snow Don damage-stage portrait from the real shared boss HP: 100%, 90%, ... 10%, then the 0% defeat image. The selection rounds *up* to the next 10% step. The actual HP and shared boss engine are unchanged.
- Add genuine cosmetic previews to the Winter Market, an illustrated map, city crests and Snowball Alley art.
- Add mobile navigation that can be expanded and collapsed with an accessible button, a skip link, improved alt text, keyboard focus support, and reduced-motion respect.
- Provide a Snowfall SVG favicon (including the /favicon.ico compatibility route).
- Keep the Underworld login, Discord identity bridge, old linked-player data, shared score, idempotency keys, staff launch audit and game write endpoints unchanged.

## Existing art, not new user-generated artwork

The staging site mounts only `src/snowfall/graphics/art` under `/art/` via FastAPI StaticFiles.
It serves existing committed PNG and WebP assets in the same Docker image as the bot.
No CDN, third-party image hosting, extra image tokens, bot token, database changes or second art source.

## Discord #the-streets community link

**Phase 1 only:** A configurable link opens the existing Discord text channel in another tab. This is **not** an iframe, IRC room, Discord-message proxy, webhook, account-data relay or message synchronisation. The bot receives no new permissions.

In the **Snowfall-Web-QA service only**, optionally add:

```dotenv
SNOWFALL_DISCORD_STREETS_URL=https://discord.com/channels/YOUR_GUILD_SNOWFLAKE/YOUR_CHANNEL_SNOWFLAKE
```

Both values must be real numeric Discord IDs copied from **Copy Channel Link** in Discord.
Do not invent a channel ID or set this on the Discord worker. The server and client both reject non-HTTPS, non-Discord, non-channel, query-string and redirect-style URLs. When missing or invalid, the link is hidden and an honest 'not configured' notice appears.

A future embedded or mirrored chat needs a separate moderation, consent, security and retention design. It is deliberately **not** enabled in v2.9.6.

## Release and QA procedure

1. CI must pass `python -m compileall -q src`, `python -m pytest -q`, `node --check src/snowfall/platform/static/app.js` and `node --test tests/test_v295_browser.mjs tests/test_v296_browser.mjs`.
2. Deploy **only Snowfall-Web-QA** from the v2.9.6 branch. Do **not** redeploy the existing Discord worker or Underworld login service as part of this visual release.
3. Check `/v1/health`, `/v1/ready`, `/v1/web/config` (UI version 2.9.6), `/`, `/favicon.ico` and all referenced `/art` images. Health endpoint version is maintained by the underlying shared API; the UI config is the v2.9.6 marker.
4. Desktop and mobile: tab through menu, sign in from Underworld QA, verify SnowDude's canonical player ID and compare score, Snowflakes, snowballs and Snow Don HP with `/snowbridge verify`.
5. Check Snow Don's portrait corresponds to the HP/maximum ratio, and that changing to another panel does not alter state.
6. Test Snowball Alley, Winter Market browse, cosmetic purchase/equip and a consenting QA action, then verify the result in the existing Discord bot. Confirm idempotent retry and linked-account requirements remain intact.
7. If a real channel link is supplied, check it opens the right Discord channel; without it, ensure no dead button is shown.
8. Re-run `/snowadmin launch-check`. **QA prize awards MUST remain zero.** Test-only fictional/unlinked NPC warnings may remain.
9. Confirm staff-only functions, login credentials, user messages and secrets are not revealed by public assets or web config.

No migration, reset, OAuth relink, character transfer, prize alteration or new Discord process is required.

## Rollback

Switch **Snowfall-Web-QA only** back to its previously confirmed v2.9.5a SHA
`4175003d09004df268a995155dbec9734235e99e` (or the current approved web QA rollback deployment).
Leave the PostgreSQL database, linked player records, Underworld service, Discord worker and its original SQLite snapshot alone.
