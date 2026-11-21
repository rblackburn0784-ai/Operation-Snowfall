# v2.9.5b — Post-deployment QA Smoke & Discord World Button Repair

## Scope and safety

Review the live v2.9.5a staged QA release on 21 November 2026,
including the existing Discord bot, Snowfall-Web-QA, Underworld-Login-QA
and staging PostgreSQL. This is still **fictional QA / NO REAL PRIZES**.
No player reset, score adjustment, account relink, new bot, or token change.

The smoke report distinguishes **observed live evidence**, **previously
verified linked-character behaviour**, and **manual live checks still needed**.

## Live infrastructure — observed from Railway

- Snowfall-Web-QA, Underworld-Login-QA, staging Postgres and existing
  Operation-Snowfall Discord worker are all **online**, each with 1/1 replicas.
- No crashed replicas, deployment failures or outstanding Railway warnings
  in the eight-hour inspection window.
- Snowfall-Web-QA is deployed from v2.9.5a commit
  `4175003d09004df268a995155dbec9734235e99e`,
  using healthcheck `/v1/ready`.
- Existing Discord worker is deployed from the *same* commit, in isolated
  PostgreSQL season `web-qa-2026`.
- The bot logs confirm the **original pre-cutover SQLite backup was verified**,
  five slash command groups synchronised, and the existing Discord gateway
  connected to the event guild.
- Website HTTP metrics in the inspected eight-hour window: 659 requests,
  588 2xx, 14 3xx, 57 4xx, **zero 5xx**. Authenticated browser
  requests to `/v1/game/me`, `/v1/game/progress`,
  `/v1/game/targets`, `/v1/game/world`,
  `/v1/game/wardrobe` and `/v1/verification/status`
  have returned HTTP 200 since the deployment.
- The public favicon still returns 404; minor cosmetic issue for v2.9.6.

## Issue discovered — Discord Unknown interaction 10062

At **2026-11-21 16:48 UTC**, the live Discord bot raised an uncaught
`discord.errors.NotFound: 404 Not Found (error code: 10062):
Unknown interaction` in `WorldView._attack` after a user clicked
**Attack Snow Don**.

Cause: the button's interaction check performed cross-project identity
and Underworld-link database queries before the callback acknowledged
the Discord interaction. This may exceed Discord's approximately
three-second acknowledgement deadline. This is a UI response failure;
it is not proof that gameplay progressed, and the failed click was on
the *confirmation screen*, not the score-changing attack itself.

**Hotfix:** For real boss/siege attack and confirm/cancel component
buttons, the shared-QA worker acknowledges the component *before*
performing the slower ownership lookup. On successful validation it
edits the original deferred message once; on a revoked/unlinked
character it sends a private denial, without doing the game action.
Other menu/navigation controls and the standalone SQLite mode retain
their previous response semantics. Tests exercise both paths and
ensure no double Discord acknowledgement.

## Staff audit — existing real command

The existing `/snowadmin launch-check` is **read-only** in shared QA,
requires host permissions, validates the staging database ownership
marker, and checks:

- Count of registered Underworld+Discord linked active characters;
- Fictional/unlinked/retired players and noncanonical account rows;
- Orphan or out-of-range game resources;
- The four immutable gameplay ledgers;
- Count of prize awards (**must be zero**);
- Explicit blocking conditions and warnings.

**Important:** Staff audit results cannot be inferred from server health.
No real staff command execution or its private Discord result was
available through Railway. A host must execute `/snowadmin launch-check`
and review the report. QA may legitimately contain fictional NPC
warnings; treat prize awards or orphan resources as blockers.

## SnowDude and cross-platform test

Prior live QA screenshots had already proved Discord and web share
canonical player `6000000000000000002`, and the same inventory, score
and Snow Don HP after real Discord crafting and web gameplay. That was
on the prior version, not a fresh v2.9.5a result.

The new v2.9.5a deployment's authenticated `/v1/game/progress` and
`/v1/verification/status` endpoints returned HTTP 200. Railway logs
do **not** include the response bodies, so current SnowDude points
or item counts must not be guessed.

Host/player manual gate:

1. Sign into Underworld QA → Snowfall; confirm SnowDude's linked
   character ID remains `6000000000000000002`.
2. Start the website's 15-minute Cross-Platform Test Lab check, then
   use `/snowbridge verify` in the **existing** Discord guild.
3. Use `/snowbridge progress` and compare score, Snowflakes, snowballs,
   inventory and Snow Don HP to website `Verify Progress`.
4. Craft one inexpensive QA item in Discord. Confirm one deduction
   and one inventory item on both clients. Then perform a web action
   and verify its result via Discord. Retries must not double-charge.
5. Check **Attack Snow Don** from the legacy `/snow` menu: clicking
   must open a confirmation *without* Unknown interaction. Do not
   hit Confirm Attack unless you intend a real QA game action.
6. Run read-only `/snowadmin launch-check` and verify no blocking
   integrity results or prize rows. Keep any warning screenshot private.
7. Check PvP with a second **consenting** linked QA character, daily
   caps and cooldowns. Never attack production/player accounts.

**Do not claim launch readiness until both the bot button and the
organiser audit are checked in the real Discord guild.**

## Rollback

If this bot-only acknowledgement patch fails, restore the original
`v2.9.5a` bot commit `4175003d09004df268a995155dbec9734235e99e`
without changing its Railway variables or the persistent /data backup.
Snowfall-Web-QA can remain on v2.9.5a. No database migration is
required by v2.9.5b.
