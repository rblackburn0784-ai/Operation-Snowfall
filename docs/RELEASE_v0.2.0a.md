# Operation Snowfall v0.2.0a — Global Stability & Fair-Play Audit

Patch release on top of v0.2.0. No prize allocations, equipment benefits,
quest rewards, boss stats, combat odds or database tables have been changed.

## Corrections

1. **Quest score reconciliation** now checks the actual singular `quest` ledger
   category. A player may legitimately claim at most three 20-point quests
   per event day (60 quest points), not 70. Reconciliation also verifies
   the matching `quest_claims` history and flags missing or unsupported
   quest ledger entries. Previously the `quests` plural filter was never
   true and could silently approve corrupt or inflated quest scores.
2. **Defense score reconciliation** detects score mismatches between the
   immutable combat event and its target's `defense` ledger credit.
3. **Fair city cooperative goals** now exclude flagged and disqualified
   player contributions in the PvE branches, matching the existing
   eligibility rules for PvP throws, quest claims and gifts.
4. **CSV formula injection protection:** staff registration exports and
   prize CSVs prefix leading spreadsheet formula characters from
   self-declared player names or organiser-supplied reward descriptions
   with an apostrophe, so opening an export does not evaluate them.
5. **Scheduler resilience:** unexpected database, disk or graphics exceptions are
   logged and retried on the next scheduled tick rather than permanently
   terminating the live broadcast, leaderboard or backup task.
6. **Release identification:** menu, dashboard and app version strings
   reflect v0.2.0a. The Python package uses `0.2.0.post1` (the
   PEP 440-compliant post-release equivalent, instead of an alpha
   version numerically older than v0.2.0).

## Added regression coverage

- Genuine `quest` category overcap plus ledger-to-claim mismatches
- Missing defense credits
- Review-flagged players' city PvE milestone contributions
- Spreadsheet-safe exports
- Full single-day combat → PvE → daily quests → gift →
  encounter/arcade → cosmetic purchase/equip → achievements/community
  → reconciliation (zero arcade/cosmetic impact on official scores)

The repository's existing CI checks package installation, compilation,
fatal Ruff lint, and all tests across Python 3.12 and 3.13 and Windows.

## Launch review / limitations

These tests use a controlled local SQLite engine and simulated Discord
UI contracts. They cannot assert actual Discord availability, role
configuration, channel send permissions, real message-edit behaviour,
host identity claims, or live user behaviour in the event server.
Self-declared MafiaReturns identities remain subject to manual review.
The bot still does not initiate external MafiaReturns prize transfers.

**Before deployment:** back up the live database, install updated
dependencies (`python -m pip install -e ".[dev]"`), run
`python -m pytest -q`, then start a disposable test day and check
v0.2.0 features in real Discord before approving the live event.
