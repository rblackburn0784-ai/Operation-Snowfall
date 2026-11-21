# Operation Snowfall v2.9.4d — Keep Underworld, Discard Discord Character

## Purpose

An event player might sign in through Discord first, register a separate
Snowfall character and accumulate points/inventory, then sign in through
Underworld and discover a separate canonical character. Discord OAuth cannot
silently merge those two game histories, and an automatic unlink would
expose existing players to account-takeover or prize-loss risks.

v2.9.4d adds an **optional, explicit, irreversible retirement** instead:

- **Keep:** the Underworld account and character, its canonical player ID,
  scores, snowflakes, inventory, cosmetics and existing progress.
- **Discard:** access to the separate, OAuth-verified Discord-only Snowfall
  character. None of the old Discord-only points, snowflakes, warmth,
  snowballs, owned equipment, cosmetics, titles or achievements transfer.
- **Link:** the verified Discord login is rebound to the Underworld character.
  Both logins then open the same canonical player.

**This is NOT a data merge or a full erasure of historical events.** The old
game character is permanently **retired**, marked disqualified, renamed to a
non-public tombstone and removed from active leaderboards; old web sessions
are revoked. Immutable score ledgers, combat records and historical
contributions are retained to preserve game integrity and auditability.
Damage done to the shared Snow Don or other players is not reversed.
This distinction is stated explicitly in the confirmation screen.

## Player experience

1. Sign in through Underworld. The website session must identify a real
   Underworld character.
2. Select **Link Discord Account** and authorise Discord normally.
   OAuth `identify`, PKCE and single-use 5-minute state still apply.
3. If Discord has a **separate, registered Discord-only Snowfall character**,
   Snowfall creates a ten-minute challenge bound to the Underworld session
   and OAuth-verified Discord user; it **does not change any player data**.
4. Snowfall displays a two-column preview: **YOU KEEP** (Underworld name and
   city) vs **YOU PERMANENTLY LOSE ACCESS TO** (Discord name and city,
   points, Snowflakes, snowballs, warmth, items, cosmetics and event activity).
5. The player must tick the explicit acknowledgement and type the exact
   phrase `DISCARD DISCORD CHARACTER`. The destructive button is disabled
   until both are complete. **Cancel** leaves both accounts unchanged.
6. Server rechecks both account ownerships, the unexpired session-bound
   challenge, complete Discord game-state fingerprint and confirmation in
   one locked PostgreSQL transaction. If the old Discord profile changed
   since the preview, the operation is refused and OAuth must be repeated.
7. Confirmation retires the old game character and links Discord to
   Underworld in a transaction. A durable audit records the discarded name,
   points and both canonical IDs. A fresh Discord login now returns the
   Underworld character.

### Security and non-eligibility

- Only `web-qa-2026` is enabled in this release; the existing production
  Discord worker and real Underworld account data are not changed.
- No raw Discord ID is accepted as input from a browser. Both identities
  are proven via their authenticated provider flows and matched server-side.
- OAuth challenge is a short-lived random, **HttpOnly**, `SameSite=Lax`
  secure cookie; only a hash is stored in PostgreSQL. Underworld session and
  anti-CSRF header are independently required for the final POST.
- One-use challenge, 10-minute expiry, atomic transaction and the same
  advisory lock used by game writes prevent double retirement and
  time-of-check/time-of-use conflicts.
- Cannot rebind an account linked to a *different Underworld character*,
  a target that already has a Discord identity, a discarded profile with
  prize awards, or an event after finalisation. Those require manual review.
- Active leaderboards omit the retired player using the existing
  `review_state='disqualified'` rules.
- Historical game records remain immutable; this release intentionally
  avoids potentially destructive deletes and game-history rewriting.
- If the player has a real prize or a cross-player account ownership dispute,
  staff should investigate separately. No real prize redirection is allowed.

## QA and future rollout

Automated tests in `tests/test_v294d_discard.py` use disposable PostgreSQL
and mocked OAuth. They cover Discord-first registration with real score,
Underworld registration and preservation, preview and owner verification,
CSRF and typed consent, mid-preview changes, single-use retirement,
immutable ledger retention, active ranking exclusion, browser session
revocation, and subsequent Discord login to the retained Underworld ID.

The optional screen is only shown for eligible Discord-only registered
profiles. Everyone else continues to receive the existing safe conflict
message or standard automatic linking.

**Do not apply this to production without a separate prize, privacy,
retention, record-keeping and scoreboard review.** In staging there are no
real rewards, and this is strictly a feature acceptance build.
