# v2.9.9k8a — QA Event Lifecycle Controls

Built on the v2.9.9k8 gameplay-polish branch.

In Event Control, explicitly authorised hosts can restart the shared QA event
(including an expired or finalized event without prize records), select days
1–7, extend it by 1–7 days, or reset only gameplay. Restart and reset erase
QA gameplay including scores, arcade attempts, world progress, inventory and
cosmetics; default starter resources are reseeded for registered characters.
Registrations, identity links, OAuth sessions, staff allowlists, prize records
and audit history are not deleted. Day selection preserves prior gameplay and
reopens at the selected day's beginning; it is not a fresh scoring run.
Extension preserves elapsed time and holds scoring at day seven after day seven
begins. A finalized season must be restarted before other lifecycle actions.

Uses the existing verified Discord staff identity, host subset, CSRF and origin
checks. Configure an existing staff Discord ID in
SNOWFALL_WEB_HOST_DISCORD_IDS if it is not already a host; no Underworld login
is needed for staff operations. No production database is eligible.

The QA-only optional extension column is installed transactionally on first use.
Deploy web and Discord from the same revision for consistent event-clock semantics.
PostgreSQL resets require the dedicated QA database, matching staging marker,
one season and zero QA prize awards. All operations are transactional and
audit-recorded with replay-safe request IDs. No CASCADE is used.

Run CI before deploying. After deployment use Event Control > Shared QA event
lifecycle; enter the displayed typed confirmation and reason. Test restart after
expiry, day selection, extension, resource reset and account/staff login.
