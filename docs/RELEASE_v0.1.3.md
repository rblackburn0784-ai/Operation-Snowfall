# Operation Snowfall v0.1.3 — Milestone C (SNOW-014–016)

## Features

- **SNOW-014:** One starter cocoa per registered player, private inventory, crafting with Snowflake costs/caps, Hot Chocolate, Fort Kit armour/6-hour expiry, Precision Mittens +10pp on next legal throw, Blizzard Bomb power-shot boost, 30-minute guard/2-hour reuse delay; item use caps and 300-point PvP cap protection.
- **SNOW-015:** Three daily 20-point/+2-Snowflake missions, computed from historical events, claimed once per player per day, immutable quest claims and scoring ledger. Temporary *Winter preparation* replaces boss/siege participation until milestone D; five throws and two distinct scored rival hits remain intact.
- **SNOW-016:** One gift/day unlocked after a claimed quest, 40/25/20/10/4/1 percent odds, 1%-rarity Golden Snowball once per player per season, cap substitution +5 Snowflakes, Day 4 extra non-Golden gift after all three claims.
- Golden thrown from existing private combat menus: 80% accuracy / 25 damage / 25 base individual points, no ordinary ammo spent; future city-credit recorded at max 10 points.
- Slash commands plus persistent dashboard Inventory and Quests buttons, private item confirmation menus, quest claim buttons and text-only gift/result fallbacks.

## Schema / upgrade

SQLite schema **v4**, additive to v3: `player_economy`, `player_inventory`, `item_events`, `quest_claims`, `mystery_gifts`; tracked modifiers on `combat_events`. Existing accounts, registrations, scores and v0.1.2 combat events are preserved. Starter cocoa is seeded lazily exactly once; **not** on every restart. Protected unique claims, gift rolls, event records and ledger entries prevent replay exploitation. All event clocks use effective paused UTC.

1. Stop bot; safely back up its SQLite database (or use online backup API while active).
2. In PyCharm run `git pull origin main`, `python -m pip install -e ".[dev]"`, `python -m pytest -q`.
3. Run `python bot.py` only after ensuring its configured guild ID matches the dedicated event server and the app is installed there with `bot` and `applications.commands`.
4. On a **separate test season/database**, join players from different cities and test `/snow inventory`, `/snow guard`, `/snow craft`, `/snow quests`, `/snow claim`, `/snow present`, and `/snow throw` (especially buff/fort/Golden interactions).
5. After a restart verify that items, claims, gift outcomes, scores, shield/guard expiry and dashboard buttons persisted. Do not prematurely start the real Christmas competition.

## Verification / boundaries

- Local unit suite: **86 passed, 1 Discord contract skipped** in the minimal container without discord.py. GitHub Actions runs with discord.py installed on Python 3.12 and 3.13.
- Real Discord server smoke test still required, including the previously reported **403 Missing Access** guild-command synchronization issue (configuration/installation, not the domain logic).
- PvE/boss/siege, normalized city scoring, graphics, item artwork, prize payout/export, and seven-day load simulation remain milestones D–F. There is no MR API/credential integration and no city prizes.
