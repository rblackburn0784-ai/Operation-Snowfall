# Operation Snowfall v2.9.5 — Cross-Platform Consolidation & Launch Readiness

**Status:** QA hardening release, not authorisation to start a prize-bearing live event.

## Scope and established baseline

The 21 November 2026 real-guild acceptance test already demonstrated
SnowDude's canonical Underworld player across **Underworld login → Snowfall
Web → existing Discord bot**. The same score, Snowflakes, inventory, and
Snow Don HP appeared on both platforms. Discord and browser actions were
separately identified in the shared PostgreSQL game ledger; repeat attempts
were idempotent.

The original Railway bot is the **only** Discord worker using its established
token and guild. The source/season for the working QA cutover were
`feature/v2.9.4e1-existing-bot-qa-cutover` and `web-qa-2026`.
The original SQLite database was backed up and kept on the /data volume.
The website's working source was `feature/v2.9.4e-cross-platform-verification`.

v2.9.5 is a hardening branch on top of that baseline, not a new data
migration or a claim that every winter game has a browser UI.

## Changes

### 1. Identity & menu security

- Every historical Discord UI component family must enforce the current
  verified Discord identity: Main Menu, combat targets and confirmations,
  crafting/use/guard/quest menus, boss and siege confirmations, persistent
  Dashboard, City Picker and registration modal.
- Discord's app command tree check and /snowbridge gateway both refuse a
  **Discord-only first-login** principal until its verified Underworld
  character is linked; this specifically prevents accidentally creating
  a second prize-bearing character before the user links Underworld.
- Stale menus opened **before** a link changed cannot be used as a
  backdoor to registration, spending or combat. Recheck is server-side,
  using the trusted interaction.user.id and identity repository, never a
  client-supplied player ID.
- Unexpected PostgreSQL identity lookup failures fail **closed**, with
  a private, non-sensitive error rather than creating an orphan player.
- Original SQLite-only mode remains backwards compatible: the extra
  linking gate is a no-op when there is no shared identity repository.

### 2. User experience and support

- Discord's persistent dashboard, help and rules clearly identify the
  shared `web-qa-2026` season as **QA / no prizes**. No claims that
  account linking is unnecessary while shared mode is active.
- Discord's app command tree sends a generic private failure when a
  command crashes, without posting SQL traces, connection URLs, secrets
  or a second error for an expected permission check failure.
- The website's Cross-Platform Test Lab and server version now use v2.9.5.

### 3. Operations & reliability

- `GET /v1/health`: cheap process liveness (never implies DB is healthy).
- `GET /v1/ready`: checks current identity schema, game season and
  isolated QA database marker and cross-platform schema; returns 503 with
  a fixed, non-sensitive explanation on database failure.
- `python -m snowfall.platform.launch_audit --confirm READ_ONLY_QA_AUDIT`:
  read-only, aggregate-only QA audit, requiring the exact
  `snowfall_web_qa` logical database and verified ownership marker.
  Counts active/retired players, linked canonical profiles, unlinked
  fictional profiles, orphaned game resources, resource-limit issues,
  immutable events and prize award records.
- A **prize award in the QA database** is a hard audit failure.
  Missing Underworld identity on fictional NPCs is flagged as a warning,
  not quietly treated as a verified game player.
- The audit never mutates accounts, season clock, funds or scores, nor
  prints credentials, player names, Discord IDs or Underworld IDs.
- Original v2.9.4e1 pre-cutover verified SQLite rollback backup, public
  TLS staging PG connection restriction, single-Discord-worker check,
  idempotency, replay protection and receipt checks remain intact.

## Platform parity — present versus not yet exposed

| Feature | Existing Discord bot | Snowfall website | Shared canonical state? |
|---|---|---|---|
| Underworld + Discord identity | OAuth-linked login | Underworld/Discord sessions | Yes |
| Registration, city, player profile | /snow, /snowbridge | Register + headquarters | Yes |
| Snowballs and regeneration | /snow, /snowbridge | Headquarters/resources | Yes |
| PvP target finding/attacks | /snow and /snowbridge | Target list and throwing | Same combat engine; real PvP still needs a two-player acceptance test |
| Snow Don / siege | Both Discord command families | Boss + city siege | Yes; tested live for Snow Don |
| Crafting/inventory/Snowflakes | /snow and /snowbridge | Market and inventory | Yes; tested live |
| Quest listing/claiming | /snow | Quests | Same economy engine |
| Cosmetic shop/equip | /snowfun | Market/wardrobe | Same cosmetics engine for available actions |
| Individual/city standings | Discord leaderboards | Scoreboards | Same score ledger |
| Cross-platform verification | /snowbridge verify | Cross-Platform Test Lab | Yes; live acceptance passed |
| Trophy cabinet and illustrated player cards | Rich Discord UI | Not equivalent | Discord-first UI |
| Christmas mysteries, secret encounters, social arcade | Rich Discord UI | Not yet complete | Discord-first UI; no claim of browser equivalence |
| Snowfall Wire full editorial/player submissions | Extensive Discord UI | Summary/bulletins | Presentation parity incomplete |
| Host/admin launch controls, audit and prize review | Staff-only Discord interface | No equivalent | Admin workflows remain Discord-only |

