# Operation Snowfall v2.9.4c — Discord-First Login Reconciliation

## Problem

Using **Continue with Discord** before **Continue through Underworld**
creates an empty, Discord-only Snowfall identity. The v2.9.4a link operation
correctly rejects binding that identity to the Underworld character, even
though both sign-ins are controlled by the same person. No gameplay has
necessarily taken place.

## Safe solution

- Keep the **Underworld character and its existing canonical player ID**.
- Only on an authenticated Underworld Snowfall web session, initiate
  **Link Discord account**. The normal OAuth state, session CSRF validation,
  PKCE and Discord `/users/@me` verification still apply.
- If the Discord identity was previously created by Discord-first login,
  it may be reassigned **only when**:
  - It has the canonical Discord-snowflake ID, not another Underworld ID.
  - Its **only** identity is that single Discord link.
  - It has **no registered game character, game activity, inventory, rewards,
    combat events or other known gameplay records** in the imported v11 schema.
  - The target is an actual Underworld character with **no other linked
    Discord account**.
  - The identity database's transaction lock and the PostgreSQL game
    write lock are both held while checking and reassigning.
- Old Discord-first website sessions are revoked when that empty identity
  disappears. The obsolete principal is removed; a durable transfer audit
  is recorded. Underworld data and player history are never copied or
  merged, nor does linking award resources.
- If a Discord identity has progress, belongs to another Underworld
  character or conflicts with another link, **reconciliation is refused**.
  The user must contact the event operator for a manual review.
- Repeated OAuth linking is idempotent; no second identity or audit row.
- The existing `/snow` bot and planned v2.9.4b integration are retained,
  with no second bot token or Discord app.

## Verification

`tests/test_v294c_relink.py` uses disposable real PostgreSQL and mocked
Discord OAuth2. It tests the exact Discord-first → Underworld → link flow;
rejected transfers of registered accounts; stale session revocation; no
duplicate link; and subsequent Discord login resolving to the Underworld
character with its progress intact.

## Staging activation

This feature is built on `feature/v2.9.4b-existing-discord-bot` and
must first run in isolated Snowfall-Web-QA. It does not require new OAuth
credentials or changes to the real Underworld game or existing live Discord bot.

Once the staging web deployment reports SUCCESS, the user can:

1. Sign out of Snowfall, then log into **Underworld QA**.
2. Enter Snowfall from Underworld (this chooses the correct character).
3. Under **Connected identities**, choose **Link Discord account**.
4. Authorize the same Discord account used previously.
5. Confirm that **Discord connected** and **Underworld connected** both appear
   and the canonical character remains unchanged.
6. Optionally sign out and **Continue with Discord**; it must now return to
   that same Underworld character, with identical progress.

The code only reconciles verified *empty* Discord-first identities. It will
not reset, forcibly unlink or move a Discord identity with actual gameplay.
