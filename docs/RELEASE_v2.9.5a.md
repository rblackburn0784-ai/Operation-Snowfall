# v2.9.5a — Cross-Platform Release Consolidation & QA Deployment

**Target: the existing two Railway QA services; preserve the current isolated PostgreSQL game and the original Discord bot. No prizes.**

## Proven starting state

- Discord: one existing Operation-Snowfall bot (no new token or guild), running v2.9.4e1 with the pre-cutover SQLite database and checked immutable snapshot retained on the mounted /data volume.
- Web: Snowfall-Web-QA, Underworld handoff and Discord OAuth links operating on dedicated PostgreSQL `snowfall_web_qa` season `web-qa-2026`.
- Cross-platform verification previously proved SnowDude's shared ID, score, inventory and Snow Don HP on both clients.

## What v2.9.5a consolidates

From `feature/v2.9.5-cross-platform-launch-readiness`:

- Verified Underworld + Discord identity checks on slash, legacy buttons, registration picker and modals, with account revocation/outage handling.
- Web gameplay rejects Discord-only OAuth principals before they can earn or spend resources.
- Read-only staff `/snowadmin launch-check` and PostgreSQL launch-audit report of link, resource, event, orphan and real-prize anomalies.
- Safe handling of Discord interaction exceptions and QA labelling in existing player menus.
- Identity conflict and launch-audit regression suites, and a database-backed `/v1/ready` endpoint.

From `feature/v2.9.5-cross-platform-consolidation`:

- Browser action retry preserves the identical per-player idempotency key after network loss, timeout or 5xx, avoiding accidental extra purchases/attacks on manual retry.
- SQL-boundary rejection of unlinked raw Discord snowflake IDs that could otherwise create a second game profile if old commands outlive a link.
- Six-way concurrent craft replay, two-player isolation, restart/replay and lost-response integration tests.
- Additional link checks for Snowfall Wire modal submissions.
- Transient 429/5xx Discord slash-command synchronisation retries, clear QA status in navigation.
- Hard lockdown of all mutable legacy admin/host operations in shared QA. Read-only `status`, `test-status` and `launch-check` remain.

## Deployment gates

1. All CI jobs green on the **exact v2.9.5a merge commit**: Linux 3.12/3.13, Windows 3.13 and real disposable PG16 suite (plus Node browser retry tests).
2. Check Railway staged changes affect **only** GitHub source branch/commit; never credentials, volumes, networking or season flags.
3. Commit Snowfall-Web-QA staging patch first; verify successful deployment, static page, `/v1/health` version 2.9.5a and `/v1/ready` 200. Do not expose private player data.
4. Only when web is healthy, commit existing Discord bot's staged source patch. Inspect runtime for verified pre-cutover SQLite backup, successful PG preflight, one Discord connection, slash group sync and no error loops.
5. Keep `SNOWFALL_SHARED_MODE=qa`, `SNOWFALL_DB_BACKEND=postgres`, `SNOWFALL_SEASON_KEY=web-qa-2026` and private `SNOWFALL_DATABASE_URL` unchanged.
6. Conduct human Discord ↔ Web smoke test using real linked QA identities: `/snowbridge verify`, craft, PvP, boss, website reverse read, verification receipts, logout/in and cooldowns.
7. Run `/snowadmin launch-check` privately. QA must show zero actual prize-award rows. Blockers must be reviewed before any real event.

## Backout

- Web source: pinned verified `feature/v2.9.4e-cross-platform-verification` commit `60c8f7684de40cd325482eb70bda2bb3f9f06f7f`.
- Bot source: pinned verified `feature/v2.9.4e1-existing-bot-qa-cutover` commit `6c18ff2e79349a142af2e688e98a3500992ddfba`.
- Do not alter QA database, OAuth links or previously stored SnowDude progress. The SQLite original snapshot remains available should the bot need a full production-mode restoration.
- Rollback requires a **new source-only Railway staged patch** and applied deployment. Avoid mixing both deployments in one transaction when only one side fails.

## Remaining launch boundary

CI success and QA startup are **not** proof of live PvP/boss interaction in the Discord guild. A real-prize event launch needs additional human approval of dates, limits, production-account migration, disaster recovery and privacy/organiser controls. Some Discord-only arcade, mysteries and illustrated extras are not duplicated on the website yet.
