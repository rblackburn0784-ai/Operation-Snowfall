# Operation Snowfall v2.9.4a — Discord Linking & Shared Progress Verification

## Summary

This is an **isolated staging release**, built on the verified v2.9.4
Underworld → Snowfall login handoff. It does not touch Underworld production,
the live Discord worker, the imported PostgreSQL migration reference, or
prize allocations.

v2.9.4a delivers:

- An authoritative `GET /v1/game/progress` endpoint, with canonical
  **decimal-string player IDs** and the same score, ammunition, snowflakes,
  warmth, inventory quantities and Snow Don HP from the official engines.
- A web **Connected identities** panel that displays the Underworld/Discord
  link state, canonical player ID and a fresh shared-progress snapshot.
- Discord `/snowbridge progress` and `/snowbridge craft` commands, plus
  existing profile, PvP, Snow Don, inventory and leaderboard commands.
- A one-Discord-account-per-game-character constraint, enforced both in
  PostgreSQL (partial unique index) and transactional application code.
- Graceful OAuth conflict redirects that never change existing linked
  accounts or silently merge two sets of progress.
- Browser and Discord QA clients both applying the **same** StagingGame
  rules, including fictional targets and the one-time starter bonus.
- A disposable PostgreSQL end-to-end test using real v11 game services,
  server-signed Underworld login, server-backed OAuth state and a
  **mock Discord /users/@me** response. The test runs two independent
  PostgreSQL connections for the browser and Discord adapters and verifies:
  - Underworld session → canonical player → verified Discord link.
  - Both adapters read the same player ID and starting resources.
  - Discord Snow Don attack updates the website's boss HP and resources.
  - Browser crafting updates the Discord inventory without a sync job.
  - Discord crafting updates the website inventory and snowflakes.
  - Browser PvP immediately appears in the Discord progress snapshot.
  - Replaying the same action cannot double-spend items or score.
  - Logging out and back in through Underworld preserves linked progress.
  - Unlinked and conflicting Discord accounts cannot hijack the character.
- Browser contract tests for incorrect CSRF, state replay, OAuth link
  conflicts, BIGINT IDs, and an unauthenticated progress endpoint.

## IMPORTANT: simulated OAuth vs real Discord activation

The test **mocks Discord's verified OAuth response**. It proves the
underlying account-linking and shared-game code without using real Discord
tokens. It **does not** prove that an actual Discord user has completed
authorization or that a QA Discord bot has executed live slash commands.

As of the start of this release, the Railway Snowfall QA service has no
Discord OAuth credentials, and no separate QA Discord bot token or QA
guild ID. The user must create or identify a Discord application for QA
in the Discord Developer Portal and add private configuration to Railway.

### Snowfall web service (existing staging Railway service)

Set these private variables on **Snowfall-Web-QA** only:

- `SNOWFALL_DISCORD_OAUTH_CLIENT_ID` — the app's OAuth client ID.
- `SNOWFALL_DISCORD_OAUTH_CLIENT_SECRET` — the OAuth client secret.
- `SNOWFALL_DISCORD_OAUTH_REDIRECT_URI` —
  `https://snowfall-web-qa-staging.up.railway.app/v1/auth/discord/callback`

Register the **exact same** redirect URI in the Discord Developer
Portal's OAuth2 redirect list. Use **identify** scope. Do not expose
the client secret in browser JavaScript, a Discord chat, repository
commits, screenshots or a user-visible config endpoint.

Once the three settings are in place, the Connected identities panel
shows **Link Discord account**. Sign in from the Underworld QA site
first; click Link Discord while logged in to Snowfall. Discord's
actual `/users/@me` response is used for identity verification and
the OAuth2 state is single-use, five-minute and bound to your Snowfall
session. The system rejects a Discord account already linked elsewhere
or carrying separate historic gameplay that needs staff reconciliation.

### Separate Discord QA bot

The existing `/snow` bot uses legacy numeric Discord IDs. It has
**not** been switched to canonical Underworld player IDs. For the
`/snowbridge` commands to operate on a real Discord guild, deploy
a separate QA bot service with:

- `SNOWFALL_DISCORD_BRIDGE_ENABLED=1`
- `SNOWFALL_DISCORD_BRIDGE_TOKEN` — private token of a **distinct**
  test bot, never the live Discord token.
- `SNOWFALL_DISCORD_BRIDGE_GUILD_ID` — the **test** Discord server ID,
  not the live server ID.
- `SNOWFALL_PRODUCTION_GUILD_ID` — the live server ID for explicit
  mismatch checking.
- `SNOWFALL_DATABASE_URL` — a Railway reference to the **staging**
  PostgreSQL server's existing `railway` database URL; the bridge
  derives the isolated `snowfall_web_qa` database.
- `SNOWFALL_API_SEASON_KEY=web-qa-2026`
- `RAILWAY_PROJECT_ID` and `RAILWAY_ENVIRONMENT_ID` are provided by
  Railway and must match the isolated staging project/environment.
- Start command `python -m snowfall.platform.discord_bridge`, installed
  with Python's `operation-snowfall[postgres,web]` dependencies.

The bot uses `discord.Intents.default()` and guild slash commands.
Keep its Discord scope/permissions limited to `bot` and
`applications.commands` as necessary for your test guild. The test
bot must **not** be installed in your production Discord server.

No QA Discord service should be started without these credentials.
Do not reuse the production Discord application token.

## Test protocol once credentials are connected

1. Enter Underworld QA with your test account, click ❄ SNOWFALL,
   and confirm your original character and inventory have returned.
2. In Snowfall **Connected identities**, use **Link Discord account**,
   approve the Discord OAuth screen and verify **Discord connected**.
3. Open your separate QA guild's `/snowbridge progress`; compare the
   canonical decimal ID and score/resources to the website's
   **Verify progress** button.
4. Attack Snow Don in the QA Discord command. Refresh the website:
   its shared HP, score and ammunition should reflect the action.
5. Craft Hot Chocolate on the website, then inspect Discord inventory.
   Craft a Fort Kit on Discord, then refresh the website's market.
6. Repeat the same action ID in regression tests and verify
   idempotency (no doubled rewards or spending).
7. Sign out of Snowfall, return through Underworld and confirm the
   same Discord link, character ID, items and score.
8. Attempt a second Discord link and an already-linked account:
   both must be refused without changing either character's progress.

### Safety and limitations

- This release is **staging-only**: all test scores and items are
  fictional and **not** the production Discord Christmas event.
- The actual Discord OAuth journey and live QA bot still need the
  separate Discord app/guild credentials above.
- Existing `/snow` menus, views, background tasks and production
  identity flows remain unchanged.
- The partial unique index will reject a database with pre-existing
  duplicate Discord links rather than silently picking a winner;
  that is intentional fail-closed behaviour.
- There is no automatic merging, unlinking or copying of two existing
  game histories. Any reconciliation requires a separately audited
  admin workflow.
- All API player IDs stay decimal strings to avoid JavaScript precision
  loss for large PostgreSQL BIGINT player IDs.
- A real production cutover still requires fresh backup/reconciliation,
  recovery rehearsal, security review and live cross-platform acceptance.

### Release checks

GitHub CI runs the full Linux and Windows regression suite, a
PostgreSQL 16 migration/engine suite, new v2.9.4a two-adapter PostgreSQL
verification, JavaScript syntax checks and external staging HTTPS smoke
checks. The Underworld QA site is unchanged by this branch.
