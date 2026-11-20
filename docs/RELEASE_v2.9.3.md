# v2.9.3 — Shared Game Engine & Cross-Platform Foundations

## Scope and status

This is an **opt-in development branch**. The production Railway Discord
worker remains on its existing SQLite version, without a new API process or
changes to its volume. The Underworld website is not modified by this release.

v2.9.3 provides a concrete PostgreSQL-backed, platform-neutral game facade,
an optional FastAPI server, verified identities and one-time login assertions,
OAuth-based optional Discord linking, and durable session/cross-platform
foundation. Full Underworld website UX and end-to-end Discord command
principal resolution are later integration steps, *not* claimed here.

### Data architecture

- Existing v11 Snowfall game tables and scores are the sole authoritative
  ledger for PvP, economy, Snow Don and leaderboards.
- `snowfall.platform.game.SharedGame` delegates to the **existing** engines.
  No mirrored scores, localStorage progress, web-only inventories, alternate
  prize ledger or independently generated boss HP.
- `snowfall.platform.identity.IdentityRepository` provisions separate
  `snowfall_identity_*` tables in the **same PostgreSQL database**, with
  version marker 1. It never alters the 33 v11 game tables.
- Verified Discord logins retain existing numeric Discord player IDs. New
  Underworld-first accounts receive canonical numeric IDs from a reserved
  high-range PostgreSQL sequence. Existing game SQL can continue using its
  `discord_user_id` column name with canonical IDs without schema migration.
- Unique constraints ensure one Underworld character per Underworld account,
  one account per character and one player principal per verified external
  identity. Links never merge two existing gameplay histories automatically.
- Discord commands **currently still use their legacy Discord IDs directly**.
  Linked Underworld-first players must not be promised shared Discord actions
  until the Discord adapter uses `resolve_discord` for every gameplay call;
  the identity repository and facade establish that next integration point.

### Web API

Separate optional application, `python -m snowfall.platform.api`. Endpoints:

| Route | Authentication | Behaviour |
| --- | --- | --- |
| GET /v1/health | none | API state, version |
| POST /v1/auth/underworld | signed short-lived assertion | create browser session |
| POST /v1/auth/discord/start | none (login), session+CSRF (link) | OAuth2 PKCE login/link |
| GET /v1/auth/discord/callback | verified OAuth2 code+state | login/link result |
| GET /v1/auth/session | HttpOnly session | principal, CSRF, linked accounts |
| POST /v1/auth/logout | session+CSRF | revoke hashed session |
| GET /v1/game/leaderboard | none | shared official scores |
| GET /v1/game/me, /targets, /inventory, /wardrobe | session | same engine snapshots |
| POST /v1/game/register, /ready, /wardrobe/equip | session+CSRF | official game actions |
| POST /v1/game/throw, /boss, /siege, /craft, /wardrobe/purchase | session+CSRF+Idempotency-Key | official transactional actions |
| GET /v1/game/raid?day=1 | none | official Snow Don progress |

The API never accepts arbitrary `player_id` as its acting identity.
Authenticated player identity is extracted from the server-side session.
A `target_player_id` is an opponent identifier, **not an acting user**.
`Idempotency-Key` is scoped to authenticated player and operation.
Existing game transaction, cooldown, score-cap, unique source and anti-fraud
logic remains authoritative.

### Underworld login contract

**No player password is sent to Snowfall.** Underworld authenticates the
existing account and its single character in its own backend. Underworld
then creates a signed assertion for Snowfall and submits it over HTTPS.

Wire format:

```text
base64url(canonical JSON bytes).base64url(HMAC-SHA256(secret, first-segment ASCII))
```

Required claims:

```json
{
  "iss": "underworld",
  "aud": "operation-snowfall",
  "account_id": "the immutable existing account ID",
  "character_id": "the immutable one-character ID",
  "character_name": "the character display name",
  "iat": 1795150000,
  "exp": 1795150060,
  "jti": "unique random assertion ID"
}
```

Example timestamps are illustrative, not a real token. Assertions must have
a maximum lifetime of 120 seconds; `iat` must be recent and `jti` must be
single-use (stored as a SHA-256 digest). Use a random shared secret at least
32 bytes long, stored in private environment variables on **both server
backends**, never in frontend JavaScript or GitHub. HTTPS is mandatory
outside explicitly enabled localhost development.

