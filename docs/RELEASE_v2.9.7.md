# v2.9.7 — Full Release Consolidation & Launch Readiness

## Scope
Build on v2.9.6i, preserving all art, the original game rules, season points,
prize policy, database schema and isolated web QA deployment. This is a launch
candidate, not production approval. No game reset, no account relink, no awards.

## Fixes
- One release identifier for API health and web config; cache-busted client.
- Actual missing-season readiness failure, bounded handoff body and demo
  login limiter, CSP/HSTS/permissions policy.
- Expected canonical player guard for authenticated requests protects old tabs
  when cookies change. Sign-in fetches authoritative current account links.
- Pending actions recovered in the same browser tab after refresh. Store only
  opaque IDs and operation keys scoped to season and player (no credentials).
  Preserve keys on ambiguous responses, auth/proxy failures; explicit rejection
  or successful decoded response resolves the request. No automatic replay.
- Keep previous art calibration; browser checks must measure the visible
  goggles lenses, not the transparent outer square.

## Release gates
1. All CI matrix jobs (Linux 3.12/3.13, Windows 3.13, PostgreSQL) pass.
2. HTTP smoke: ready, matching version, original artwork, security headers.
3. Real browser QA with intercepted fictional player writes only: login,
   account mismatch, attack retry after reload, siege, all six sections,
   market/portrait geometry and endgame. No mutation of real QA scores.
4. Existing isolated DB audit, no prize awards or invariant blockers.
5. Human cross-platform test on the currently deployed Discord worker and
   Underworld, including logout/login and rollover. No claim that the worker
   has been upgraded or production proven before this manual sign-off.
6. Production readiness requires explicit host approval, backed-up data,
   reviewed environment/identity migration and prize configuration. Never
   promote the QA database or its fictitious participants.

Rollback QA web source to 86fcfeb2b1bf054b88601defbaa18717990c4797.
