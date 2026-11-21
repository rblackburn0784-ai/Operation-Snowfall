# Operation Snowfall v2.9.5 — Cross-Platform Consolidation & Launch Readiness

## Release scope

**QA-first, no real prizes.** Build on the working v2.9.4e1 single Discord bot
cutover: the original Discord application and Underworld-connected Snowfall Web
share the same isolated `snowfall_web_qa` PostgreSQL game and canonical player
IDs. There is no second bot, no mirrored score database and no production
identity merge. The original, verified SQLite rollback snapshot is preserved.

v2.9.5 is a *hardening* release: remove access-control gaps in legacy
Discord interfaces, improve outage/reconnect handling and make QA identity
and prize status unmistakable.

## Audit findings and repairs

### 1. Legacy Discord menus / modals bypassing account-link checks

**Finding:** Discord slash commands pass through the global
`CommandTree.interaction_check`, but persistent `Dashboard` buttons,
`MenuView` children, `CombatMenu`, `EconomyView`, `WorldView`,
`WorldConfirm`, `CityPicker`, registration modals and Snowfall Wire
submissions can arrive without invoking the tree. Most checked only
guild/owner, not whether the Discord account was *still* linked.

**Fix:** `platform.discord_security.check_linked_player` performs a fresh
trusted `principal_for_discord` lookup on every protected UI callback.
Transient identity-database errors refuse an action; no fallback to a
discord-snowflake game record, no new second account. This also protects
old, still-open menus when a player changes or loses an account link.

The original standalone SQLite bot has no unified identity service and
retains its historical, unchanged access behaviour.

### 2. Staging safety of production host commands

**Finding:** The original host/admin slash commands include score
adjustment, launch approval, event phase changes, prize status,
announcements, and a test-day reset panel. Although intended for
production/event operations, they were still callable on shared QA.

**Fix:** In shared-QA mode, `/snowadmin status` and
`/snowadmin test-status` remain read-only; all other legacy host
commands and old interactive admin panels refuse with an explicit
message. No official prizes, host score overrides, or pinned production
broadcasts may be changed via the QA bot.

### 3. Discord command sync, disconnects and outages

**Finding:** Discord API 429/5xx responses during slash-command
synchronisation could terminate startup immediately.

**Fix:** Bounded retry for transient 429/500/502/503/504 responses
(three attempts); 403 Missing Access and other permanent failures
still fail closed. The bot logs the count of synced command groups.
The shared-game gateway provides a consistent, private error message
when a backend call fails without reporting a success it cannot prove.

### 4. Website uncertain-request replay

**Finding:** A fresh idempotency key was generated on every browser
click. If a valid request was committed by PostgreSQL but its response
was lost, manually retrying created a *different* action capable of
spending currency or snowballs again.

**Fix:** For a signed-in canonical player and identical action payload,
the browser remembers the action ID after timeouts, broken connections
and 5xx outcomes. Retrying reuses the same idempotency key, allowing
the server's immutable event ledger to return a replay result. Only
a successful response or conclusive 4xx clears the pending key.
A subsequent legitimate action then receives a fresh key.

A bounded 15-second fetch timeout provides feedback rather than
indefinitely leaving the UI spinning. A lost response is described as
**possibly successful**, not as definitely failed. Signing out or
changing accounts clears/isolates pending action keys. Web mutations
continue to use the anti-CSRF token.

### 5. Reliable launch-readiness and QA UI

- `GET /v1/health` remains lightweight liveness; version reflects 2.9.5.
- `GET /v1/ready` performs actual PostgreSQL identity/schema and shared
  game connectivity checks. A database outage returns HTTP **503**
  with a generic non-secret error; the check is read-only.
- Original Discord dashboards/private menus explicitly say
  **SHARED QA — NO REAL PRIZES** even though Railway calls the bot's
  deployment environment `production`.
- Public rules explain that the actual MR password is never requested
  and that linking Underworld ↔ Discord is required for shared progress.

## Test matrix

Existing suites remain mandatory: migrations/PostgreSQL adapters,
Underworld assertions, Discord OAuth PKCE and conflict rejection,
canonical ID/account reconciliation, shared in-game balance,
PvP/world engine caps, idempotent game ledgers, registered character,
score/raid/crafting, and verified SQLite backup/rollback.

