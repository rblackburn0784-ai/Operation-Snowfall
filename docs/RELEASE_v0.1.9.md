# Operation Snowfall v0.1.9 — City Rivalries & Community

## What's new

- **City Headquarters:** available from Main Menu, Game Menus, My Player, and the personal Headquarters, plus top-level `/cityhq` (the `/snow` group is already at Discord's 25-command limit). Private city-scene card shows honorary rank, roster, active scorers, fortress HP, daily mission, local top five and a route to rivalries and the news.
- **Seven cooperative missions:** one per game day; scaled to the city roster at the start of that day (capped at five for accessibility). Tracked from the existing immutable PvP, PvE, quest and gift records. No quests or inventory changes; completion is for **bragging rights only**, with no additional score ledger, Snowflakes, multipliers or paid perks.
  1. Opening Salvo — combined PvP throws
  2. Fortress Breakers — siege damage
  3. Whiteout Ambush — successful PvP hits
  4. Holiday Supply Run — mystery presents opened
  5. Don's Downfall — real Snow Don damage (not echo damage)
  6. Blizzard Brigade — legal PvE attempts (including echoes)
  7. The Final Push — daily quest claims
- **City Rivalries:** a five-opponent read-only season summary, using recorded cross-city throws, hits, damage and knockouts. No friendly-fire exceptions, score changes or personal-identifying data.
- **The Snowfall Wire:** deterministic 1930s noir daily newspaper. Reports actual players, completed-day city snapshots, biggest recorded hit, boss contribution, sieges cleared, quests, presents and cooperative missions. Uses existing six-city winter art for illustrated 960×540 PNGs.
- **Expanded daily recaps:** the existing minute scheduler posts the earliest as-yet-unpublished *completed* day as a separate illustrated notice in the configured `#Announcements` channel. It sends **at most one issue per scheduler tick**, with a season/day message ID and recovery markers. Restart-safe; no new channels or permissions beyond existing Attach Files. The `#leaderboard` continues to be **one edited message every five minutes**.
- **In-app testing:** City Headquarters shows practice data inside the test channel. The practice Wire menu offers a private, TEST-labeled preview; it does not publish to the real announcements channel. Practice Stop & Delete/Archive remains unchanged.

## Access

- Players: `/cityhq` or `/snow menu` → City Headquarters; use the Co-op Mission, Rivalries and Snowfall Wire buttons.
- Hosts: normal `/snowadmin panel` → Test Centre. Start an isolated day; advance through days to test news preview and daily mission goals. Stop & Delete before live kickoff.
- News scheduling: normal `python bot.py` runs the existing one-minute world loop. No configuration changes.

## Upgrading

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

Back up `data/snowfall.sqlite3` first and stop the running process. **No database migration**: this release reads existing schema v7, stores only daily publication identifiers in the existing `published_messages` table, and does not modify results or prize rules.

## Important behaviour and limits

- All leaderboard ranks remain those calculated by `WorldEngine`; the cooperative mission is independent and cosmetic.
- Daily news only reports **closed days** based on the pause-adjusted event clock; it never publishes early or includes a live day as final.
- If the bot is offline through several day boundaries, it publishes **one missed issue per minute** after restarting, oldest first, to avoid a flood of seven simultaneous messages.
- Each announcement is idempotent by `wire_day_N` plus the existing Discord marker/SQLite record, and image upload failures fall back to full text.
- No MafiaReturns passwords, APIs or direct identity checks are used. Player names are self-declared; no mass mentions are created.
- Live Discord permissions still need validating with test accounts: View Channel, Send Messages, Read Message History, Embed Links and Attach Files.
