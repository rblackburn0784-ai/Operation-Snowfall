# ❄️ Operation Snowfall — v0.1.6b (Main Menu → Game Menus → Admin/Test Panel)

**New in v0.1.6b:** `/snow menu` or `/snow dashboard` opens a private **Main Menu**. Navigate to **Game Menus** (combat, gear, quests, Snow Don/siege and rankings), **My Player**, or—hosts only—**Admin / Test Control Panel**. The public dashboard retains its old shortcuts and adds a **Main Menu** button. Game screens offer **Game Menus** and **Home** navigation, editing the same private message.

Hosts: `/snowadmin panel` opens status, live launch checks, broadcast updates with confirmation and **Test Centre** buttons for Day 1–7 Start, Switch, Stop & Delete and Stop & Archive. The TEST Centre uses the existing bot and dedicated test channel; switching/ending never touches live scores or prizes. See [v0.1.6b Release Notes](docs/RELEASE_v0.1.6b.md).

**One Discord bot, one token, one event server.** Kat can rehearse any event day **inside the existing bot**, in a separate `#snowfall-testing` text channel, without changing live registrations, dates, scores, announcements or prizes.

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

Start a practice day as a host:

```text
/snowadmin test-start day:1 channel:#snowfall-testing confirmation:TEST
```

Switch freely between all seven days (test-only items and scores reset; test registrations retained):

```text
/snowadmin test-day day:5 confirmation:RESET_TEST_DAY
```

Stop and **delete** the test data without stopping the bot:

```text
/snowadmin test-end confirmation:END_TEST archive:false
```

Or use `archive:true` to keep a verified **test-only** local SQLite archive. `/snowadmin test-status` reports the active day and its bonuses. Practice is available **before** the real event has started. The original `/snow` controls work in the selected test channel; the official five-minute `#leaderboard` and daily `#Announcements` stay unaffected.

**Do not create a second Discord application or token.** The former `python bot.py --test`, `DISCORD_TEST_TOKEN` and `config.test.toml` setup is obsolete. Details: [Test Day Guide](docs/TEST_MODE_v0.1.6a.md) and [Release Notes](docs/RELEASE_v0.1.6a.md).

Kat (MK)'s **unofficial** MafiaReturns Christmas event runs for 168 effective hours. It includes registration, combat, crafting, quests, gifts, boss fights, city sieges, city standings, illustrated cards and individual prize exports. **City titles are honorary, not prize payouts.** Launch still requires Kat's checklist and recorded approval.

## Milestone E — illustrated Discord game screens

Six original 1930s winter city scenes now ship with the Python package, along
with icons for cocoa, forts, mittens, bombs, golden snowballs, the Snow Don and
sieges. Profile, PvP, Snow Don, fortress and provisional winners cards render
locally (960×540) in Pillow. Critical/KO and final-blow events can use small
480×270 GIF effects, falling back to static PNG and then full text when needed.

- `/snow profile` and dashboard **My Profile** display personal illustrated cards.
- `/snow throw` shows battle artwork after confirmation; **no artwork affects the RNG**.
- `/snow world`, `/snow boss`, `/snow siege` show the illustrated battlefield
  status and attack results.
- `/snow champions` and dashboard **Podium** show the top three individual
  competitors and the honorary leading city. Before finalisation, this is
  **provisional** and cannot issue prizes.
- Dashboard **Refresh** edits the existing message rather than posting again.
- Worlds' **Inventory** button navigates within the current private menu.

Grant the bot **Attach Files** and **Embed Links** in addition to its existing
channel permissions. Text-only fallbacks retain complete stats and action
results if images fail. The five-minute leaderboard and daily announcements
remain unchanged. See `docs/RELEASE_v0.1.5.md` and `docs/ASSET_LICENSE.md`.


## Upgrade to v0.1.6a in PyCharm (Python 3.13)

