# v2.9.9h — End-to-End Release Hardening

**Scope:** security and launch-readiness work for the five complete
Arcade 2.0 mini-games, the Arcade Hub, the existing Underworld-to-Discord
identity bridge and the original Classic Arcade.

**Release status:** code hardening and automated regression release.
**Not a production launch:** no Railway credentials, project settings or
live database are changed by this GitHub commit. Live QA deployment,
mobile hardware tests, manual sign-off and production authorisation
remain separate steps.

## Changes delivered

### Identity and reconnect protection

The website now records an in-memory account epoch every time the
authenticated character **or sign-in session** changes. A late
server response from the old epoch cannot update an Arcade 2.0 game,
overwrite its practice record, mount a stale canvas or close the new
character's game. The protection covers:

- All five full-game start, control, action and session callbacks.
- Arcade Hub launching and its existing account/sequence guard.
- Classic Arcade's original start/move controls and fallback game
  buttons.
- Refreshes of private character, wardrobe, combat targets,
  headquarters, world and verified cross-platform identity data.
- Old Gallery pending-shot keys when a fresh game session is issued.

This is a browser-side defence in addition to server-side
X-Snowfall-Player verification, CSRF tokens, authenticated Underworld
character requirements in QA and per-player database ownership.
No login secret is saved in localStorage.

### Protected read-only QA preflight

New module: snowfall.platform.arcade_readiness.

The preflight verifies the exact **/snowfall_web_qa** PostgreSQL logical
database and **web-qa-2026** season, verified staging marker, identity
and cross-platform verification schema. It inspects the five
independent mini-game session/action tables, their unique active-session
indexes and their integrity: foreign seasons, orphaned players, score or
status anomalies and duplicate active sessions.

An enabled mode with an absent schema or index **blocks** readiness.
A game that is disabled may have no tables; an enabled hub with no
enabled full games is a warning rather than a hard failure. An
unexpected second Discord bridge is blocked. The existing shared
QA launch audit is included, so prize anomalies, bad resources and
other launch blockers remain blockers.

**Staging web startup now fails closed when an explicitly enabled
arcade mode does not pass this check.** It never installs arcade tables
on startup. The previous protected manual migration remains mandatory.

The command does not print database passwords, source DSNs, player
IDs or private names, and opens only read-only audit transactions.
Running it does not reset games or touch rewards.

### End-to-end and deployable-wheel QA

New automated tests cover:

- Start all five independent sessions under one QA character, resume
  after saving, and verify another player cannot read or control them.
- Real Gallery target hits, Safecracker turns, Snowman placements,
  Snowflake Catch crossings and Trivia answers.
- Exact replay of idempotency keys without extra moves, points or items.
- Verify zero changes to Classic Arcade attempts, official
  score_ledger, prize_awards or player_resources.
- Browser account switching, logout, same-character re-login and
  stale-response rejection in all five modes.
- Default-off flags, hostile source database addresses, missing tables,
  missing indexes, duplicate sessions and invalid resource/audit
  states.
- Real disposable PostgreSQL proof that launch is refused before
  a protected schema is installed, accepted after installing it,
  and refused again when a QA prize anomaly is introduced.
- The **built Railway wheel** actually bundles the seven required
  arcade JavaScript modules, full website controller, stylesheet,
  home page and all five existing arcade artworks. A source-tree
  success with a broken wheel now fails CI.

No new gameplay, scoring formula, database migration or official
Discord policy change has been made in this release.

## Explicit QA deployment checklist

Do **not** paste credentials in GitHub tickets, chats or logs.

1. **Identify the right Railway project/environment.**
   The web app must run only in the existing Snowfall **staging**
   project and staging environment using its configured
   SNOWFALL_WEB_QA_CONFIRM marker. Keep the original bot and
   imported production `/railway` database untouched.
2. **Back up `/snowfall_web_qa`.** Confirm its current season is
   `web-qa-2026` and the Underworld and Discord identities are linked
   to the same character, not duplicated accounts.
3. **Install any outstanding v2.9.9–v2.9.9e tables manually** using
   the already protected installer against `/snowfall_web_qa` only:

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

   Never run this against `/railway` or as a web startup task.
