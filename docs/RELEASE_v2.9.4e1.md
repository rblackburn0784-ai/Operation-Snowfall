# Operation Snowfall v2.9.4e1 — Existing Discord Bot → Shared Web QA Cutover

## Aim

Keep the **existing Operation Snowfall Discord application, one Discord token,
one Discord guild and all original /snow commands**, and connect it to the
same isolated PostgreSQL `snowfall_web_qa` game used by Underworld and
Snowfall-Web-QA. The new `/snowbridge verify` then provides real-guild
Discord → web and web → Discord verification using the linked player's
canonical BIGINT identity and authoritative shared event history.

**This is an isolated QA test season.** Never transfer official event
credits, prizes, or balances from the original SQLite season. The original
database remains on the bot's persistent `/data` Railway volume.

## Infrastructure findings

- Original Discord service: **Operation Snowfall → Operation-Snowfall**,
  Railway service ID `39d25075-0fb8-498a-b32c-7a982b7b38c1`,
  production environment (Railway naming only).
- The mounted **5 GB /data volume** currently contains the original bot
  database. The worker reuses its existing `DISCORD_TOKEN` and server.
- Snowfall PostgreSQL Staging is a *different Railway project*. Its private
  `postgres.railway.internal` address **cannot** be reached from the
  original Discord service. A public TCP proxy is already active at
  `junction.proxy.rlwy.net:21957`.
- The dedicated logical QA database is **`snowfall_web_qa`**. Do not connect
  to `railway` or the production event database.
- The connected Railway integration lists names of secrets **but does not
  reveal secret values**. You must enter the DB connection URL directly in
  Railway's secure variable editor, not in GitHub or this chat.

## First: secure credential handoff (one-time, user action)

Open the Railway dashboard and find the **Snowfall PostgreSQL Staging**
project → **Postgres** service → **Variables**. Reveal or copy the Postgres
**DATABASE_PUBLIC_URL**, not DATABASE_URL (the latter uses private DNS).

In the same project, DATABASE_PUBLIC_URL may end in `/railway`. The bot
must instead use the existing isolated **`/snowfall_web_qa`** logical
database. Change only the **database name** in the public URL to
`snowfall_web_qa`, and add `sslmode=require` to its query string,
preserving its actual username, password and host/port. Structure:

```text
postgresql://<POSTGRES_USER>:<PRIVATE_PASSWORD>@junction.proxy.rlwy.net:21957/snowfall_web_qa?sslmode=require
```

Go to **Operation Snowfall → Operation-Snowfall → Variables** and add
`SNOWFALL_DATABASE_URL` with that full private connection string.
Prefer staging the variable with the other changes; **do not share the
password in chat, screenshots or GitHub**. Do not delete or rotate the
staging database credentials.

If copying DATABASE_PUBLIC_URL is inconvenient, build the URL using the
same staging Postgres connection username/password shown in the Railway
dashboard. Do not create a new Postgres database: `snowfall_web_qa`
already exists with SnowDude's progress.

## Cutover gates implemented in v2.9.4e1

1. The bot checks it is **the original exact Railway service**, with
   `SNOWFALL_SHARED_MODE=qa`, `SNOWFALL_DB_BACKEND=postgres`, and
   `SNOWFALL_SEASON_KEY=web-qa-2026`.
2. A public DB DSN may only point at the known staging TCP proxy with port
   **21957**, database **snowfall_web_qa**, and TLS `sslmode=require`
   or stronger.
3. Before connecting Discord, the worker validates the PostgreSQL
   **staging ownership marker**, season, identity schema and v2.9.4e
   cross-platform verification table.
4. Before connecting Discord, the worker checks the existing SQLite
   file, creates a WAL-safe, checksummed **pre-cutover SQLite backup on
   the mounted /data/backups volume**, and writes a durable marker for it.
   On subsequent deployments it re-verifies the *original same backup*.
   An absent/corrupt backup prevents startup rather than silently
   overwriting it.
5. Only the original single Discord process connects. All `/snow`
   commands retain the original server's command scope and dashboard.
   `/snowbridge` appears in the same Discord application when the
   shared-QA connection is verified. Unlinked users cannot play.
