# Operation Snowfall v0.2.0 — Expanded Christmas Gameplay

Release status: game systems / menus implemented and covered by automated tests.

## What's new

### 1. Seven rotating daily mission sets

Each event day has a different set of three named objectives, keyed to existing
`throws`, `rivals`, and `community` claim slots. Day 1 retains the approved
original objectives. Later days offer alternate paths via PvE or preparation so
unavailable opponents don't block participation. **Claim rewards are unchanged:**
20 individual points and up to 2 Snowflakes per mission; 3 claims/day maximum.
No extra quest slots, reward inflation, or recurring quest bonus.

### 2. Cosmetic shop and new specialist gear

Eight purchasable decorations: Icy Noir Frame (8 Snowflakes), Golden Gutter
Frame (15), Snowstorm Trail (6), Candy Cane Trail (10), Glacier Goggles (10),
Froststep Boots (10), Snow Don Scarf (12), Midnight Mob Banner (8).

Cosmetic purchases are persisted, transaction-safe, and one time per player per
season. Frames/trails/banners are **wardrobe display names** in the current UI;
no unprovided graphics are advertised. Goggles, boots, scarf affect **arcade
scores only**; they never improve real combat accuracy, warmth, boss damage,
loot, city points or real event prizes. Only existing Snowflakes can be spent.

### 3. Daily surprise encounters

Seven scripted encounters, one per player per active day. Players choose help,
investigate or prank, earning an outcome-specific collectible souvenir in their
private encounter history. No score, Snowflake, item inventory or prize rewards.
Retrying or racing the same day cannot produce multiple souvenirs.

### 4. Three mini-game modes

Target Practice, Blizzard Dodge and Boss Drill; maximum three attempts per
mode per event day. Players choose Steady (higher accuracy, lower arcade score)
or Risky (lower accuracy, double arcade score). One specialist piece of equipped
gear improves *its corresponding mini-game only*. Scores and personal bests are
stored per season for private amusement, not in `score_ledger` or city standings.

### 5. Menus and entry points

A new `/snowfun` command group provides `/snowfun menu`, `/snowfun shop`,
`/snowfun wardrobe`, `/snowfun encounter` and `/snowfun arcade`. A **Winter
Activities** button is present in Main Menu, Game Menus and Headquarters.
Submenus are private, owner-checked, and practice-session-pinned. The existing
25-command `/snow` group remains unchanged.

## Safety, migration and backups

- SQLite schema v8 creates five season-scoped tables: `cosmetic_unlocks`,
  `cosmetic_equipped`, `cosmetic_purchases`, `encounter_events`, `arcade_events`.
- Historic combat, quest, item, score and prize rows are not rewritten.
- All costs/actions use atomic SQLite writes and unique interaction IDs.
- No cross-season or test-session data sharing; test-day deletion/archive remains
  controlled by the current `/snowadmin` Test Centre.
- Back up `data/snowfall.sqlite3` before upgrading; the existing startup
  migration backup provides additional protection.
- The live two-channel broadcasts and five-minute single-post leaderboard stay
  unchanged.

### Upgrade in PyCharm

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

### Kat's verification plan

In a **disposable test day**, register players from two cities, visit
`/snowfun menu`, inspect the shop, unlock/equip an item, play all three arcade
modes in Steady/Risky, resolve a daily encounter with each choice across
separate players, then switch to another day. Ensure original boss, scores,
leaderboard, announcements, rewards and test Stop & Archive/Stop & Delete work.
Only then approve the live rollout.
