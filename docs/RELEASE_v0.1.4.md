# Operation Snowfall v0.1.4 — Milestone D (SNOW-017–021, SNOW-032)

## Implemented

- **SNOW-017:** Shared 24h-per-day Abominable Snow Don, HP scaling (Day1 registered, Days2–7 prior-day active scorers), deterministic 65%-hit/12–18-damage rolls, six personal attempts, shared victory bonuses, daily boss score cap 50; pre-season host-locked boss override/disable with audit.
- **SNOW-018:** Six separate daily NPC snow forts with independently snapshotted HP, four 65%-accuracy 14-damage attacks per person per day, 8 personal points on hit, one 25-city-point completion bonus per day and post-clear practice rubble for late players.
- **SNOW-019:** Deterministic normalized city standings: top-five contributions padded with zeros, per-player 300 city-credit cap, +4 participation up to 40, +25 daily siege clear; three legitimate scoring-player minimum, flagged/disqualified exclusion, golden city credit at most 10, tie-breaks, immutable per-city per-day snapshots with provisional in-progress results.
- **SNOW-020:** Persistent idempotent daily spawn and rollover across seven 24h effective windows, pause-aware 168h season, scheduler checks once/minute, auto-refreshes published boards every five minutes, optional once-daily themed announcements, Day3 quest bonus +10, Day5 boss participation +10, Day6 two-PvE-attack challenge +20. Existing Day2 item discount and Day4 extra non-Golden gift retained.
- **SNOW-021:** `/snow world`, `/snow boss`, `/snow siege`, `/snow cities`, text-first private menus/confirmations, extra persistent dashboard navigation, staff-managed public individual/city messages that update instead of spamming channels, and a private individual `/snow leaderboard` view.
- **SNOW-032:** The defeated shared boss exposes six personal attempts per day as **training echo** to any later player, at regular 65% chance and normal capped individual hit points; no extra boss-clear or finisher bonus and no shared HP changes.

## Database migration and operations

- SQLite schema **v5** adds `world_settings`, `world_days`, `world_sieges`, `pve_events` and `city_day_snapshots`. Existing user identities, session state, v0.1.2 combat log/ledger, v0.1.3 items/gifts/quests remain intact. New PvE and city snapshots are insert-only; staff correction flows are a later Milestone F feature.
- Stop the bot and back up the DB before pulling `main`. Run `python -m pip install -e ".[dev]"` and `python -m pytest -q`, then `python bot.py`.
- The event must be **LIVE** for PvE; do not start a real Christmas season for practice. Use another `season_key` and DB for Discord smoke tests. If `403 Missing Access` appears during command syncing, verify actual configured guild ID and bot installation scopes in the dedicated Discord server.
- Run `/snowadmin publish-leaderboards` in the desired channel once. Optional `announcement_channel_id` in `[discord]` enables automated daily announcements. The host can instead use `/snowadmin announce-day`; repeat calls edit that day's message.
- `/snowadmin boss-settings enabled:true hp_override:0 reason:...` uses automatic HP; set a valid override >=150 or `enabled:false` before kickoff. Once started, changes are rejected and audited successful pre-start changes are immutable records.

## Boundaries / known launch requirements

- No graphics assets have been fabricated; text fallback is fully usable while Milestone E delivers composited cards/GIFs.
- No final credit payouts, prize exports, staff score adjustments, distributed DB processes, or production load simulation are provided in v0.1.4 (Milestone F).
- During a season upgrade from v0.1.3, existing item-based *Winter preparation* actions still count toward the community quest; boss/fort attempts are now counted as the primary contribution and also count toward the 5-throw quest.
- Automated tests cover concurrency, history immutability, boss/fort clear, late-player echo, score normalization, protected activity, pause/restart, seven-day rollover, migration and themed bonuses. Actual Discord interaction and display tests must be completed on a real server.
