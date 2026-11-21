# v2.9.4b — Existing Discord Bot, Unified Accounts (QA preparation)

## Purpose

Reuse the **existing Operation Snowfall Discord application, token and guild**.
This feature branch builds on v2.9.4a. It does **not** start or require a
second Discord QA bot, does not touch the live Underworld application, and
does not change official event prizes.

The existing `/snow`, `/snowfun`, `/snowadmin`, dashboard and graphical
menus stay registered on the same Discord Client. The extra `/snowbridge`
group runs inside that **same** process for linked-account verification.

### Shared database behaviour

- Snowfall web remains the identity authority for Underworld login and
  Discord OAuth account linking.
- An existing linked Discord member is looked up using their Discord
  snowflake; its canonical player ID comes from the PostgreSQL identity
  tables, not from a user-supplied option or text message.
- The existing `/snow` engines use a PostgreSQL adapter that translates
  bound Discord IDs to canonical player IDs. Ownership IDs read back for
  legacy menus/replay comparisons are translated back for presentation.
- The website continues to use `PostgresStore` directly and always sees
  canonical BIGINT IDs. No secondary score database or asynchronous sync.
- Unlinked Discord members cannot invoke game slash commands; the
  public persistent dashboard also checks the link before acting.
- `/snowbridge link` and public help remain available without linking.
- OAuth linking still refuses conflicting accounts or pre-existing
  standalone Discord game histories. No automatic data merge.

### IMPORTANT — no new OAuth application required

Use the **existing** bot's Discord Application ID and OAuth client secret.
No new bot token, guild or app installation is needed. The bot and OAuth
identity verifier belong to the same Discord application, but the secret
is used **only by Snowfall-Web-QA**, never in the existing bot's Discord
service or front-end JavaScript.

You do not need OAuth settings to build and run automated tests. Before
a real Discord account can be linked, open the **existing** application
in Discord Developer Portal → OAuth2 and register exactly:

```
https://snowfall-web-qa-staging.up.railway.app/v1/auth/discord/callback
```

Set the following private Railway variables on **Snowfall-Web-QA**:

- `SNOWFALL_DISCORD_OAUTH_CLIENT_ID` — existing Application ID
- `SNOWFALL_DISCORD_OAUTH_CLIENT_SECRET` — existing app OAuth client secret
- `SNOWFALL_DISCORD_OAUTH_REDIRECT_URI` — exact URL above

The flow uses the `identify` OAuth scope, a five-minute single-use
state and PKCE; the user signs in to Underworld first and clicks
**Link Discord account** in Snowfall.

**Never share** the client secret, bot token or database password in a
public channel, GitHub issue, browser JavaScript or chat transcript.

## Optional controlled activation of QA on the existing Railway worker

**Do not deploy this feature branch or change the existing worker's
database variables until GitHub acceptance passes and the launch operator
has confirmed a backup/recovery path.** When activating for testing,
change the existing **Operation Snowfall** Railway service, *not* the
Snowfall-Web-QA service:

- Source branch: `feature/v2.9.4b-existing-discord-bot`
- `SNOWFALL_SHARED_MODE=qa`
- `SNOWFALL_DB_BACKEND=postgres`
- `SNOWFALL_SEASON_KEY=web-qa-2026`
- `SNOWFALL_DATABASE_URL` — a private connection URI for the **same
  isolated `snowfall_web_qa`** logical PostgreSQL database used by
  Snowfall-Web-QA (never the source `railway` database).
- Keep the **existing** `DISCORD_TOKEN`, `SNOWFALL_GUILD_ID`, admin IDs,
  channels and mounted `/data` volume unchanged.

Do not set `SNOWFALL_DISCORD_BRIDGE_ENABLED` or
`SNOWFALL_DISCORD_BRIDGE_TOKEN` on this worker. Do not start
`python -m snowfall.platform.discord_bridge` anywhere else with the
existing token. Only the original `python -m snowfall.railway` process
should connect to Discord.

For QA the startup guard requires the exact existing Railway
project/service, a `production`-named environment, season
`web-qa-2026`, the isolated PostgreSQL database name
`snowfall_web_qa`, and its staging ownership marker. A wrong value
fails closed **before Discord connects**. Although Railway calls the
worker's environment "production", v2.9.4b QA writes only to the
separate, fictional staging game database.

The existing main-branch SQLite worker is **unchanged** while this
feature branch is not connected. A future production cutover must be
handled separately with reconciled season data and a safety review.

## Acceptance

- QA settings cannot select a live database/season or run a second bot.
- Existing worker remains backward compatible with flag unset.
- Link resolution uses the trusted PostgreSQL identity table.
- Legacy /snow crafting writes authoritative PostgreSQL progress;
  web reads the same snowflakes and inventory.
- Repeated Discord actions do not consume resources twice.
- Website crafting is immediately visible in legacy Discord inventory.
- Legacy boss attacks change the exact same Snow Don HP as the website.
- No duplicate gameplay profile is created for the linked Discord ID.
- Only one Discord client in the original worker registers both
  existing slash commands and the additional shared progress commands.

### Live acceptance still required

CI uses a disposable PostgreSQL database and simulated OAuth. It
cannot verify the **real** Discord OAuth consent screen or live guild
interactions without the user configuring the existing application.
After enabling QA, check: Underworld login → OAuth link →
`/snowbridge progress` → `/snow inventory` → `/snow craft` →
website refresh → `/snow boss` → website Snow Don HP →
logout/relogin → unchanged character.

This release is **QA-only** and not a prize-bearing production cutover.
