# Operation Snowfall v0.1.4a — Dual Channel Broadcast Update

**Base:** Milestone D v0.1.4, schema v5 (unchanged). **Package version:** `0.1.4.post1` (PEP 440 version ordering; release nickname v0.1.4a).

## Fixed channel mapping

| Channel | Discord ID | Function |
|---|---|---|
| `#leaderboard` | `1571697566842748970` | One combined individual-and-city leaderboard message, edited automatically every 5 minutes |
| `#Announcements` | `1571828901024374824` | Daily stages, pre-event notices, boss-defeat notices and event conclusion |

Local `config.toml` must have both values under `[discord]`; it is intentionally ignored by Git and is not overwritten by `git pull`.

```toml
[discord]
leaderboard_channel_id = 1571697566842748970
announcement_channel_id = 1571828901024374824
```

## What changed

1. A **single combined leaderboard embed** shows individual Top 10, the six-city honorary standings, current stage, boss HP and siege clears. Only the individual board implies prize eligibility. The bot automatically creates the message once, saves its channel/message ID in the existing `published_messages` table, and uses `Message.edit` every 5 minutes. Editing includes a current timestamp. Restart reconnects to the saved message; a history search can recover a sent but unrecorded message.
2. Migrates an existing legacy `individual_board` in that channel into the combined board and deletes its redundant `city_board` message in the same channel where possible, avoiding two maintained public ranking posts.
3. `#Announcements` gets one dedicated message when registration opens (7 days before the configured start), one when it is time for a host to start, and a unique themed **Day 1–7** notice with correct daily bonuses. A late-arriving bot posts only the **current** day rather than spamming old missed days. One **Snow Don defeated** notice can appear per day, and the bot announces season completion once. Each key is stored across restarts, with recovery scanning to mitigate send/DB-save crashes.
4. The background jobs run once per minute for stage changes and once every five minutes for the board. Both validate channels as belonging to the configured guild. No new permission intent or database migration is needed.
5. `/snowadmin publish-leaderboards` now takes **no channel parameter**, refreshing the configured #leaderboard message. `/snowadmin announce-day` also takes **no channel parameter** and updates the configured #Announcements post for the current day. Existing dashboard interaction commands are unchanged.

## Upgrade from v0.1.4

1. Stop the bot and back up `data/snowfall.sqlite3` (or take a SQLite online backup).
2. `git pull origin main`, `python -m pip install -e ".[dev]"`, `python -m pytest -q`.
3. Add both channel IDs to `[discord]` in local `config.toml` exactly as shown above.
4. Check that the bot has **View Channel, Send Messages, Embed Links and Read Message History** in both channels, plus its existing `bot` + `applications.commands` guild installation.
5. `python bot.py`. Once online, #leaderboard is created automatically and refreshed every five minutes. The announcements channel stays quiet until registration opens, unless the season is already active.
6. For a safe smoke test, use a **test season key and database**. On a running test season, `/snowadmin announce-day` edits the existing daily notice, and `/snowadmin publish-leaderboards` edits the existing leaderboard.

**No additional message is posted for leaderboard refreshes.** A new board message is created only when the stored original has been deleted or the target channel has been changed. Daily announcements are intentionally separate new posts for distinct event days.

**Note:** The previously reported `403 Forbidden (50001 Missing Access)` on Discord slash-command sync must be resolved through the correct server installation / guild ID / scopes. This release does not alter those permissions. The game still requires live-server smoke testing and Milestones E and F before official deployment.