6. The original SQLite game database is **not migrated or deleted**.
   QA web/Discord gameplay uses the existing canonical PostgreSQL game,
   with one score and one inventory.

## Safe staged Railway configuration

Existing **Operation-Snowfall** service (not a new worker):

| Variable | Required value |
|---|---|
| `SNOWFALL_SHARED_MODE` | `qa` |
| `SNOWFALL_DB_BACKEND` | `postgres` |
| `SNOWFALL_SEASON_KEY` | `web-qa-2026` |
| `SNOWFALL_DATABASE_URL` | Secure URL above; entered by operator |
| `DISCORD_TOKEN` | **Keep unchanged** |
| `SNOWFALL_GUILD_ID` | **Keep unchanged** |
| `SNOWFALL_STARTS_AT_UTC` | Keep unchanged; existing QA season already exists |

Existing service source branch:

`feature/v2.9.4e1-existing-bot-qa-cutover`

Use one replica with the existing /data volume. **Do not run**
`python -m snowfall.platform.discord_bridge` as a separate worker,
and do not create a second Discord application/token.

Before applying the staged Railway patch, check that all tests have
passed and that `SNOWFALL_DATABASE_URL` is set. Deploying with
the wrong URL will correctly **refuse to start** rather than fall back
to SQLite or create a disconnected second character. Secret values
must never be surfaced in deployment logs.

## Live acceptance — real SnowDude account

1. After deploy, check Railway startup logs contain confirmation of a
   verified **pre-cutover SQLite backup**, then the existing bot's normal
   Discord ready log.
2. In Discord, type `/` and confirm **`/snowbridge verify`** (plus
   inventory/craft/boss) are visible in the original Snowfall guild.
3. Open Underworld QA → Snowfall Web, confirm **Underworld connected ·
   Discord connected** and canonical SnowDude ID.
4. Click **Start 15-minute verification** in Cross-Platform Test Lab.
5. Run `/snowbridge verify` in Discord and then refresh the website;
   check the Discord identity receipt.
6. Craft using `/snowbridge craft` or `/snow craft` in Discord, refresh
   the website, compare inventory and Snowflakes. Event receipt count
   must increase exactly once for the actual action.
7. Make a legal Snow Don attack on Discord, refresh the website, and
   confirm the same shared HP/score, with no duplicate damage on retry.
8. Craft once on the web, then rerun `/snowbridge verify`; Discord must
   report the web-updated progress. Log out/in and verify persistence.
9. Check no second registered player exists for the same Discord ID and
   that the original SQLite DB and its backup remain intact.

## Rollback

If QA fails or the database becomes unreachable:

- In the **original Railway bot service**, revert source to the previous
  `main` branch and set `SNOWFALL_DB_BACKEND=sqlite`, unset
  `SNOWFALL_SHARED_MODE` (or clear it), and restore
  `SNOWFALL_SEASON_KEY` to its prior production season.
- Leave `DISCORD_TOKEN`, guild and original mounted volume unchanged.
- `SNOWFALL_DATABASE_URL` can remain as a dormant, private setting but
  should normally be removed after reverting.
- Do **not** copy QA PostgreSQL player records into the original SQLite.
  The original SQLite database has not been overwritten, and the durable
  snapshot is retained on `/data/backups` for an offline restore if needed.
- Never run a second live worker with the same Discord token.

## Automated regression

`tests/test_v294e1_cutover.py` checks:

- Original-service and QA-season safeguards.
- Known staging public TCP port, logical QA DB and TLS requirement.
- Safe refusal of accidental PostgreSQL mode without guarded QA mode.
- New durable SQLite backup, verified manifest and checksum, no overwrite
  after gameplay, missing/corrupted backup refusal.
- Read-only `--check` validation with no bot connection, secrets hidden.
- No external staging DB credentials or live Discord connections in tests.
- Existing bot tree registers `/snowbridge` in the original Discord client.

Earlier v2.9.4e PostgreSQL gameplay integration tests remain required.
