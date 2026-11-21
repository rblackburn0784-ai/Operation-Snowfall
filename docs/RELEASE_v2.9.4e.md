# Operation Snowfall v2.9.4e — Cross-Platform Gameplay Verification

## Goal

Verify that a linked Underworld character (such as SnowDude), its existing
Discord login, and the standalone Snowfall web interface read and write
**one canonical Snowfall game**, not mirrored scores or disconnected progress.

v2.9.4d proved shared identity. v2.9.4e adds an auditable, reproducible
proof of **actual gameplay** across both platforms, including the original
Discord bot's gameplay engines.

## What is built

- A 15-minute, player-bound verification baseline under **Your Connected
  Identities** on Snowfall Web. No points, equipment or currency are
  generated merely by starting or checking a verification.
- An opt-in `/snowbridge verify` command running in the **existing**
  Discord worker. It trusts only the real Discord interaction's user ID;
  the PostgreSQL identity mapping resolves that ID to the original
  Underworld canonical BIGINT player. A fake Discord ID sent to a website
  cannot complete the check.
- A verification table in the **isolated QA PostgreSQL** identity schema,
  with an expiring timestamp, baseline snapshot, Discord-verified timestamp
  and last Discord-read snapshot. No new auth tokens or bot applications.
- Read-only verification endpoints:
  - `POST /v1/verification/start` (web session + CSRF required).
  - `GET /v1/verification/status` (same authenticated player).
  - Discord acknowledgment happens inside the existing bot, not by a
    public HTTP endpoint.
- Immutable event proof for **Discord** via `item_events`,
  `pve_events` and `combat_events`. The event must belong to the
  linked canonical player, occur after the web baseline, and have an
  actual Discord interaction ID (existing numeric IDs or the
  `discord-bridge:` command prefix).
- Separate **Web** gameplay evidence uses the trusted `web:`
  idempotency prefix, never an unauthenticated browser claim.
- Website comparison shows score, Snowflakes, snowballs, warmth, boss HP,
  inventory delta, real event counts and a distinct flag when Discord
  has re-read progress after a website action.
- Verification is disabled outside `web-qa-2026`. No prize,
  account-reconciliation, or production scoring changes.

## Player walkthrough

1. Log into **Underworld QA**, enter Snowfall, verify **Underworld connected
   · Discord connected**, and keep the same player/character.
2. Open **Cross-Platform Test Lab** and click **Start 15-minute verification**.
   This captures an authoritative baseline. Do not start a second browser
   identity or register a new character.
3. In the existing Snowfall Discord guild, run **`/snowbridge verify`**.
   This proves the Discord identity can read the same canonical player.
   On the website, use **Check shared progress**. Discord confirmation
   changes to verified; gameplay remains pending until a real action.
4. In Discord, run **`/snowbridge craft`** (e.g. cocoa if affordable),
   **`/snowbridge boss`**, or the corresponding existing `/snow`
   command. Refresh the website. The **real Discord gameplay event** is
   confirmed in PostgreSQL, and the corresponding inventory, snowflakes,
   score and/or Snow Don HP reflect the action.
5. Optional reverse test: craft an item on **Snowfall Web**, then repeat
   **`/snowbridge verify`** on Discord. Website status confirms that
   Discord re-read the updated player progress after the web move.
6. Retrying the same Discord interaction or web idempotency key must not
   pay twice, deduct currency twice or damage the boss twice. Starting
   a fresh test resets the *proof baseline only*, not game stats.

The player may see resource regeneration between two reads, so a single
snowball count changing is **not** conclusive proof. The backend requires
new game events and an authenticated Discord acknowledgment.

## Current infrastructure and release boundary

**The existing Operation Snowfall Discord bot has NOT been cut over.** Its
Railway service remains on `main`, the original bot token and SQLite.
Snowfall-Web-QA is connected to the independent `snowfall_web_qa`
PostgreSQL database, and the account is linked there.

This branch adds the new commands to the *original* bot code; merely
deploying the web portion does not make Discord register them.

To run the REAL Discord ↔ Web comparison, an operator must perform a
controlled **single-worker QA cutover** on the original Discord app:

- Back up the old SQLite volume and confirm a rollback procedure.
- Make sure the original production bot has no outstanding event
  participation and schedule downtime; do not run two workers using the
  same Discord token.
- Verify network reachability from the existing bot project to the
  isolated QA PostgreSQL database. Railway private network addresses
  may not work across separate projects. Do not substitute the production
  `railway` database or use the public web URL as a DB connection.
- On the existing Operation Snowfall bot service ONLY, use the explicitly
  guarded QA variables (see `docs/RELEASE_v2.9.4b.md`):
  `SNOWFALL_SHARED_MODE=qa`, `SNOWFALL_DB_BACKEND=postgres`,
  `SNOWFALL_SEASON_KEY=web-qa-2026`, and a private, reachable
  `SNOWFALL_DATABASE_URL` to **`snowfall_web_qa`**. Keep the existing
  `DISCORD_TOKEN`, guild, admin IDs and volume.
- Switch its source to
  `feature/v2.9.4e-cross-platform-verification` ONLY as part of that
  coordinated cutover. The startup guard validates Railway service ID,
  QA season, PostgreSQL DB name and staging ownership marker before
  the original bot can connect.
- Validate `/snowbridge verify` appears on the existing Discord app,
  then follow the player walkthrough above.
- Roll back by reselecting the original source branch and removing the
  QA shared-mode configuration (without deleting the original SQLite
  game volume). Do not move QA scores into official event results.

**Do not enable this integration on the existing live bot without
explicit authorisation for that worker's QA cutover.** The web feature
can be independently staged and previewed without touching Discord.

## Automated acceptance

`tests/test_v294e_postgres.py` uses a local disposable PostgreSQL
database and includes:

- Browser session and CSRF checks, both provider links, original
  Underworld player ID and no duplicate registered Discord profile.
- A Discord acknowledgment that cannot be forged through HTTP or by an
  unlinked Discord user.
- Baseline and expired proof behaviour.
- A real Web crafting event, shared balance/inventory, duplicate key
  protection and subsequent Discord-read receipt.
- A real Discord crafting event, repeated interaction protection and
  immediate website game/delta verification.
- The **original** `/snow` EconomyEngine, using the canonical player via
  the guarded PostgreSQL adapter, reading the same inventory.
- A Discord Snow Don attack followed by a website boss HP check and
  replay protection.
- Relogin continuity and the same unchanged canonical player ID.
- No need for real Discord OAuth secrets, GitHub permissions or a live
  Discord token during CI.

Passing tests is **not proof that the actual Railway Discord worker has
been cut over**. The real-guild walkthrough is the release gate.