4. **Turn on only the intended QA game flags**, after the preceding
   tables exist:
   `SNOWFALL_ARCADE_V299A_ENABLED=1` through
   `SNOWFALL_ARCADE_V299E_ENABLED=1`, and
   `SNOWFALL_ARCADE_V299F_ENABLED=1` for the Hub. The legacy drill
   uses its separate `V299_ENABLED` flag.
5. **Run the read-only release gate** from a staging shell whose
   SNOWFALL_DATABASE_URL addresses `/snowfall_web_qa`:

       python -m snowfall.platform.arcade_readiness --confirm READ_ONLY_ARCADE_QA

   Treat a non-zero exit code, `status=blocked` or any required
   table not ready as **NO-GO**. Review warnings before sign-off.
6. **Deploy the new web release only to Snowfall-Web-QA.**
   Do not install it over the independent Discord bot worker.
   Verify the page advertises v2.9.9h, its seven new/retained arcade
   scripts load without 404s and all five game cards appear.
7. **Test real Underworld sign-in**, then optionally link Discord.
   Confirm reopening the website retains the same character and
   practice record. Discord-only accounts must not be able to
   mutate shared QA gameplay before Underworld linking.
8. **Test real phone and desktop controls** for each mini-game:
   pointer/touch/keyboard actions, responsive HUD, sound opt-in,
   reduced motion, high contrast, pause and resume, expiry,
   finish confirmation, personal records and replay recovery.
9. **Test interrupted networks** at each action: refresh, recover
   an uncertain write with the same key, and verify no duplicate
   score, extra ammo, extra dial step, extra snowman part or
   duplicated catch/Trivia answer.
10. **Test account changes** with two QA characters, including a
    logout/sign-in while a previous request is slow. Verify no
    cross-character session, score, wardrobe or private data leaks.
11. **Inspect the Classic Arcade** and original Discord bot:
    daily attempts per game, passport stamps, City Cup, score
    ledger, shared resources, boss/siege and prizes unchanged
    by unranked website practice.
12. **Run a full QA day and repeat after the event day boundary.**
    A saved session from the previous day must not be resurrected
    as a new active game. Check the seven-day simulator and staff
    Test Lab against the same QA season.
13. **Review moderation and operations:** backups, health/ready
    endpoints, database capacity, expected concurrency, performance,
    logs without personal or secret values, incident ownership and
    accessible rollback procedure.

## Rollback / emergency controls

- Turn off `SNOWFALL_ARCADE_V299F_ENABLED` to hide the Hub,
  or turn off a specific `V299A`–`V299E` flag to block its web
  endpoints. Restore the previous known-good QA web revision if
  necessary; all the new schema changes were additive.
- Do not delete the QA arcade tables to roll back. Saved practice
  sessions can be kept intact while an individual game is disabled.
- A failing readiness audit, unknown project/season/identity marker,
  unexpected Discord bridge, copied production DSN, broken package
  assets or official reward mutations means **stop, investigate, do
  not launch**.
- This code release does not authorise a real event, real prizes
  or automatic production Railway changes.

## Automated release gates

- Python: `python -m pytest -q` plus the full existing Linux
  Python 3.12/3.13 and Windows Python 3.13 matrix.
- Node: `node --test tests/test_v299h_crossplatform_browser.mjs`
  plus every existing browser reconnect/replay regression.
- Real PostgreSQL: `tests/test_v295_launch_audit_postgres.py`
  exercises enabled arcade flags and the protected preflight using
  disposable local Postgres. The other migration tests remain.
- Wheel: `python tests/check_v299h_arcade_wheel.py output/wheels`,
  run against the actual built deployable wheel.
- Lint, compile, existing UI contracts and old Classic Arcade
  regressions remain in GitHub Actions.

## Sign-off

**Automated CI:** verify the final main-branch commit's four jobs.

**Manual QA:** outstanding until a human tests browser interaction on
real Android/iOS and desktop devices in the deployed staging site.

**Live launch:** not approved by this code-only release. Separate
deployment approval and prize/event policy review required.
