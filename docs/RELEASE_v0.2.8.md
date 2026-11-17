# Operation Snowfall v0.2.8 — Snowfall Wire 2.0

A seven-day interactive Christmas mob newspaper with verified live reports,
an illustrated broadsheet, personal roleplay letters, a host editorial desk,
and restart-safe community broadcasts. It extends the existing automatic
Snowfall Wire recap and does not change any competition rules.

## The newspaper

Open **/snowfun wire**, **Game Menus → Snowfall Wire**,
**Winter Activities → Snowfall Wire**, or **Today → Snowfall Wire**.

The newsroom shows the current verified headline and five reporting beats:
the leading eligible individual player, legitimate PvP throws and hits,
verified Snow Don damage, cleared city fortresses, and quest/arcade activity.
All figures are calculated from existing event ledgers; they are not
manually entered or invented. The **live** front page is labelled
provisional; completed-day reports use the existing authoritative community
recap and locked city standings.

A dropdown provides a **seven-day archive**. Future issues cannot be opened.
Each edition has an illustrated 960×540 newspaper cover, concise breaking
headlines, links to approved letters and a **Read Full Recap** view after
the day is complete. The read model respects host pauses, effective event
day and season data isolation. It remains browsable after the event ends.

## Player stories: Letters to the Editor

Registered players may submit **one original fiction letter per live event day**
using a private Discord modal: a title (6–80 characters) and story
(20–650 characters). Roleplay is sanitized to disable mentions, external
links and Discord markup; only the registered MR username and city are used
as byline. The story is stored as **pending** and is never publicly displayed
until a configured host approves it.

Open **Editorial Desk** as a configured host to inspect pending letters,
then explicitly **Approve Story** or **Reject Story**. Decisions are
one-time, season-scoped and transactionally immutable. The host's identity
and decision time are saved. Submissions from subsequently flagged or
disqualified identities are automatically hidden from published lists.
A rejected submission can never be retroactively approved through a second
click. Duplicate Discord submission interaction IDs return their saved
story rather than creating a second submission.

The **Player Stories** archive shows only approved submissions, clearly
labelled as *community fiction, not verified event results*. There is no
private-message contact, real-life data collection, external link sharing,
or prize reward for a submission or approval.

## Community broadcasts

The existing scheduler still handles one daily announcement, Snow Don phase
notices, the automated **one completed-day Wire recap**, and the live
leaderboard. In v0.2.8 the recap's body is a factual **Wire 2.0 edition**,
with five verified reporting beats and up to two approved, labelled
roleplay excerpts. The existing illustrated Wire report card remains.
The registered announcements channel and marker `wire_day_N` are reused.

A host can also choose **Admin → Broadcasts → Publish Latest Wire →
Confirm Live Publish**. This uses the **same one-post-per-day marker** as
automatic publication; it does not create a duplicate. It refuses to
broadcast the practice/test database. Already published editions are not
updated later just because additional stories were approved.

No publication sends @mentions; Discord allowed mentions are disabled.
Existing restart recovery checks the saved message ID and marker against
the authorised announcement channel before deciding to send.

## Scoring and migration guarantees

**SQLite schema v11** adds only `wire_submissions` and `wire_decisions`,
along with a season/day index and append-only triggers. An interaction ID,
per-player/day unique constraint and `BEGIN IMMEDIATE` prevent duplicate
stories and moderation races. The upgrade from v10 is automatic and
idempotent, preserving historic score, combat, world, economy, mystery,
arena and cosmetic databases.

The Wire makes **no changes to scores, prize allocations, inventory,
snowballs, Snowflakes, City Wars districts or social arcade rankings**.
The only award is fictional newspaper recognition.

## Deployment

Stop the bot and **back up its live SQLite database** first — v10 → v11 is
a forward-only migration. From your PyCharm PowerShell terminal:

```powershell
git checkout main
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

Test in an isolated Practice Manager channel: view a live edition,
submit a letter, check that another player cannot read it, approve it as
a configured host, review its byline, complete an event day, publish the
new issue, verify a repeat broadcast does not create another message, and
read the historic report. Verify no official points or prizes changed.