New v2.9.5 suites:

| Test | Evidence |
|---|---|
| `tests/test_v295_ui_security.py` | Old menu/registration/World/Economy/Combat/Wire callbacks cannot bypass linking; DB outage fails closed; host mutations locked; original SQLite behaviour retained |
| `tests/test_v295_browser.mjs` | Lost HTTP responses and 5xx reuse the same idempotency key; 4xx clears it; later legitimate action gets a new key; keys scoped to player |
| `tests/test_v295_postgres.py` | Two unrelated linked players isolated; six concurrent duplicate Discord crafting requests deduct once; a second actor cannot steal the action ID; restart/reconnect sees identical progress; read-only readiness failure is HTTP 503 |
| Full CI matrix | Linux Python 3.12, Linux Python 3.13, Windows Python 3.13, PostgreSQL 16 integration; compile/ruff and browser syntax |

## Feature parity status — no overclaim

| Capability | Existing Discord /snow | Snowfall Web |
|---|---|---|
| Underworld/Discord identity, registration | Yes, same canonical player | Yes |
| PvP targeting, readiness, attacks | Yes | Yes |
| Shared snowballs, warmth, score and equipment | Yes | Yes |
| Snow Don, city siege, rankings | Yes | Yes |
| Crafting and cosmetic wardrobe | Yes | Yes |
| Quests, catalogue, scoreboard and city information | Yes | Core API |
| Equipment activation and guard controls | Full legacy Discord menus | Not all legacy actions exposed |
| Winter Arcade, mysteries, news, illustrated trophies | Extensive legacy Discord UX | Not fully reproduced |
| Host controls / prizes | Disabled on shared QA | Not a real-prize launch surface |

**Cross-platform progress is unified; full feature parity is NOT yet
complete.** The website can be used independently for its currently
available modes, and Discord retains additional legacy modes. Avoid
advertising an entirely identical feature set on both platforms.

## Deployment and acceptance plan

1. Verify all GitHub Actions jobs pass, including `v295` tests.
2. Verify existing live bot still on `v2.9.4e1`, Snowfall-Web-QA on
   `v2.9.4e`, and both healthy. Preserve the original SQLite backup
   and existing staging PostgreSQL; never reset SnowDude or other
   linked QA player progress.
3. Stage **only** v2.9.5 GitHub source branch on the two existing
   Railway services. No variable, Discord token, PostgreSQL credential,
   environment, volume or public domain changes are required.
4. On explicit deployment approval, update Snowfall-Web-QA first.
   Verify `/v1/health` and **`/v1/ready`** return success.
   Invalid/unavailable canonical DB must return 503 from readiness.
5. Update the **existing** Operation-Snowfall Discord service on the
   same shared QA variables; ensure **one worker and the same token**.
   Verify original SQLite pre-cutover backup marker is still checked,
   command sync succeeds and `/snowbridge verify` appears in the
   existing guild.
6. Log into Snowfall Web through Underworld as the existing linked
   character; run `/snowbridge verify`; craft on Discord and read
   web inventory and snowflake deductions, then reverse the operation.
7. Test one real PvP action with two consenting linked QA characters,
   cooldowns, daily caps, failed/blocked actions and duplicate retries.
   Test one Snow Don action and compare HP on both surfaces.
8. Test menu navigation, Discord old/private buttons, registration
   modals, reconnect/restart, and error messages with the real guild.
   Read-only host diagnostics must remain available, host scoring/prize
   operations refused in QA.
9. Only after a separate launch decision, revisit the full website
   feature-parity backlog, privacy notice, real-prize allocations,
   event dates, moderator roles and production environment strategy.

## Rollback

Return the original bot source to its previously verified
`feature/v2.9.4e1-existing-bot-qa-cutover` commit and web to the
previously verified `feature/v2.9.4e-cross-platform-verification`
commit. Keep the original `SNOWFALL_DATABASE_URL`, existing Discord
token, Underworld linking and isolated QA season as-is; there is no
schema migration in v2.9.5. If necessary, revert the bot all the way
to the original `main` SQLite config using the procedure in
`RELEASE_v2.9.4e1.md`. Do not merge QA scores into the original
prize-bearing game.

**Release gate:** Code passing CI is not proof of an actual final
in-guild acceptance test or prize-bearing launch approval.
