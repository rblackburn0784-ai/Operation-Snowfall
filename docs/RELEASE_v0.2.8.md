# Operation Snowfall v0.2.8 — Snowfall Wire 2.0

A rebuilt 1930s-style in-game newspaper for the seven-day MafiaReturns
Christmas event, featuring real game-event reports, illustrated front pages,
opt-in player-written dispatches, a private host editorial desk and
non-duplicating public community broadcasts.

## Every event day gets its own newspaper edition

- Seven unique daily front-page headlines (the same day schedule as the
  existing event).
- **Live Street Editions** during the day; **Morning Editions** once the
  event day ends. Historical Day 1–7 pages remain accessible for the
  remainder of the event and afterwards.
- Reports are drawn exclusively from existing authoritative records:
  most points earned by an eligible player that day, city activity,
  real PvP throws/hits/largest hit, eligible boss damage, fortress clears,
  quest claims, presents, solved detective cases and finished Winter Arcade
  games. Headline flavour is fictional noir; the displayed quantities
  always come from logged events.
- A city with most ledger activity is explicitly labelled "busiest
  streets," **not** the official city leaderboard winner. These articles
  cannot change official city or individual scores.
- Illustrated **960×540 original newspaper front page**, plus an illustrated
  "Extra! Extra!" flash bulletin; text fallback if Pillow/Discord media
  attachment fails.

### Reader experience

- `/snowfun wire` opens a private reader with illustrated front page,
  **Latest Wire**, **Previous Day**, **Next Day**, and a dropdown for all
  opened Day 1–7 editions.
- **Game Menus → Snowfall Wire**, **Winter Activities → Snowfall Wire** and
  **City Headquarters → Snowfall Wire** open the same interface.
- Host-approved player dispatches appear in the daily edition with
  registered MafiaReturns byline, city and an explicit fiction/opinion
  label. No invented player statements or fake attributed quotes.

### Player stories and consent

Players submit an original, optional story using the **Submit Dispatch**
modal. Each story requires a headline (8–76 characters) and an
in-world written dispatch (40–500 characters). The form identifies it
as fiction submitted for public publication.

- At most **one submission per player per event day**; identical repeat
  requests return the existing record. No overwriting a reviewed story.
- Submissions are only accepted on a **live** event day for registered,
  non-flagged identities. Time-freezing pauses and future-day protection
  follow the canonical event clock.
- A draft is **pending** until a configured event host reviews it.
  Pending/rejected writing is never rendered into public editions.
- The host can **Approve** or **Reject** exactly once; later changes require
  a new submission on a subsequent day. Reviewed entries and original
  text are protected by database triggers; no deletion/edit-in-place.
- Up to **two oldest approved, currently eligible stories per day** are
  selected for the public edition to prevent spam/overflow; longer
  articles are excerpted for Discord's 2,000-character message limit.
- Player names and submitted text are neutralised for Discord mentions
  and formatting before display. Links and mass pings are blocked.
- A user can privately review their own submission and status with
  **My Story**. Not all submissions will be published.

### Host editorial desk

The existing `/snowadmin` slash group is full; v0.2.8 adds a
separate **`/snowwireadmin` host-only group**, with:

- `/snowwireadmin desk` — full private, selection-based editorial queue
- `/snowwireadmin queue` — list recent pending submissions
- `/snowwireadmin review story_id:<id> decision:Approve/Reject` — one-time verdict
- `/snowwireadmin preview day:<1–7>` — private illustrated preview
- `/snowwireadmin publish day:<1–7> confirmation:PUBLISH` — explicitly
  post the issue to the configured announcement channel; optional
  `refresh_existing:true` updates text on the already published message
- `/snowwireadmin flash` — private status of a newsflash milestone

The main host **Admin / Test Control Panel → Wire Editorial** opens
the same private editorial queue with approve/reject buttons.
Previewing or moderating never sends an announcement.

**Public posting is disabled in the disposable Test Centre**, and only
the configured live announcements channel is ever used. The bot requires
the exact host-only publish confirmation, preventing accidental messages
from a preview or click.

### Daily broadcasts and newsflashes

The existing one-minute background loop continues publishing **one
completed-day Wire issue at a time**, with the established
`wire_day_<day>` saved-message markers. The new issue is formatted as a
real noir newspaper with a front page instead of the original plain recap.

An optional **one-per-day factual "Street Flash"** also triggers
automatically if the event records at least **10 real PvP throws** or
**12 completed Winter Arcade runs** on the same day. No fabricated milestones,
no private submission text, no reward allocations.

Existing marker/message recovery, configured server checks, no-pings
delivery and the one-message-per-kind publication model remain intact.
Restarting the bot never republishes a saved issue. Previously posted
editions are not changed when a new player story is approved: the host
must explicitly use `refresh_existing:true` for that day.

### Persistence, security and competition fairness

**SQLite schema v11**, one new `wire_submissions` table containing
season, player, day, headline, original story, status, reviewer ID and
timestamps. Unique (season, user, day), reviewed-once and immutable
content triggers. `BEGIN IMMEDIATE` prevents duplicate submissions
and races; moderation remains host-only in both the service and Discord.

The new Wire engine **does not write** combat events, score ledgers,
player resources, currency, items, arcade results, mysteries, territory
control, score adjustments or prize awards. All city and community
storylines are presentation-only. Event test databases remain isolated.

## Upgrade

**Stop the bot and back up SQLite before upgrading.** Schema v10 → v11
is automatic and forward-only; the bot's normal boot routine also makes
a pre-migration backup of the prior database.

```powershell
git checkout main
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

## Host's Test Centre checklist

1. Start a disposable practice day. Open `/snowfun wire` and preview the
   illustrated front page; verify future-day editions are hidden.
2. As a registered player, submit a test story. Its status must remain
   **Pending**, absent from public reader pages.
3. Open **Admin / Test → Wire Editorial**, select the pending story and
   approve it; test a rejection separately. Reader views must show
   approved items only and other players' submissions must stay private
   until approved.
4. Test identity-review removal, same-day duplicate drafts, and event pause
   and day rollover. Restart the bot and ensure reviewed status persists.
5. After ending the practice session, test the live publication path only
   in the correctly configured, authorised announcements channel. For a
   preview use `/snowwireadmin preview`; real posting requires
   `confirmation:PUBLISH`. Verify that reruns do not duplicate posts,
   and that explicit refresh edits the original post.
6. Check that all combat, scores, item counts, Snowflakes, city standings
   and individual award exports are unchanged by editorial actions.
