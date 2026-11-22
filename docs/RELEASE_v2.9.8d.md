# v2.9.8d — Event Controls & Disposable Test Lab

## Shared QA remains protected

The Discord bot and website already share one PostgreSQL staging season. Direct /snowadmin score changes, lifecycle resets and prize actions remain intentionally blocked for shared QA. This update **does not bypass them**.

## Web Test Lab

The verified Discord-staff-only Event Control Centre now includes disposable test sessions with six fictional players in all six cities. Administrators can:

- Start a temporary rehearsal on Day 1–7.
- Switch and reset to any other day, discarding that rehearsal's previous scores.
- Run real PvP, Snow Don and siege mechanics against the disposable test players.
- Refill the test players' snowballs/warmth and clear their cooldowns (without resetting already-earned test scores).
- End and erase the test session.
- Inspect practice HP, attempts, provisional scores, staff action history and expiry.
- Refresh the real shared QA dashboard, export a private JSON diagnostic report, and copy Discord staff commands.

These sessions run on separately generated local SQLite PracticeStore files, not on shared QA PostgreSQL. Each authorised Discord staff ID has a distinct lab. Six staff labs maximum, 90-minute idle expiry and automatic erasure on reset/end. A web restart also removes the temporary labs. This is intentionally **not persisted** or synchronised with the bot.

The Discord worker continues to provide its existing /snowadmin test-start, test-day, test-status and test-end commands in its separately configured permissible practice environment. The shared QA worker continues to reject mutating /snowadmin commands. The website does not remotely control the worker.

## Access and safety

- Verified Discord OAuth staff ID is mandatory; Underworld remains optional for staff and required for actual gameplay.
- Staff endpoints require fresh server-side authorisation on each request.
- Staff POST requires valid session CSRF and refuses a foreign Origin.
- All state-changing rehearsal actions require a staff reason. Start, day reset, refill and end also require typed confirmation phrases.
- Every action uses an ID-replay guard. Retired session IDs cannot mutate a replacement session.
- Real gameplay cooldown, score limits and eligibility rules apply to temporary test actions; no fabricated score engine.
- No shared player, resource, leaderboard, season, prize, chat or announcement mutations.
- No new PostgreSQL schema, Railway secrets or Discord worker deploy necessary.
- Private diagnostics download contains potentially sensitive QA names and review reasons; never publish it into chat.

## QA acceptance criteria

Automated Python tests must verify session lifecycle, day selection, test PvP/boss, refill, expiry, replay, per-staff isolation and zero writes to canonical sample QA game. API tests must verify unauthenticated/nonstaff rejection, CSRF/origin/account-mismatch rejection. Browser tests must verify desktop and both mobile widths, start/PvP/reset/end workflows and no horizontal overflow. Live WidgetBot two-way chat remains independent and unchanged.

## Future possibilities

A separately reviewed staff-to-bot command bridge might allow web control of bot practice, but would require a new authenticated work queue, independent host approval, safeguards and Discord worker upgrade. It is intentionally **not enabled** here. Actual score edits, disqualifications and payouts must remain outside this disposable lab until separately designed with approval/audit protections.
