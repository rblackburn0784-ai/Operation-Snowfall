# ❄️ Operation Snowfall — v0.1.4 Group Gameplay (Milestones A–D)

Kat (MK)'s **unofficial** MafiaReturns Christmas event for **one dedicated Discord server**. This release implements Milestones A (registration/admin), B (transactional combat), C (inventory/quests/gifts), and **D (daily Snow Don boss, six independent city sieges, normalized city standings and themed challenges)**. No MR credentials or API integration; **individual prizes only**, city competition is honorary.

## Update from v0.1.3 in PyCharm (Python 3.13)

1. **Stop the bot** before updating. Back up `data/snowfall.sqlite3` safely after shutdown (or via SQLite's online backup API). The migration to **schema v5** preserves v0.1.2/v0.1.3 combat, quests, gifts and registration data.
2. Run:

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

3. Keep your local `.env` (only `DISCORD_TOKEN`) and `config.toml` (IDs and dates); neither file belongs in Git. Check `config.toml` has the **correct Discord server ID** and that this exact bot application is installed there with **`bot` + `applications.commands`**. A `403 Forbidden (50001 Missing Access)` during startup is a Discord guild-access/installation issue, not a failed game test.
4. Optional in `config.toml` under `[discord]`: `announcement_channel_id = 0`. Replace 0 with a channel ID **in the dedicated event guild** to publish one themed announcement per day. If left 0, Kat can announce through `/snowadmin announce-day` manually.
5. **Test with a disposable `season_key` and separate database** before starting the real 168-hour Christmas season. The actual start and completion clock is host-operated; do not use `/snowadmin start` on the real season to test.

## Discord commands added in v0.1.4

| Command | Behavior |
|---|---|
| `/snow world` | Private current boss HP, your city's fort HP, attempts, theme and points |
| `/snow boss` | Private Snow Don view, choose → confirm a boss attack |
| `/snow siege` | Private city fortress view, choose → confirm a siege attack |
| `/snow cities` | Normalized 6-city standings (honorary, not prize payouts) |
| `/snow leaderboard` | Individual ranking (only individuals can receive prizes) |
| `/snowadmin boss-settings enabled:<true/false> hp_override:<0 or 150–100000> reason:<...>` | Host-only; tune or disable boss **before** the season is started; audited |
| `/snowadmin publish-leaderboards channel:<#channel>` | Host creates/updates two public messages; scheduler edits every 5 minutes |
| `/snowadmin announce-day channel:<#channel>` | Host creates/edits the current daily theme announcement |

The permanent main dashboard includes **Snow Don**, **City Siege** and **City Standings** buttons. Individual NPC interactions stay **ephemeral** and edit one message instead of spamming the channel. PvE and scoreboards have text-only fallbacks; graphic assets arrive in Milestone E.

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
- **This is not full v1.0 launch-ready:** the actual Discord gateway UI still needs live-server testing; artwork, graphics, final individual prize exports, anti-abuse load simulation, backed-up restore drills, and Kat's dry run are Milestones E and F. An earlier reported **403 Missing Access** requires the bot installation/server permissions to be corrected separately.

See [`docs/RELEASE_v0.1.4.md`](docs/RELEASE_v0.1.4.md), [`docs/DEVELOPMENT_TICKETS.md`](docs/DEVELOPMENT_TICKETS.md), and the approved [`docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md`](docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md).
