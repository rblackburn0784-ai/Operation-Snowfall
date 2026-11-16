# Operation Snowfall v0.1.6a — Test Days in the Existing Bot

**No second Discord application, test token, test server or second Python process is required.** The existing Operation Snowfall bot can run one disposable practice day at a time in a specified text channel **inside the existing server**. All existing `/snow` gameplay commands work there, but use an isolated SQLite database with a unique practice season key. The official registration, score ledger, daily announcements, persistent #leaderboard and prize records are untouched.

## One-time setup

1. Pull v0.1.6a, install its dependencies, and restart your **one** bot using `python bot.py`.
2. Make a Discord text channel such as `#snowfall-testing` within the Operation Snowfall server. Give the bot View Channel, Send Messages, Read Message History, Embed Links and Attach Files there. It must **not** be the existing `#leaderboard` or `#Announcements` channel.
3. Use an account listed under `admin_user_ids` in your existing `config.toml`. **Keep the existing `DISCORD_TOKEN` and `guild_id` unchanged.** `config.test.toml`, `DISCORD_TEST_TOKEN`, and `python bot.py --test` are **obsolete**.
4. Official game must not have started. Practice is blocked while the official season is live, paused, closed or finalized.

## Start a specific day

From any channel where the bot accepts slash commands, run as a host:

```text
/snowadmin test-start day:1 channel:#snowfall-testing confirmation:TEST
```

Or select **Day 2, 3, 4, 5, 6 or 7** directly. This starts a private-to-the-channel *game season* at that effective event day, without advancing the actual Christmas date or requiring approval of the real live event.

Players join from **#snowfall-testing**, using normal commands:

```text
/snow join
/snow ready
/snow dashboard
/snow throw
/snow boss
/snow siege
/snow inventory
/snow craft
/snow quests
/snow claim
/snow present
/snow leaderboard
/snow cities
```

Commands and interactive ephemeral menus in this test channel are routed to the practice database. Commands in other channels still refer to the official season. The production `#leaderboard` and `#Announcements` jobs continue using only official data. The test channel **does not publish separate automatic production announcements**. You can view practice standings with `/snow leaderboard` or `/snow cities` in the test channel.

### What to check each day

| Day | Stage | Practice checks |
|---|---|---|
| 1 | Opening Barrage | Registration, throw styles, warmth, knockouts, Snow Don and sieges |
| 2 | Fortification Frenzy | Fort Kit crafting discount to 8 Snowflakes, armour, defensive bonuses |
| 3 | Great Whiteout | First claimed quest gives the configured +10 theme bonus |
| 4 | Christmas Supply Drop | Three quests unlock a non-Golden bonus present |
| 5 | Snow Don's Revenge | First boss attempt bonus (+10), shared defeat, training echoes |
| 6 | Blizzard Blitz | Second eligible PvE attack theme bonus (+20) |
| 7 | The Last Snowfall | Final-day objectives, standings, NPC limits and champion preview |

Use two Discord accounts registered to **different cities** to test PvP. A single registered user can still test Snow Don, siege, crafting, quests and most profile controls. Game rules are unchanged in practice: snowball regeneration, cooldowns and daily caps work as normal. A day is selected at its beginning, and you can end the rehearsal after a few minutes; you don't have to run it for 24 hours.

## Switch between Days 1–7

```text
/snowadmin test-status
/snowadmin test-day day:4 confirmation:RESET_TEST_DAY
```

The previous practice day's scores, rewards, inventory, combat logs, cooldowns and other temporary state are discarded. **Test-only participant registrations are carried forward** so players need not repeatedly enter names/cities. A new test database is created for the selected day, and old practice buttons are disabled. You may switch through all seven days in any order.

## End and clear a test

```text
/snowadmin test-end confirmation:END_TEST archive:false
```

This immediately revokes the practice database, deletes its SQLite file and sidecars, and returns the test channel to normal production context. Existing live registrations, game settings, scores, prizes, bot token and announcement IDs remain unchanged. The bot stays online; **you do not need to restart it**. Old practice menus cannot apply changes after the test ends.

To retain a local copy for review instead, run:

```text
/snowadmin test-end confirmation:END_TEST archive:true
```

This uses SQLite's online backup API to create an integrity-checked file in `data/practice_archives/`, then clears the active practice database. These files are not Git-tracked; they contain test account IDs and names, so treat them as private and delete them after review.

`/snowadmin test-stop confirmation:END_TEST` is a compatibility alias for **ending the practice session**. It no longer shuts the bot down.

## Restarts and safety

- A practice session exists only while the bot process is running. If the process stops unexpectedly, its previous practice DB is removed at the next bot startup; the real DB is never selected for practice.
- Official event start is still blocked until Kat's recorded approval. Practice start **does not authorize the live event**.
- You cannot test once production has started. It is intentional: users should not be able to confuse real prizes and practice points during the live season.
- The one-minute live scheduler and five-minute live leaderboard publisher always use the **production** store, never a routed practice store.
- Practice notices in the test channel are marked TEST. Clearing the practice DB does not automatically purge the channel's message history; remove any old rehearsal messages there manually if desired.
- `python bot.py --simulate` remains available as a seven-day **automated** simulation, without Discord or touching either database.
- `python bot.py --test` is no longer supported. **Never create/use a second Discord token for v0.1.6a.**

## Launch checks

After all seven test-day rehearsals, end the test session, verify `/snowadmin test-status` says no practice is active and compare the official `/snowadmin status` and `#leaderboard`. Then complete the normal backup, identity/privacy, staff and prize sign-off checks before Kat authorises the live event.
