# v2.9.4 — Discord Identity Bridging & Underworld Login Integration

This release is **staging-only**. It comprises:
- The Snowfall web API receiving a signed form POST from Underworld's backend.
- A matching opt-in Underworld feature branch, preserving its existing
  one-character account model and signed session cookies.
- An optional, completely separate Discord **QA bot** with canonical linked
  player IDs for core gameplay via /snowbridge commands.
- A browser link-Discord button using the already-developed OAuth2 PKCE flow.

The live Operation Snowfall Discord worker, original /snow menus, live
Underworld service and prize rules are **not modified**. Do not deploy
this branch to either production service.

## Underworld existing-login handoff

After authenticating normally, Underworld's existing require_character
dependency confirms the account, that it isn't suspended/banned, and its
single character. It then signs a one-minute assertion using a private
shared HMAC-SHA256 secret containing:
- iss=underworld, aud=operation-snowfall
- account_id and character_id (immutable numeric identifiers)
- character_name (display only)
- iat, exp, and random one-time jti.

The authenticated Underworld page submits a **same-origin POST** to
/api/snowfall/handoff. It then submits the signed token via an HTML form
POST to the Snowfall /v1/auth/underworld/handoff endpoint. No password,
email, Underworld session cookie or private signing secret is forwarded.
The assertion stays out of URLs and localStorage.

Snowfall validates the exact trusted Origin, HMAC, audience, 60-second
lifetime and one-use nonce. It binds the Underworld account and its
single character to a canonical game ID in PostgreSQL, stores the browser
session token only as a hash and redirects to the Snowfall dashboard.

If a character is already linked to a different Underworld account, or
an account is linked to another character, the login is rejected.
Changing the Underworld display name doesn't change the identity link.

## Optional Discord OAuth

The browser dashboard now displays Link Discord account when the Discord
OAuth client credentials are configured privately. Discord's identify
scope and authenticated /users/@me response establish the Discord user ID.
No browser-supplied Discord ID can link an account.

Existing Discord game profiles are *never silently merged* into an
Underworld profile. A manual staff-reviewed reconciliation process would
be required if both have existing scores. OAuth state is single-use and
scoped to the original Snowfall browser session; PKCE and CSRF required.

Note: if Discord OAuth is used for login before a user connects Underworld,
the account may have a separate profile. Link Underworld first, then
Discord where possible; conflict is reported rather than auto-repaired.

## Discord canonical gameplay bridge (test guild ONLY)

An isolated v2.9.4 Discord test client, NOT the existing live Discord bot,
is implemented at snowfall.platform.discord_bridge. It uses a distinct
QA Discord bot token and test guild, checks Railway's staging project and
environment ID before startup, and accesses exactly the same logical
snowfall_web_qa Postgres database as the browser.

Commands: /snowbridge link, profile, register, ready, targets, throw,
boss, siege, inventory, leaderboard. All use the official SharedGame
facade and canonical game IDs. The actor is resolved only from the
verified discord.Interaction.user.id through the identity repository;
it is impossible to submit an acting player ID via a slash command.
Target IDs are player IDs from the official shared targets endpoint,
with server-side eligibility enforcement. Discord interaction IDs become
unique idempotent game action keys.

The live /snow menus **still use legacy Discord IDs**. They have not been
migrated to canonical linked IDs in this release, so do NOT claim that
all historical Discord commands are cross-platform. The new /snowbridge
path is the safe verified adapter for QA.

The QA Discord client is intentionally not deployed without a separate
bot token and dedicated test-guild ID. Do not reuse the production token.

## QA service configuration

Snowfall web staging service:
- SNOWFALL_API_ENABLED=1
- SNOWFALL_DB_BACKEND=postgres
- SNOWFALL_API_SEASON_KEY=web-qa-2026
- SNOWFALL_WEB_QA_CONFIRM=CONFIRM_ISOLATED_WEB_QA_DATABASE
- SNOWFALL_DATABASE_URL=the staging PostgreSQL private DATABASE_URL reference
- SNOWFALL_UNDERWORLD_ASSERTION_SECRET=secure independent 32+ byte secret
- SNOWFALL_UNDERWORLD_TRUSTED_ORIGIN=exact HTTPS Underworld staging origin
- SNOWFALL_DISCORD_OAUTH_CLIENT_ID, _CLIENT_SECRET and _REDIRECT_URI can
  remain blank until Discord developer app setup.

Matching isolated Underworld staging service:
- UNDERWORLD_SNOWFALL_BRIDGE_ENABLED=1
- UNDERWORLD_SNOWFALL_SHARED_SECRET=same secret
- UNDERWORLD_PUBLIC_ORIGIN=its own exact HTTPS staging origin
- UNDERWORLD_SNOWFALL_TARGET_ORIGIN=https://snowfall-web-qa-staging.up.railway.app
- UNDERWORLD_ENV=production (only to enable secure cookies in hosted QA)
- UNDERWORLD_SECRET=a *separate* random 48+ character session key
- UNDERWORLD_DATA_DIR=/data (with its OWN persistent volume, not production).

QA Discord bridge service (optional, not enabled/deployed by default):
- Start command: python -m snowfall.platform.discord_bridge
- SNOWFALL_DISCORD_BRIDGE_ENABLED=1
- SNOWFALL_DISCORD_BRIDGE_TOKEN=new separate bot token
- SNOWFALL_DISCORD_BRIDGE_GUILD_ID=separate test guild ID
- SNOWFALL_PRODUCTION_GUILD_ID=live guild ID for explicit mismatch
- SNOWFALL_API_SEASON_KEY=web-qa-2026
- SNOWFALL_DATABASE_URL=the staging PostgreSQL service reference
- Railway project/environment automatically identify the QA environment.

For all staging services, keep secrets in Railway variables, never GitHub.

## Testing and release gates

The GitHub Actions Snowfall suite tests:
- Legacy SQLite game engine and original Discord commands
- Real disposable PostgreSQL v11 migration, identity and replay checks
- Underworld assertion acceptance, wrong-origin and JSON-form rejection,
  no URL credential leakage and nonce replay.
- Correct Discord actor canonical mapping and input validation.
- Refusal to start bridge with a production Railway project, season or token.

The Underworld branch has its own CI for signature, CSRF origin checks,
missing character/auth rejection and disabled-by-default settings.

For staging verification, test Underworld QA login/create-character;
click Snowfall; verify same canonical ID after refresh; score a game
action and reconnect; link verified Discord via OAuth when configured.
Never use real production account data or live prizes.

## Outstanding before real production cross-platform gameplay

- Do not activate Underworld branch or new Snowfall bridge in production.
- Integration in the **existing production /snow menus** still needs a
  complete audited canonical adapter across all persistent views, buttons
  and background jobs, not just slash commands.
- Discord OAuth credentials and a dedicated test bot token need to be
  configured by an authorized Discord app administrator.
- Production migration needs a fresh SQLite snapshot and rollback/backup
  rehearsal, staged database cutover, conflict handling, security review,
  monitoring, rate limiting and real-browser tests.