The Underworld account and character IDs must be stable and unique, not
usernames or mutable display names. The Underworld website's authentication
backend must still implement the assertion issuance and signed handoff;
the Snowfall side is ready to verify it.

### Discord linking

The web API can initiate Discord OAuth2 with the `identify` scope, a
five-minute single-use state, PKCE and the fixed allowlisted callback URI.
Discord's authenticated `/users/@me` response is the only accepted
Discord ID. Linking requires an active Snowfall session and a CSRF header.
A Discord account with existing unlinked game progress is **rejected** rather
than silently moved to a different principal. A staff-reviewed merge process
must be separately designed before such progress can be reconciled.

### Session security

12-hour, random HttpOnly, Secure, SameSite=Lax cookie; only the token's hash
is stored server-side. State-changing requests require an `X-Snowfall-CSRF`
header derived from an authenticated same-origin session. OAuth state and
Underworld assertion nonces are one-time. No passwords or OAuth access
tokens are stored; HTTP responses and OAuth callbacks disable caching.
CORS is disabled by default; if enabled, it uses an explicit origin list.
Deployment does not expose a wildcard credentialed CORS origin.

### Safe staging instructions

1. **Never** change the running production Railway Dockerfile, branch,
   database URL or worker settings as part of this release.
2. Use the already-isolated PostgreSQL staging service. For isolated
   PostgreSQL CI tests the GitHub workflow creates a disposable database.
3. Install locally:
   `python -m pip install -e ".[dev,postgres,web]"`
4. Set a local private `SNOWFALL_DATABASE_URL` pointing at the staging
   PostgreSQL tunnel. Check it carefully before any schema operation.
5. Provision the *additional identity tables* explicitly, one time:
   ```powershell
   $env:SNOWFALL_PLATFORM_ENV = "staging"
   python -m snowfall.platform.bootstrap --install --confirm INSTALL_IDENTITY_SCHEMA
   python -m snowfall.platform.bootstrap --check
   ```
6. Add a **separate** web service using `Dockerfile.web`, with
   `SNOWFALL_DB_BACKEND=postgres`, `SNOWFALL_API_ENABLED=1`,
   `SNOWFALL_API_SEASON_KEY`, private `SNOWFALL_DATABASE_URL`,
   and an HTTPS `SNOWFALL_WEB_PUBLIC_BASE_URL`. Add private
   Underworld signing secret and Discord OAuth secrets only when those
   integrations are deliberately enabled. No Discord bot token is required
   for the API.
7. Test `GET /v1/health`, identity handoffs, CSRF-protected action calls,
   and reconnection using dummy users. Do not connect it to real Underworld
   accounts until assertion issuance is implemented there.
8. Keep the web service non-public or access-controlled during staging.
   Never perform blind production import into a nonempty database.

### Production cutover and rollback

v2.9.3 is **not** approval for production cutover. A fresh, consistent
SQLite snapshot, verified migration, downtime/write freeze, PostgreSQL
backup/restore testing, cross-platform Discord adapter integration and
reconciliation/rollback procedure are required before live use. Returning
to the old SQLite snapshot after PostgreSQL-only actions discards those
actions unless explicitly reconciled.

## Release acceptance tests

- Original SQLite v11 regression suite remains green on Windows and Linux.
- CI PostgreSQL migration v11, constraint checks, PvP, complete Snow Don
  defeat and replay are green.
- v2.9.3 contract tests cover web opt-in, assertion expiry/signatures,
  mandatory CSRF, secure cookies, trusted Discord OAuth identity, session
  access, idempotency and shared canonical gameplay.
- v2.9.3 PostgreSQL integration tests cover one-character uniqueness,
  nonce replay, verified Discord legacy account reuse, conflicting links,
  session expiry/revocation, OAuth state replay and shared ledger reads.

### Known follow-up work

- Underworld server code must issue signed assertions using its **existing**
  account/character session, not Snowfall passwords.
- Adapt all Discord menus, slash commands and persistent views to resolve
  linked canonical IDs through the shared facade; leave practice/simulation
  databases fully isolated.
- Design explicit admin-reviewed merging if someone has game progress on
  both identities.
- Build the actual browser UI and cross-domain login handoff; this release
  intentionally supplies the authenticated API rather than finished web art.
- Rate limits, observability, browser integration testing, migration rehearsal
  on a populated production snapshot and production disaster recovery remain
  prerequisites for public launch.
