# v2.9.8f — Admin Control Centre 2.0

**Scope:** isolated `web-qa-2026` only. Shared API/game engine remains v2.9.7. No PostgreSQL schema migration, Discord worker upgrade or additional artwork.

## Organiser and host permissions

The existing `SNOWFALL_WEB_STAFF_DISCORD_IDS` allowlist grants **organiser** permissions: authenticated Discord-staff access, the shared QA operations overview, private diagnostics, player search, dossiers and disposable Test Lab 2.0. Underworld is **not required for staff-only views**. Ordinary gameplay still requires the verified Underworld character.

The new optional **`SNOWFALL_WEB_HOST_DISCORD_IDS`** variable is a comma-separated subset of the same verified staff Discord IDs. Only those IDs have **host** permission to flag or clear an account's QA review state. No default hosts: until this variable is configured, review mutations fail closed (403).

The backend verifies a live server-managed OAuth session and its linked Discord subject **on every request**. Client-provided IDs, page markup, custom roles or browser storage cannot grant permission. An unallowlisted account receives no staff access. Malformed host IDs or hosts not in the staff list cause startup to refuse the configuration.

## Player search and inspection

The new Review Desk supports case-insensitive literal character search or exact player ID, city, review status and 25-record pagination (maximum page 100). The server enforces season scoping, parameterised SQL, input limits and no-store responses.

A dossier shows current resources, verified Underworld/Discord link presence **without account subject values**, recorded points, recent PvP and boss/siege history, staff review history and per-character integrity signals:
- existing account review flags;
- abnormal resource values;
- PvP/defence ledger exceeding 300 points in a day;
- PvP engine event points missing or mismatched from the immutable score ledger.

Potential flags are **investigation leads, not evidence of misconduct**. Staff can export a private JSON dossier. Keep exported player data confidential.

## Audited and safe account review

Only a host can flag or clear a registered character, with a 12+ character specific reason, an exact **FLAG QA PLAYER** or **CLEAR QA PLAYER** confirmation, and an additional browser confirmation. The server applies a fresh expected-review-state check and rejects stale tabs, self-reviews, disqualified targets and finalized seasons. All successful changes use a transaction, update only `players.review_state` and append to `admin_audit` with before/after state and a persistent request-ID replay marker. Retries never double-audit or reverse a newer action.

**Important:** A QA flag affects the player's eligibility in the shared QA leaderboard/prize preview and is visible to the existing Discord bot; this is the **only authorised canonical-game mutation** added here. It does not alter score ledger, inventory, Snow Don HP, event dates or prize records. Host actions should be tested against dummy QA characters before any real launch.

Website controls still **cannot** directly edit official scores, transfer or merge identities, disqualify accounts, reset/finalise events, change prizes, post Discord messages or operate Discord bot test sessions. Those operations remain behind existing separate reviewed processes. The web Test Lab remains a completely separate disposable SQLite environment.

## Operational instructions

1. Deploy the web code to **Snowfall-Web-QA** after review/CI. Do not change the Discord worker deployment.
2. Sign in using an existing allowlisted Discord staff account. Verify the Staff Role line displays **Organiser**; search and inspect characters.
3. If host review is required, configure `SNOWFALL_WEB_HOST_DISCORD_IDS` **in the QA website service only**, using approved IDs already included in `SNOWFALL_WEB_STAFF_DISCORD_IDS`; redeploy the web service. Do not store these IDs in Git.
4. Verify the role changes to **Host**, use a fictional QA character, and test flag, idempotent retry and clear. Confirm corresponding audit entries and unchanged score/prize rows.
5. Validate desktop, 390px and 320px mobile layouts and persistent The Streets drawer. Run `python -m pytest -q` and the repository's browser suite before any rollout beyond staging.

## Release acceptance gates

- Search treats `%`, `_` and backslashes as literal input; filters and pagination cannot reveal other seasons.
- Anonymous and unallowlisted users are rejected; organisers cannot review players; misconfigured hosts fail closed.
- State-changing requests require CSRF, same-origin and a typed phrase; each action has a durable audit-replay identifier.
- A stale review or reused request ID cannot overwrite a later decision; finalisation locks review writes.
- Existing Test Lab 2.0, linked gameplay, public rankings, prizes and Discord commands retain their current rules.

**Status:** source and regression checks are present in this branch; live staging and cross-platform operator acceptance must still be performed before release signoff.