**Do not promise full feature parity.** Shared *core gameplay state* is
proven; platform coverage of arcade, mysteries, trophy display, and
staff operations remains a product/UX decision. Cosmetic-only activities
must remain explicitly prize-neutral unless later designed and tested.

## Regression and safety coverage

Required automated checks:

- v2.9.4a–v2.9.4e1 PostgreSQL migration, OAuth identity, cross-platform
  real engine, economy, inventory, Snow Don, idempotency and rollback tests.
- `tests/test_v295_ui_link_guard.py`: stale buttons, unlinked registration
  modal, guild and owner checks, Discord-only first-login denial, private
  errors on lookup outage, legacy SQLite compatibility and accurate QA text.
- `tests/test_v295_launch_audit_postgres.py`: verified isolated PG,
  linked account counts, no prize awards, all resource integrity checks,
  readiness HTTP 200/503, and no credential disclosure on outage.

A CI success does **not** mean human testers have exercised every
graphical menu or that 100 simultaneous users can be supported.

## Real-guild QA acceptance checklist

Before applying v2.9.5 to Railway, confirm all CI jobs passed and both
the existing Discord and web staging deployments are healthy.

1. Log into Underworld QA; confirm the same character/player ID appears
   with Discord connected on Snowfall Web.
2. In the original Discord guild, run /snowbridge progress and
   /snowbridge verify; confirm exact player and inventory/score match.
3. Open every historical /snow button family: Dashboard, Main Menu,
   player/Join, target selection, throw confirmation, Inventory,
   Craft/Use/Guard, Quests, World/Snow Don/Siege, community/winter menus.
   Linked users should navigate without duplicate public messages.
4. Simulate an unlinked or Discord-only first-login account. It can
   access account-link instructions but **cannot** register, craft,
   throw, attack or reuse a stale modal. No second game profile.
5. Run two linked test accounts in **different cities** for PvP.
   Check Ready windows, target eligibility, cooldowns, one interaction
   per action, two scoring hits per target/day, KO and shields, and
   the 300-point daily PvP cap on the same PostgreSQL game.
6. Craft and use all legal items using both /snow and web; compare
   resources and inventory, including insufficient Snowflakes and
   duplicate interaction IDs.
7. Attack Snow Don on Discord, then web, verify HP/score/ledger agree.
   Do not assume a render or GIF error rolled back a committed attack.
8. Claim daily quests and test present eligibility/cooldowns; check
   scoreboard, city standings and cosmetics without unexpected awards.
9. Repeat web actions across logout/login and bot restart. Confirm
   identical canonical player, persisted accounts, no duplicate
   actions, and retained original /data SQLite backup.
10. Test web /v1/ready against a controlled **disposable** database
    outage; it should return HTTP 503, while /v1/health can remain up.
    Never disconnect production credentials for this test.
11. Run the read-only QA audit. Investigate any "blocked" result;
    document warnings from known fictional QA NPCs.
12. Verify QA-only labels, no real prize transfers, and no automatic
    broadcast replacing official Discord messages.

### Release blockers requiring explicit operator decision

- **Production data migration is not implemented by this release.**
  The current bot is deliberately pointing at a fictional staging season.
- Prize policies, appeal windows, moderation, game-day start and payout
  controls require separate approval for a prize-bearing official season.
- The browser does not contain all Discord-only Christmas minigames.
- A real two-player PvP session, graphics/menu walkthrough, restart
  rehearsal and realistic concurrent-load test have not been reported
  as completed by automated cross-platform integration alone.
- A safe operational plan is required for any future PostgreSQL
  production database, including separate access credentials, backups,
  monitoring, incident rollback and data retention.

## Deployment sequencing and rollback

1. **Stage Snowfall-Web-QA** on
   `feature/v2.9.5-cross-platform-launch-readiness` and ensure its DB
   readiness checks are healthy after deployment.
2. **Stage existing Operation-Snowfall bot** on the same branch, keeping
   `SNOWFALL_SHARED_MODE=qa`, `SNOWFALL_DB_BACKEND=postgres`,
   `SNOWFALL_SEASON_KEY=web-qa-2026`, and existing stored
   `SNOWFALL_DATABASE_URL` / `DISCORD_TOKEN` unchanged. Only one
   worker per token; do not start a second Discord QA bot.
3. Apply one staged change set at a time with explicit deployment
   approval. Verify the web readiness endpoint and bot Discord-ready
   logs between steps.
4. On regression, restore the prior known-good source **and preserve
   both** PostgreSQL QA player records and the original persistent
   SQLite file and backup. Do not merge, clear or re-award scores.

The release is "QA launch-readiness hardening", not "official launch".
