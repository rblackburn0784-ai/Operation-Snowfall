# Operation Snowfall v0.1.8 — Achievements & Boss Personality

v0.1.8 adds cosmetic personal milestones, a Trophy Cabinet, player records,
Snow Don phase dialogue, and illustrated victory flair. **No adjustments to
PvP hit probabilities, daily caps, snowflake values, score ledger, individual
prize definitions, city ranks or PvE mechanics.** Practice uses its disposable
season and database; it never unlocks trophies in the live season.

## Trophy Cabinet

- `/snow trophies` opens a private illustrated cabinet with two pages of badges,
  personal combat statistics, and a dropdown for equipped cosmetic titles.
- Main Menu, Game Menus, My Player and Headquarters include a Trophies shortcut.
  Navigation stays private, owner-checked and edits the existing message.
- Thirteen badges are automatically unlocked from recorded, append-only game
  actions: PvP hits, different rivals, criticals, knockouts, boss/siege damage,
  boss hits, completed quests, gifts, Golden Snowball, all seven event days
  and Hot Chocolate uses. Locked entries show measured progress.
- Only earned titles can be equipped. The default is **Snowball Recruit**.
  Equipped choice survives bot restart and is isolated per season; it never
  changes gameplay, prize eligibility, scores or inventory.
- Player's selected title is displayed in their Headquarters as well as Cabinet.
- Personal Records shows throws, accuracy, critical hits, knockouts, unique
  rivals, biggest hit, boss and siege attempts/damage, quests, gifts, and active days.

## Snow Don reactions and illustrated celebrations

- The Don reacts to shared boss HP reaching **75%, 50% and 25%**.
  Dialogue appears in the personal attack result on the threshold-crossing hit.
- The existing **#Announcements** channel sends one short, unique notice for
  each newly reached threshold. Saved message IDs and recovery markers prevent
  repeat announcements after bot restart. A disabled boss sends none.
- The Snow Don final-blow card now shows golden confetti and a distinct
  defeated banner, and the existing final-blow GIF remains available.
- Training echoes and city sieges never trigger shared boss phase reactions.

## Storage and compatibility

- Schema **v7** adds only `player_titles`, a season/user-scoped cosmetic
  selection table. Existing immutable event records and score ledger are not
  rewritten; the existing pre-migration backup mechanism remains enabled.
- New stats are derived from the historical event tables, not separate
  mutable reward counters. Badges can be re-evaluated safely on restart.
- The bot requires no new tokens, channels, or privileged Discord intents.
- The original ten Snow Don portraits remain bundled, if present in the repo.

## Local update

Stop the bot; back up `data/snowfall.sqlite3`; then:

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

Inside Discord: `/snow menu` → Trophy Cabinet, or `/snow trophies`.
In `#snowfall-testing` use the host Test Centre to start a disposable day,
play, view stats and then Stop & Delete or Stop & Archive.

Automation checks correctness but **does not replace a real Discord-server
smoke test**, mobile screenshot review, Kat's launch sign-off or the external
backup and restore drill.