1. **Stop the bot** before updating. Back up `data/snowfall.sqlite3` safely after shutdown (or via SQLite's online backup API). Schema remains at **v6**; this update needs no database migration and preserves existing game data and published-message references.
2. Run:

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

3. Keep your local `.env` (only `DISCORD_TOKEN`) and `config.toml` (IDs and dates); neither file belongs in Git. Check `config.toml` has the **correct Discord server ID** and that this exact bot application is installed there with **`bot` + `applications.commands`**. A `403 Forbidden (50001 Missing Access)` during startup is a Discord guild-access/installation issue, not a failed game test.
4. **Add both channel IDs** to the `[discord]` section in your private `config.toml` (this file is not replaced by Git pulls):

   ```toml
   leaderboard_channel_id = 1571697566842748970
   announcement_channel_id = 1571828901024374824
   ```

   The channels must belong to the configured dedicated event server. Both IDs must be different. Setting an ID to 0 disables that channel's automation. Give the bot **View Channel, Send Messages, Embed Links and Read Message History** permissions in both channels.
5. **Use `/snowadmin test-start` inside the existing bot** to rehearse Day 1–7 in a separate test channel. Practice manages its own disposable season/database and does not touch the official season. Do not run `/snowadmin start` on the real season to rehearse.

## v0.1.4a: automatic leaderboard and announcements

**#leaderboard — `1571697566842748970`:** The bot automatically creates one combined Discord embed (top 10 individuals, six cities, boss HP, city siege summary), immediately refreshes it when online, and then **edits that same message every five minutes**, including across restarts. Message ID is stored in SQLite. A missing/deleted message is recreated; previously published `individual_board` content in the same channel is reused when possible and the obsolete `city_board` message is retired. An ordinary refresh never posts again.

**#Announcements — `1571828901024374824`:** The bot posts **registration opening**, **host kickoff readiness**, **seven different themed daily stage messages** with the day's real bonuses, and **season completion**. It also posts a single boss-defeat alert per event day. Each notice has a persisted key and is normally sent once; if the process crashes after posting and before saving the ID, a recent message scan can recover the sent notice. A manual `/snowadmin announce-day` edits the existing daily post rather than duplicating it. Announcements are checked once per minute; event days honour pause-adjusted time.

**Permissions and reliability:** Neither channel is an MR prize payout channel. Only individuals can earn prizes. There are no mass pings. The bot validates that both channels belong to the configured event guild. Do not run two copies of the bot against the same SQLite database.

## Discord commands added in v0.1.4

| Command | Behavior |
|---|---|
| `/snow world` | Private current boss HP, your city's fort HP, attempts, theme and points |
| `/snow boss` | Private Snow Don view, choose → confirm a boss attack |
| `/snow siege` | Private city fortress view, choose → confirm a siege attack |
| `/snow cities` | Normalized 6-city standings (honorary, not prize payouts) |
| `/snow leaderboard` | Individual ranking (only individuals can receive prizes) |
| `/snowadmin boss-settings enabled:<true/false> hp_override:<0 or 150–100000> reason:<...>` | Host-only; tune or disable boss **before** the season is started; audited |
| `/snowadmin publish-leaderboards` | Host manually creates/refreshes the **single** combined message in configured `#leaderboard`; background job edits it every 5 minutes |
| `/snowadmin announce-day` | Host manually creates/updates the current day's existing post in configured `#Announcements` |

The permanent main dashboard includes **Snow Don**, **City Siege** and **City Standings** buttons. Individual NPC interactions stay **ephemeral** and edit one message instead of spamming the channel. PvE, PvP, profiles and podiums now have illustrated cards with complete text-only fallbacks.

All existing `/snow join`, `ready`, `targets`, `throw`, `profile`, `inventory`, `craft`, `use`, `guard`, `quests`, `claim`, `present`, and host lifecycle commands remain available.

## PvE rules: Snow Don

- Day 1 boss HP = `max(150, 28 × eligible players registered at start)`; Days 2–7 use **previous game day's active scorers**, measured from the immutable ledger, capped below by 150. Host may override HP or disable the boss before kickoff.
- Each player has **6 attacks per game day**, using **one normal snowball** per attempt, **65% accuracy**, **12–18 damage on hit**, and **+5 individual points per hit**.
- Shared global boss HP decreases only while alive. When defeated, the final hitter earns **+10** and each earlier successful shared boss contributor earns **+10**, once only. Each player's combined daily boss score is capped at **50**.
- After defeat, later players still have their unused **personal training echo** attempts, at ordinary hit probabilities/damage and +5 points on success. Echoes **cannot change the shared boss HP, earn another boss-clear/final-blow award or repeatedly farm bonuses**. This is crucial for international players and is SNOW-032.

## PvE rules: six daily city sieges

- Each city has one independent NPC fort per game day. Initial fort HP = `24 × max(3, min(10, eligible city registrations at daily spawn))`.
- Every participant may attempt **4 siege throws/day**, each using one normal snowball: 65% accuracy, 14 damage on success, **+8 individual points** per hit, daily siege cap 50.
- The city whose fort was breached gets **+25 city standings points** for that day, exactly once. There is **no city credit/perk award**. After the fort is down, unused personal attempts target a *practice rubble pile*, which can give normal personal hit points but never additional city breach bonuses.
- PvP, boss and siege throws share the **30-second cooldown, player snowball inventory, KO protections and effective (pause-adjusted) UTC clock**. Guard prevents PvP throws; guarding players may still contribute to the shared NPC objectives. No attacks occur while PAUSED or after the seven-day endpoint.

## City scoring and daily themes

- Each city-day score uses the strongest **five** player contributions, each capped at **300 city-credit points** and padded with zeros if fewer than five. Formula: `(sum(top 5) / 5) + min(40, 4 × max(0, active_scoring_players − 5)) + (25 if daily fort breached else 0)`.
- A city needs **three eligible scoring participants** to qualify for an official day score; under three yields zero. Self-declared/cleared users count; flagged/disqualified users are excluded from city scoring until staff clear their case.
- Golden Snowball individual score is fully counted in individual rankings but contributes **at most 10** city points. Completed city-days are snapshotted once and immutably locked; scores for the ongoing day are marked provisional. After day seven all 42 city-day snapshots exist.
- City ties break by more winning city-days, then combined actual siege damage, then city name. Individual ties break by unique rival hits, shared Snow Don damage, earliest point-completion time and account name.

| Day | Theme | Mechanical bonus |
|---|---|---|
| 1 | Opening Barrage | Standard daily rules |
| 2 | Fortification Frenzy | Fort Kits cost 2 fewer Snowflakes (already in v0.1.3) |
| 3 | The Great Whiteout | First claimed quest of the day grants +10 themed points once |
| 4 | Christmas Supply Drop | Extra non-Golden gift after three claimed quests (existing) |
| 5 | Snow Don's Revenge | First legal Snow Don attack grants +10 themed points once |
| 6 | Blizzard Blitz | Second legal PvE attempt of the day grants +20 themed points once |
| 7 | The Last Snowfall | Final day, standard caps; no unfair blanket multiplier |

The third daily quest now accepts **a boss or siege attempt** as community participation; existing v0.1.3 item/guard *winter preparation* still counts as an accessible fallback for in-progress seasons. Regular quests are 20 points/+2 Snowflakes each, max 60 quest points/day; all themed rewards are separately capped to the listed once-per-day bonuses, below the 30 themed-points cap.

## Reliability and release limits

- All scored gameplay, shared boss HP, fort HP and ammo changes run in **one `BEGIN IMMEDIATE` SQLite transaction**. `pve_events` are immutable; interaction IDs are idempotent and the same ID cannot perform different NPC actions. Individual rewards are in `score_ledger` and can be reconciled from there.
- A single persisted daily spawn is created for boss + six forts per game day. The built-in UTC scheduler checks each minute, locks previous days once, publishes optional themed announcements once, and edits existing standings at most once per five minutes. Both restart and late startup reconcile missed day boundaries. Daily NPC state never resets on reconnect.
- Discord intents are minimal. Public posts should have no role pings; daily theme channels must be within the configured server.
- **Not yet externally approved for launch:** the actual Discord gateway UI needs live-server testing, an off-site restore drill and Kat's signed dry-run approval. The individual prize exports, backup tooling, in-app isolated test days and synthetic seven-day simulation are now implemented. The earlier **403 Missing Access** requires the bot installation/server permissions to be corrected separately.

See [`docs/RELEASE_v0.1.5.md`](docs/RELEASE_v0.1.5.md) and [`docs/RELEASE_v0.1.4.md`](docs/RELEASE_v0.1.4.md), [`docs/DEVELOPMENT_TICKETS.md`](docs/DEVELOPMENT_TICKETS.md), and the approved [`docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md`](docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md).

