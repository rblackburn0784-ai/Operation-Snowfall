# Operation Snowfall v2.9.8c — Staff Event Control Centre

Adds an isolated, authenticated, read-only staff dashboard to Snowfall Web QA.

## Features

- Current seven-day event phase, registration and kickoff dates, scheduled completion and accumulated pause duration
- Current Snow Don boss HP and each city siege HP (without ticking or modifying the world)
- Player registry with verified score totals and review states, capped at 60 characters per display
- Security and score integrity indicators: flagged accounts, resource limit violations, event-to-ledger mismatches, PvP/quest caps and arcade attempt caps
- Recent existing admin audit entries and daily score breakdown by category
- Individual provisional top-three preview using the exact CombatEngine leaderboard tie-break order, excluding flagged and disqualified accounts
- Manual refresh and periodic refresh while staff page is open; no state mutations

## Staff permissions: configuration required

Set SNOWFALL_WEB_STAFF_DISCORD_IDS on the Snowfall-Web-QA Railway service to a comma-separated list of explicit Discord user IDs. There is no fallback to usernames, roles, or client hints. The default is empty; staff access is denied to everyone until configured. The existing Discord worker staff IDs cannot be read through the connected Railway integration, so no users were silently granted permissions.

A user requires a verified Discord OAuth session whose linked Discord user ID matches the allowlist. Underworld is not required for staff viewing, but remains necessary for gameplay. The backend rechecks both for every protected request and only serves the web-qa-2026 season. The navigation tab is hidden from nonstaff but the backend is the security boundary. Guests get HTTP 401, nonstaff 403, changed-account sessions 409; only GET routes exist, and no allowlisted IDs are public.

## Data boundaries

The QA population includes NPC, fictional and unlinked accounts. Award previews are NOT verified real-prize rosters; no credits or payouts are allocated. Lifecycle changes, player reviews, score edits, prize approvals and exports remain in the original audited Discord staff commands, and are NOT available as web mutations. No schema migration or Discord worker restart.

The existing ops.reconcile PostgreSQL HAVING clauses are corrected to use SUM(points), avoiding a nonportable SELECT alias; the scoring rules and ledger remain unchanged.

## Acceptance

- Staff authentication matrix: Underworld-only, verified Discord-only staff, nonstaff Discord ID, unset allowlist and dual-link staff
- GET only and no writes, no staff details in public API, zero prize awards on QA
- Desktop and 390px/320px mobile, unauthorized navigation blocked
- Canonical scoring reconciliation and PostgreSQL tests, persistent WidgetBot chat intact
- Real staff sign-in and manual operational checks required before final staff sign-off

## v2.9.8c1 — Discord-only staff login

Staff access now requires only an OAuth-verified Discord user ID in SNOWFALL_WEB_STAFF_DISCORD_IDS, with no Underworld link. Use the standard Continue with Discord button from Sign in; verified staff automatically open Event Control on OAuth return. The header Event Control shortcut and a Headquarters staff card make the section easy to find. Existing Underworld-only gameplay gate is unchanged. Staff access refreshes periodically so allowlist changes are recognised without signing out, while server checks still run on every privileged request.
