# Operation Snowfall v2.9.3a — Web Staging Deployment & Integration

## Scope

This release adds a playable, mobile-responsive browser staging app to the
v2.9.3 shared PostgreSQL game engine. It is not a production launch.
The live Discord bot on Railway remains unchanged and the Underworld
website is untouched.

Web HTML, CSS and JavaScript are served by a separate Railway web service
from Dockerfile.web. Browser actions call the exact official game engines
over a same-origin API; no client-side scores, inventory, boss HP or
prize systems.

### Gameplay delivered

- Winter-noir responsive landing page, sign-in, player headquarters
- Three persistent fictional staging accounts for browser testing
- Registration, city selection, snowballs, warmth, scores, regeneration
- PvP opponent discovery, readiness and official throws
- Snow Don shared HP, boss attacks and city-siege challenges
- Cosmetic purchases, equipping, crafting and snowflake balances
- Six-city standings, official leaderboard and browser reconnection
- Existing signed Underworld assertion and Discord OAuth endpoints remain,
  but real credentials and external integrations are not yet configured.

## Database isolation

The new web service is restricted to the exact existing Railway project
Snowfall PostgreSQL Staging (project
43bd3f71-137a-4302-a456-e4c2d637e7a0, environment
f618a365-51e8-4de7-bdfe-360b50868f98).
It requires SNOWFALL_WEB_QA_CONFIRM=CONFIRM_ISOLATED_WEB_QA_DATABASE.

The original imported PostgreSQL database named railway is queried only
to confirm schema version 11. The staging bootstrap creates a **new logical
database** snowfall_web_qa in the same staging PostgreSQL instance and
migrates a generated schema-v11 dummy SQLite snapshot into it. No live
player data is imported or changed; no production Railway service is touched.
Both logical databases still share one PostgreSQL server, volume, CPU and
physical backups.

Six fictional opponents start the QA seven-day season. Additional users
can register through the browser; a one-time 60-snowflake QA-only bonus
makes purchases testable. Fake opponents are kept eligible for PvP testing.
An expired QA season never resets automatically to avoid silently deleting
test history.

## Staging deployment

Create a new Railway service in the staging project from
rblackburn0784-ai/Operation-Snowfall on branch
feature/v2.9.3a-web-staging. Use Dockerfile.web, one replica,
healthcheck /v1/health and a generated Railway HTTPS domain. No extra
Railway database service is needed.

Required service variables:

- SNOWFALL_API_ENABLED=1
- SNOWFALL_DB_BACKEND=postgres
- SNOWFALL_API_SEASON_KEY=web-qa-2026
- SNOWFALL_WEB_QA_CONFIRM=CONFIRM_ISOLATED_WEB_QA_DATABASE
- SNOWFALL_DATABASE_URL = staging Postgres service DATABASE_URL reference
- SNOWFALL_WEB_PUBLIC_BASE_URL = exact public HTTPS service origin
- SNOWFALL_WEB_DEMO_ACCESS_CODE = private random 28+ character code

Leave SNOWFALL_WEB_ALLOWED_ORIGINS unset (same-origin only).
Leave Underworld assertion secrets and Discord OAuth credentials unset until
separately configured. The temporary demo login is not a production auth
provider. Never place private secrets in GitHub or frontend JavaScript.

When the service starts, it validates the exact Railway project/environment,
explicit consent, original imported database name and schema, destination
database marker, and target season before any gameplay writes.

## Security and rollout

- Sessions: secure 12-hour HttpOnly SameSite=Lax cookies, hashed server-side,
  CSRF required on mutations, no browser localStorage tokens.
- Demo login: high-entropy staging code, six failed attempts per ten-minute
  IP bucket, three distinct fictitious accounts.
- External login: signed short-lived Underworld assertions and Discord OAuth2
  remain optional; Underworld account passwords are never passed to Snowfall.
- All BIGINT player references are serialized as decimal strings.
- HTTP responses disable caching, CORS is same-origin only, and identity
  conflicts are rejected rather than silently merging active player profiles.

## Boundaries

The live Discord bot still resolves Discord IDs directly. Linking a
previously Underworld-only identity does not yet make its Discord commands
use the canonical linked player ID. A separate Discord adapter integration
is necessary for genuine cross-platform shared progress.

The staged website currently stores its **own dummy scores**, not live
Discord production progress. No prizes are awarded. No real Underworld
website or production environment is modified.

Production cutover requires a fresh populated SQLite backup, reconciled
migration, separate live PostgreSQL backup/restore, Discord identity adapter
integration, auth hardening and rollback rehearsal. Do not switch production
to this staging database.

## Acceptance

Run the full pytest suite across Linux and Windows and PostgreSQL CI.
Verify /v1/health, static assets, invalid PIN protection, successful demo
session, registration, boss attack, PvP, shopping, city standings and
persistence. Confirm original imported staging database unchanged.
