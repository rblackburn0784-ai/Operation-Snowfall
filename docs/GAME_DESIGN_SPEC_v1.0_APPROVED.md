# OPERATION SNOWFALL
## Kat (MK)'s MafiaReturns Christmas Discord Snowball Bot
**Version:** 1.0 design specification  
**Status:** Organiser decisions APPROVED; mechanics still require closed-beta balance testing  
**Event:** Seven consecutive 24-hour days (168 hours)  
**Modes:** Individual championship + six-city championship  
**Host:** Kat (MK)  
**Platform:** Dedicated event Discord server (single-guild installation); no privileged MafiaReturns integration assumed  
**Registration:** Self-declared MR username and city; opens 7 days (168 hours) before launch  
**Prizes:** Individual awards only; city championship is for rankings and bragging rights

---

## 1. Vision and non-negotiable requirements
Operation Snowfall is a Christmas-themed, text-channel Discord game with interactive menus, generated fight cards, daily goals, snow forts, items, PvE bosses, and team-versus-team competition. Participants self-declare a MafiaReturns (MR) username and city, and earn independent personal and city scores. The separate, dedicated event Discord server is the only supported server for v1.0. City scores confer rankings and bragging rights only; all material MR prizes are individual awards. It is inspired by MR snowball events, not a direct implementation of MR's live event.

The six cities are Chicago, New York, Detroit, Philadelphia, Las Vegas, and Los Angeles. Each account may register once per season. The bot does not request MR credentials, scrape protected MR pages, or transfer prizes automatically. The host adjudicates disputed MR usernames and awards real MR prizes separately.

**Principles:**
1. Equal opportunity: seven identical 24-hour game days anchored to the configured start timestamp, not the server's calendar midnight.
2. Bounded advantage: activity helps, but personal PvP scores, PvE attempts, and city contributions have daily caps.
3. No griefing: targets cannot be camped; no attacks on protected, inactive, or same-city players.
4. Low Discord noise: one public pinned dashboard plus scheduled highlights; personal actions are ephemeral.
5. Restart-safe: every score, resource mutation, event tick, and prize grant is recorded transactionally.
6. Accessible: commands work without graphics and every image result includes a text description.

## 2. Lifecycle and registration

- **DRAFT:** Kat configures individual prize catalogue, admin roles, city definitions, channels, and event timestamps in the dedicated event Discord server.
- **REGISTRATION:** Opens **automatically 168 hours (7 days) before** configured event start. `/snow join` collects the self-declared MR username and selected city, with an explicit declaration. No routine staff approval is required to play. Registration stays open throughout LIVE; late entrants get no retroactive score or quest allowances.
- **READY:** Kat previews screens and runs test actions in a sandbox environment.
- **LIVE:** Exactly 168 hours from configured `starts_at_utc`; seven 24-hour days. No actions can cross the end boundary.
- **PAUSED:** Time-based regenerations and daily event clocks freeze logically; administrator can resume with elapsed game time shifted by pause duration, avoiding lost player opportunities.
- **FINALISING:** Freeze player actions, reconcile transactions, resolve flagged accounts, calculate final scores, and produce CSV and JSON exports.
- **CLOSED:** Publish winners and audit summary; retain historical event records.

Use UTC timestamps in storage and Discord timestamp formatting in the interface. `day_number = floor((effective_now - starts_at_utc) / 86400) + 1` (1 to 7). During a pause, `effective_now` subtracts accumulated paused duration. All seven days are full-length, even if the event starts at 19:30 UK time.

### Registration and identity checks

- Discord user ID is the authoritative account key; self-declared MR username is display metadata and must be unique within the season (case-folded comparison). Keep review states `self_declared`, `flagged`, `cleared`, `disqualified`; initial state is `self_declared`, never `pending_approval`.
- **Self-declaration is authoritative for entry, not proof of MR account ownership.** No approval queue or mandatory verification to participate. One Discord account may claim one MR username and vice versa per season (case-insensitive). Staff review only flags, conflicting claims, impersonation reports, and prize-eligibility disputes. No MR passwords, cookies or account linking.
- City is locked when the first scored action is taken. Host-approved transfers apply at the next game-day boundary and are logged. Earned city points stay with the originally credited city.
- Leave/rejoin preserves the same player record; no reset or bonus reissue.
- A participant must have scored at least one eligible action in the last 36 hours to appear as an attack target. New players count as eligible from their first scored action.

## 3. Core game resources and action economy

| Resource | Starting amount | Cap | Regeneration / source | Purpose |
|---|---:|---:|---|---|
| Snowballs | 8 | 12 held | +1 every 20 minutes while not at cap; daily quests and gifts can add up to cap | All throws, boss and siege attacks |
| Warmth | 100 | 100 | +5 per 20 minutes outside knockout; hot cocoa | Health; zero triggers a knockout |
| Fort armour | 0 | 25 | Activated from a Fort Kit; lasts 6 hours or until depleted | Absorbs incoming hit damage first |
| Snowflakes | 0 | 100 | +1 for every scored successful PvP hit; daily quests can give +2 each | Non-transferable item crafting currency |
| Inventory | 1 cocoa | Per-item limits | Gifts, quests, crafting | Tactical, no real-money purchases |

Resource regenerations are calculated lazily using stored timestamps. While at cap, unused regeneration does not accumulate invisibly. No resources are generated before the event starts or after it ends. A snowball is reserved and consumed atomically when a legal attack is resolved; invalid targets/cooldowns do not consume it.

**Attack cooldown:** One throw per 30 seconds, regardless of target or mode.  
**Target restrictions:** Rival city only; 2 successful scoring hits per attacker-target pair per game day. After 3 scored incoming hits in a rolling 30 minutes, the target receives 15 minutes of automatic protection. Targets below 1 warmth are knocked out and cannot be attacked or throw for 30 minutes; after this they return with at least 50 warmth. The knockout shield lasts through the 30-minute recovery.  
**Offline protection:** Inactive accounts are ineligible to target after 36 hours without a scored game action; accounts are never force-joined.

## 4. PvP combat

Attacker chooses a rival and an attack stance. Chance calculation is independent of player level, and the result is rolled by the server, not the Discord client.

| Stance | Base hit chance | Warmth damage | Personal points on hit | Expected base points per throw |
|---|---:|---:|---:|---:|
| Quick Lob | 75% | 8 | 8 | 6.0 |
| Standard Throw | 60% | 14 | 12 | 7.2 |
| Power Shot | 40% | 22 | 18 | 7.2 |

- A successful throw has a **10% critical-hit chance**, adding 4 warmth damage and 3 personal points. Critical hits are rolled only after the hit succeeds.
- Precision Mittens add **+10 percentage points** to the next throw's hit chance, then expire; guarding reduces incoming hit chance by **10 percentage points**. Final hit chance is clamped to 20%-90%.
- Fort armour absorbs warmth damage first. Points for landing the hit are not reduced by armour; however, attacks against an already-protected target are prohibited.
- **KO bonus:** +10 points for the knock-out throw, at most 3 scored KO bonuses per game day; a KO immediately activates recovery protection.
- **First rival-city hit:** +5 points the first time each day the player hits a target from a given rival city, max five bonuses/day. Encourages variety.
- **Defensive contribution:** +2 points when the player's fort absorbs a successful incoming attack, max 10 defense points/day.
- Missed snowballs score zero, with a short humorous message and no target loss.
- Hits from forbidden collusive attack pairs may be voided by the host, with audit history.

**PvP score cap:** Maximum 300 earned personal PvP points per player per game day, including critical, city diversity, KO, and defense bonuses. Additional legal practice throws can continue but do not award PvP points, Snowflakes, city contributions, or target-hit quota credit. UI should warn when cap is reached and preferably disable scoreless combat by default.

### Battle transaction algorithm

1. Authorise Discord account; lock attacker record, target record and event-day score counters in a transaction.
2. Confirm event LIVE, both participants eligible, rival-city relationship, range/cooldown/protection, ammo and limits.
3. If legal, consume one snowball and update the attacker's cooldown.
4. Roll hit, critical and effects using a server-side secure random number source; record rolls and calculation details in an immutable ledger.
5. Update armour, warmth, knockout protection and score (with cap); create one combat-event record.
6. Commit transaction; acknowledge interaction privately and enqueue non-critical rendered image/public summary.
7. Use Discord interaction ID as an idempotency key so repeated button presses/retries cannot produce duplicate throws.

## 5. Gear, items and crafting

| Item | Effect | Suggested access / restriction |
|---|---|---|
| Hot Chocolate | Restore 30 warmth | 1 starter item; craft for 8 Snowflakes; max 2 uses/day; not usable while KO'd |
| Fort Kit | Grant 25 armour for up to 6 hours | Craft for 10 Snowflakes; one active at a time; max 2 uses/day |
| Precision Mittens | +10 percentage points to one PvP throw | Craft for 6 Snowflakes; max 2 uses/day |
| Blizzard Bomb | Single boosted Power Shot, +7 damage and +5 hit points | Event drop or craft for 15 Snowflakes; max 1 use/day |
| Golden Snowball | One-use 80% hit, 25 damage, 25 personal points | Ultra-rare daily present; max 1 received per player per season; max +10 city-credit points for golden throw |

Golden points remain subject to the daily 300-point PvP cap. The Golden Snowball is deliberately a spectacle, not a city-leaderboard determinant. Items are non-tradeable, cannot be gifted to alter accounts, and are removed on season reset.

### Daily mystery present

One free present can be claimed per player per game day after completing at least one daily objective; it cannot be purchased. Roll distribution:

| Reward | Probability |
|---|---:|
| +3 snowballs (respect cap) | 40% |
| Hot Chocolate | 25% |
| Precision Mittens | 20% |
| Fort Kit | 10% |
| Blizzard Bomb | 4% |
| Golden Snowball | 1% |

If a reward is already at its cap or disallowed by the seasonal Golden Snowball limit, substitute +5 Snowflakes rather than losing the reward. No gift offers a permanent gameplay advantage.

### Guard mode

`/snow guard` toggles guarding for up to 30 minutes: incoming attack accuracy −10 percentage points and incoming warmth damage −2 (minimum 1), but the guarded player cannot initiate PvP throws. Guard ends on timeout or on manually leaving guard. Guard can be activated once every 2 hours. It is not active while knocked out.

## 6. Daily objectives, score and participation

Every game day presents three quests. They are auto-tracked and claimed once; each is worth **20 personal points + 2 Snowflakes**, giving at most 60 quest points/day. A proposed daily template:

1. **Get your gloves on:** throw 5 legal snowballs (any mix of PvP, boss, and siege).
2. **Spread the misery:** land 2 successful PvP hits on different targets.
3. **Community effort:** contribute at least one legal throw to the daily boss or city siege.

Quest progress cannot be reset by rejoining, username edits or reconnecting. If a quest cannot be completed because no rivals are active, the host can use a documented fallback quest that targets NPCs (same rewards, no exploit risk). Quests vary in flavour across seven days but retain comparable difficulty.

**Score breakdown and upper bounds:**

| Category | Daily personal cap | Included in city credit? |
|---|---:|---|
| PvP hits, bonuses and defense | 300 | Yes |
| Quests | 60 | Yes |
| Daily boss | 50 | Yes |
| Daily siege | 50 | Yes |
| One-off themed event | 30 | Yes |
| **Theoretical daily total** | **490** | **Capped at 300 per player/day** |

No points for simply logging in, stockpiling, sending messages, or idling. Only eligible, server-recorded gameplay actions count. An MR identity does not need routine verification to earn points.

## 7. Normalized city championship

Every player's MR city is locked for the day. For a given day, calculate each player's **city contribution = min(300, that player's eligible personal points earned that day for that city)**. Order members by contribution descending; take the top five and fill any missing slots with zeros.

`city_daily_score = (sum(top_five_city_contributions) / 5) + min(40, 4 * max(0, active_city_players - 5)) + siege_clear_bonus`

- **Active city player:** registered, not flagged as duplicate and has at least one eligible scoring action that day.
- **Participation bonus:** +4 for each active member beyond five, up to +40/day; encourages breadth but does not let a large city win solely by raw numbers.
- **Siege-clear bonus:** +25/day if the city's daily NPC fortress is breached.
- **Eligibility:** city requires at least 3 active legitimate participants to qualify for the official city leaderboard on a game day; lower numbers display provisionally until the day is finalized. If the city never reaches 3, city-day score is 0, while individual points are unaffected.
- **Event city total:** sum of the seven finalized daily city scores. Display two decimal places for clarity; retain unrounded values for sorting. **No city prizes are awarded**; the winning city receives a banner, title, and public recognition only.
- **Player ties:** individual total, then most unique rival players hit, then highest boss damage, then earliest time the score was reached. City ties: more winning daily standings, then highest total siege progress, then alphabetical city name (objective tie-break).

**Example:** Chicago's top five scores are 300, 280, 260, 220, 200; 12 members are active and the fort is cleared. Daily city points = `(1260 / 5) + 28 + 25 = 305`. New York's top five are 300, 290, 280, 240, 230; 6 active and siege not cleared: `(1340 / 5) + 4 + 0 = 272`. Chicago wins that day despite New York's higher five-player average because of participation and the siege objective. A 20-player city's participation boost can never exceed 40 points.

Use the full day rather than a live rolling window for final rankings. During the day show provisional totals; locked daily snapshots preserve historic standings even if player registration metadata changes later.

## 8. PvE: The Abominable Snow Don

A daily shared NPC boss appears at the start of each game day and remains available for 24 hours, or until defeated. It has a generated illustrated boss card, health bar, and contributors leaderboard.

- Initial HP = `max(150, 28 × prior-day active participant count)`; on Day 1 use registered eligible participant count measured at event start.
- Each player can make **6 scored boss attacks/day** using ordinary snowballs. Each boss attack has a 65% hit chance; on hit it deals 12-18 damage selected server-side.
- Earn +5 personal points for each successful boss attack, +10 for having contributed if the boss is defeated, and +10 for the final hit. Daily boss points are hard-capped at 50 per player; cap all rewards and never double-award them.
- If the boss HP is exhausted early, it remains defeated for the rest of the day and new players cannot attack it; to avoid excluding time zones, the **first six boss attempts per person are fulfilled against a personal training echo after the public boss is defeated**, yielding ordinary hit points but no final-blow or shared-boss clear reward. Echo attempts do not change the public boss's HP.
- Host can disable the boss or tune its HP before launch. Any change during a live day requires an explicit audit entry and public notice.

## 9. PvE: The Great City Siege

Each city attacks a separate NPC-controlled snow fortress across the day's full 24 hours. This gives every player in every timezone an opportunity, without requiring a simultaneous live event.

- Each city's fortress has initial HP = `24 × max(3, min(10, eligible registered city participants at start of day))`. Snapshot once at day start.
- Each player can use up to **4 scored siege throws/day**, consuming one snowball each; 65% accuracy, 14 damage on hit.
- Each landed siege shot earns +8 personal points; breaking the fortress earns a one-time +25 **city** points (not an individual jackpot). Up to 4 successful hits = 32 points, below the 50-point siege cap.
- If the fort is destroyed before a participant has used their daily allocation, their remaining attempts can target a practice rubble pile for ordinary individual siege points, but cannot change the city-clear reward.
- A city can complete at most one fortress per day. Different city sizes have separately scaled targets; city points remain normalized.

## 10. Random encounters and themed week

**Recurring encounter:** One daily mystery present per eligible player. Surprise cosmetic hit messages and low-frequency random weather changes modify only presentation unless explicitly described in rules.

| Day | Theme | One-day feature | Balance protection |
|---|---|---|---|
| 1 | Opening Barrage | Intro banner, character card and first quests | Standard caps |
| 2 | Fortification Frenzy | Fort Kit crafting costs 2 fewer Snowflakes for the day | Per-day use cap unchanged |
| 3 | Whiteout Wednesday* | Optional blizzard weather cosmetic + bonus +10 for one quest | Theme date-independent |
| 4 | Christmas Supply Drop | One extra non-Golden mystery present for anyone completing 3 quests | Same rarity limits |
| 5 | Snow Don's Revenge | Illustrated special boss skin and extra +10 for participating | Boss cap 50 |
| 6 | Blizzard Blitz | Optional bonus challenge worth +20 points | Themed bonus cap 30 |
| 7 | The Last Snowfall | Final leaderboard, last chance objectives, ending animation | No blanket score multiplier |

`*`The Day 3 label is flavour only; change it to “The Great Whiteout” if Day 3 is not a Wednesday. Themed reward modifiers are included under the one-off 30-point daily cap. No exclusive live 15-minute period is required for core championship points. Optional live announcements can be run at varied hours without granting irreplaceable advantage.

**Golden Snowball showcase:** If one is awarded, post an opt-in public highlight; protect the player's privacy and avoid pinging entire roles. If a golden attack hits, use a special animation frame and sound-caption text (not actual audio playback).

## 11. Discord information architecture

Suggested channel structure **inside the separate Operation Snowfall event Discord**, adjustable by Kat:

```
🎄 CHRISTMAS EVENT
├─ #snowfall-rules         read-only welcome, rules, prizes
├─ #snowfall-arena         pinned single live board and a few high-value highlights
├─ #snowfall-leaderboards  one editable personal board + one editable city board
├─ #snowfall-announcements daily themes, winners and major boss results
└─ #snowfall-admin         staff-only controls, audit alerts and result exports
```

Use one persistent public overview; personal menus and results are **ephemeral interaction responses**. Navigating private menus edits the existing interaction message wherever supported. Public leaderboard messages are edited at a throttled interval, e.g. no more frequently than every 60 seconds, and also after material milestones. Do not edit the entire public channel message on every individual snowball hit.

### UI A: public event board (always visible)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ❄ OPERATION SNOWFALL       DAY 3 OF 7             ┃
┃ City Wars (bragging rights) • Ends <timestamp>     ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ 🎄 TOP CITY          CHICAGO         742.50 pts   ┃
┃ 👑 TOP PLAYER        [MR username]   1,124 pts    ┃
┃ ☃ SNOW DON           46% HP • BATTLE OPEN         ┃
┃ 🏰 CITY SIEGE        4 / 6 FORTS CLEARED         ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ [ JOIN / MY PROFILE ]   [ ATTACK ]   [ QUESTS ]   ┃
┃ [ INVENTORY ]           [ BOSS ]     [ LEADERS ]  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### UI B: personal profile (ephemeral)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  [Illustrated avatar]  TheDude • Chicago          ┃
┃  Rank #12       Event Points 930       Level 4*  ┃
┃  Warmth   ███████░░░  70 / 100                    ┃
┃  Fort     ███░░░░░░░  8 / 25                      ┃
┃  Ammo      9 / 12     Next regen 12m 20s         ┃
┃  Snowflakes 18       Guard OFF                   ┃
┃  Today: PvP 158/300 • Boss 20/50 • Siege 16/50  ┃
┃ [ THROW ] [ GUARD ] [ ITEMS ] [ QUESTS ] [ BACK ]┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
*Level is cosmetic only; no accuracy or score bonus.
```

### UI C: throw flow

1. Select **Throw**, choose an eligible rival from a dropdown/paginated search or use `/snow throw player:<name>`.
2. Choose Quick Lob, Standard Throw, or Power Shot; show chance/damage/point preview.
3. Confirm. Resolve transaction once and show result as a text card plus a 1200×675 rendered still frame; a short GIF variant is optional at launch when image generation and latency allow.
4. Change existing private message to result screen, with **Throw Again**, **Profile**, **Targets** and **Back**. Disable action when cooldown or score cap applies; show remaining time.

### UI D: leaderboard

Tabs: Individual / Cities / Daily / Achievements. List top 10, current player's rank, and page controls. Separate public messages for individual and city standings; avoid exposing account verification or admin flags. Daily score is marked provisional until the period closes.

### UI E: admin console

Host-only view: Event state, registration opens, starts/ends, number self-declared, active users, identity disputes, boss HP, city standings, message sync status, recent events and buttons to pause/resume, announce, configure and finalize. All potentially destructive actions require a confirmation modal and audit entry.

### Rendered image assets

- `assets/ui/snowfall_logo.png` and `arena_banner.png` (1920×1080 originals, safe crop for Discord).
- Six atmospheric city backdrops, one per city (matched composition and colour grading).
- Character silhouettes or editable portraits in fedora/scarf variants; fallback silhouettes for users who do not set an avatar.
- Transparent snowball, fort, cocoa, mitten, bomb, golden snowball, boss and festive effects.
- `assets/ui/templates/profile.png`, `battle_result.png`, `boss.png`, `siege.png`, `winners.png` (all exported at 1200×675 or higher, consistent margins).
- Five to eight-frame compact GIFs for special events, with static PNG and descriptive text fallbacks; no media file required for a successful action.

## 12. User-facing slash commands and staff commands

| Command | Permission | Action |
|---|---|---|
| `/snow` | Anyone | Open dashboard |
| `/snow join` | Member | Register MR username and city |
| `/snow profile [player]` | Member | Show personal or public profile |
| `/snow throw [player] [style]` | Participant | Legal PvP attack |
| `/snow targets` | Participant | Search eligible rivals |
| `/snow collect` | Participant | Show regeneration/claim daily available gifts; no spam-to-farm |
| `/snow guard [on/off]` | Participant | Enter or leave guard |
| `/snow inventory` | Participant | Browse, use or craft items |
| `/snow quests` | Participant | View, claim daily objectives |
| `/snow present` | Participant | Open daily mystery present if earned |
| `/snow boss` | Participant | Show boss and attack |
| `/snow siege` | Participant | Show own city fortress and attack |
| `/snow leaderboard [individual/city/daily]` | Anyone | Standings |
| `/snow rules` | Anyone | Rules, limits, scoring, anti-abuse policy |
| `/snow help` | Anyone | Explain commands and gameplay |
| `/snowadmin setup` | Host/staff | Select channels, roles, dates, rewards |
| `/snowadmin open-registration` | Host/staff | Open signups |
| `/snowadmin start` | Host | Start configured season (confirm) |
| `/snowadmin pause [reason]` | Host | Freeze gameplay clock (confirm) |
| `/snowadmin resume` | Host | Resume with pause duration adjusted |
| `/snowadmin player [user]` | Staff | Inspect player and verification |
| `/snowadmin review [user]` | Staff | Clear or flag disputed self-declared identity, with reason |
| `/snowadmin transfer-city [user] [city]` | Host | Schedule next-day switch with reason |
| `/snowadmin flag [user] [reason]` | Staff | Flag account; suppress from award review if needed |
| `/snowadmin adjust [user] [points/items] [reason]` | Host | Ledger adjustment, never destructive SQL edit |
| `/snowadmin theme [day]` | Host | Set daily theme before day start |
| `/snowadmin announce [text]` | Host/staff | Send event announcement |
| `/snowadmin recalc` | Host | Rebuild and compare scores from ledger |
| `/snowadmin export [format]` | Host | CSV/JSON results and audit |
| `/snowadmin finalize` | Host | Freeze, review and publish (confirm) |
| `/snowadmin reset-sandbox` | Host | Test instance only; blocked in live production |

Names, descriptions and options will be synchronised using Discord application commands. Buttons call the same service functions as slash commands so there is only one rules implementation.

## 13. Architecture

**Recommended runtime:** Python 3.12+, pinned current compatible `discord.py` with Components v2 `discord.ui.LayoutView` (2.6+), `aiosqlite` for a single bot process or async SQLAlchemy with PostgreSQL if multi-instance deployment, Pillow for composited PNG cards, Pytest for tests, Docker for repeatable deployment. Avoid putting the entire game in one monolithic bot file.

**Discord layer** → interaction defer/validation, public persistent views, slash commands, access controls.  
**Domain layer** → registration, resources, combat, inventory, objectives, boss, siege, scores and city normalization.  
**Persistence layer** → transaction-safe SQLite in WAL mode for one instance; row-level locking with PostgreSQL when scaled.  
**Scheduler** → idempotent daily boundaries, regeneration via timestamps, quest generation, boss/fort snapshots, announcements and scoreboard edits.  
**Renderer** → generated images from existing art, template files and fonts; cached where safe. Rendering failure must never roll back valid game state.  
**Audit/exports** → immutable event ledger, reconciliation, CSV/JSON winner summaries.

Suggested repo layout:

```
snowfall-bot/
├─ bot.py
├─ config.example.toml
├─ Dockerfile
├─ requirements.lock
├─ src/snowfall/
│  ├─ commands/{public,admin}.py
│  ├─ ui/{dashboard,profile,combat,leaderboards,admin}.py
│  ├─ services/{registration,combat,economy,items,quests,boss,siege,scoring}.py
│  ├─ core/{rules,clock,rng,permissions,errors}.py
│  ├─ db/{models,repositories,migrations}.py
│  ├─ jobs/{day_rollover,notifications,reconcile}.py
│  ├─ graphics/{renderer,assets}.py
│  └─ observability/{logging,metrics}.py
├─ assets/{ui,backgrounds,characters,effects,items}/
└─ tests/{unit,integration,simulation,discord_contracts}/
```

### Database tables

- `seasons(id, status, starts_at_utc, ends_at_utc, paused_duration_s, config_json, winner_snapshot_hash)`
- `players(id, discord_user_id, mr_username, mr_username_normalized, verification_state DEFAULT self_declared, joined_at)`
- `season_players(season_id, player_id, initial_city, current_city, joined_day, last_scored_action_at, is_flagged)`
- `player_resources(season_id, player_id, snowballs, snowball_regen_at, warmth, warmth_regen_at, snowflakes, armour_hp, armour_expires_at, guard_until, last_throw_at, knockout_until)`
- `inventory(season_id, player_id, item_type, quantity)`
- `combat_log(id, season_id, day, attacker, target, style, rng_proof, hit, crit, damage, armour_absorbed, points, happened_at, interaction_id UNIQUE)`
- `score_ledger(id, season_id, player_id, city_id, day, category, points, source_id, created_at, UNIQUE(source_id, category, player_id))`
- `quests(season_id, player_id, day, quest_id, progress, claimed)`
- `daily_boss(season_id, day, hp_start, hp_remaining, is_defeated, last_hit_player_id)` and `boss_attempts(..., interaction_id UNIQUE)`
- `daily_siege(season_id, city_id, day, hp_start, hp_remaining, cleared)` and `siege_attempts(..., interaction_id UNIQUE)`
- `city_memberships(season_id, player_id, city_id, effective_from_day, effective_to_day)`
- `city_daily_snapshots(season_id, city_id, day, total, participant_count, siege_bonus, finalized_at)`
- `present_claims(season_id, player_id, day, reward_type, UNIQUE(season_id, player_id, day))`
- `admin_audit(id, actor_id, action, before_json, after_json, reason, at)`
- `discord_messages(season_id, purpose, channel_id, message_id, last_edited_at)`
- `job_runs(season_id, day, job_key, completed_at, UNIQUE(season_id, day, job_key))`

Add indexes for leaderboard `score_ledger(season_id, day, player_id)`, attacks per pair/day, and active target queries. All derived scores can be rebuilt from the ledger. The database—not old Discord message text—is the source of truth.

### Concurrency and Discord API safeguards

- Discord interaction must receive an initial response or defer within **3 seconds**; dispatch slow DB/render work after deferring.
- Re-register persistent component callbacks after bot restart; use stable custom IDs with season/action IDs, not serialized mutable state.
- For public messages, debounce edits to ~60 seconds, retry on transient Discord errors using library backoff and respect rate limits.
- For ephemeral private views, edit the original interaction response for navigation when allowed; create new private response only when necessary.
- Components v2 text/containers/media are **not interchangeable with traditional embeds** in the same v2 message. Use `LayoutView` for new rich screens, or use classic Embed + View as a separate fallback message type.
- Give the application only needed guild permissions: application commands, send messages, embed links/attach files if using those features, and view chosen channels. Avoid administrator permission.
- Keep bot token and any admin keys in environment variables, never in repo; log no credentials or protected IDs beyond service operation requirements.

## 14. Balance checks and acceptance tests

**Automated checks:**

1. 100,000 simulated attacks approximate intended stance hit rates: 75/60/40%, with allowed random tolerance.
2. No duplicate attack from two repeated Discord callbacks with identical interaction ID.
3. Two concurrent attacks on the last snowball cannot both spend it; ammo never negative.
4. PvP score never exceeds 300 per day; boss never exceeds 50; siege never exceeds 50; quests award at most 60.
5. No target receives scoring damage while shielded, knocked out, inactive, self-targeted, or same city.
6. Pair limit and incoming attack protections are respected under concurrency.
7. Daily reset occurs every 24 hours from season start and is executed once after restart.
8. Fort absorbs damage before warmth; criticals and item modifiers obey clamps.
9. Mystery present totals 100% and one claim/day; golden cannot exceed seasonal cap.
10. Identical city roster and contributions produce identical scores; population bonuses cap at 40.
11. Score can be rebuilt from ledger to match cached leaderboard and winner snapshot.
12. Pausing for 2 hours does not consume a day's clock time or deliver a double reset.
13. Registered city changes are effective on next day; historic credits do not migrate.
14. Host permissions prevent non-staff triggering admin features; confirmation required to finalize. Self-declaration never blocks registration awaiting routine approval.
15. Restart rehydrates dashboards and buttons, and stale buttons give a safe refresh prompt.
16. Image renderer errors fall back to text without losing committed actions.
17. A complete seven-day synthetic run finishes and exports stable individual prize winners and a city bragging-rights champion with tie-break details.
18. Time-zone tests cover UK GMT/BST transitions using UTC storage and Discord display.
19. Abuse tests: collusive paired accounts, mass late registration, MR username casing duplicates, repeated public clicks, blocked user mentions.
20. Screen tests check mobile readability, alt text, display limits and no more than the expected number of messages.

**Balance simulations:** Run modeled archetypes: casual (10-15 legal shots/day), regular (20-30), dedicated (40-60), and coordinated city teams of 3/5/10/30. Examine expected daily scoring ranges, effective participation ratio, KO frequency, top-five city normalization, and boss completion rate before launch. Rules and tuning should be frozen at the start of a live event except for clear exploit/safety fixes disclosed by Kat.

## 15. Abuse prevention, moderation and operations

- One Discord user account → one MR username per season; one claimed MR username → one Discord account. All entries begin as self-declared, playable unless flagged. Staff may flag, clear or disqualify disputed identities with a recorded reason; no mandatory preregistration verification.
- Cap pairwise hits, daily scored attacks, item grants, present claims, boss/siege attempts and defensive scores.
- No point transfers, trading, self-targeting or same-city scored attacks.
- Public usernames are sanitized; avoid unsolicited user mentions and `@everyone`.
- Restrict administrative actions by guild permission + explicit role or allow-list, and record actor, reason, old/new values.
- Player flagging should be reviewable, never silently rewrite or erase raw transaction history. Undo rewards by compensating ledger entries.
- Daily automatic backup, pre-event dry run restore, health check, log rotation, retention policy, 24/7 hosting and notification on scheduler failure.
- Use a private sandbox guild and separate development database/token. No production reset functionality.
- If the bot goes down, game time remains defined and missed scheduled jobs run idempotently on recovery; if outage significantly affects fairness, Kat may choose to pause/extend with public notice.
- Make clear this is an unofficial fan community competition unless MR operators expressly endorse it.

## 16. Prize and final-results handling

Approved prize policy: **individual prizes only**. Kat sets amounts and winner eligibility before registration opens. Proposed award categories:

- **Individual:** 1st/2nd/3rd for seven-day total.
- **City:** No monetary, credit, item or perk awards. Champion city receives a commemorative title/banner and bragging rights only.
- **Special:** Snow Don Slayer (boss contribution), Golden Arm (accuracy with minimum 30 throws), Christmas Chaos (achievement variety), and Community Hero (daily participation).

Use prizes that do not require the bot to access MR accounts. Individual winners export includes MR username, Discord ID, city affiliation for display only, total and per-day scores, tie-break results, and identity-dispute status. City standings have a separate public non-prize export. Export is staff-only until Kat publishes the winners. Reward distribution is manual and logged as `pending/confirmed`; bot never asserts credits were paid without staff confirmation.

## 17. Build order (full-feature v1.0)

**Milestone A — foundation:** Repository, dedicated-guild restriction, automated 7-day-before registration, self-declared identities, six-city selection, schema/migrations, UTC clock, persistent buttons, staff roles, dashboard.  
**Milestone B — core:** Resource regen, legal PvP, warm/cold/KO/guard states, fair scoring ledger, target selection, attack screens, combat tests.  
**Milestone C — economy:** Inventory, item crafting, daily objectives, mystery presents, anti-abuse constraints, season-day reset logic.  
**Milestone D — multiplayer features:** Boss, city siege, daily themes, normalized city leaderboard, score snapshots, announcement scheduler.  
**Milestone E — artwork/UX:** Six city backgrounds, composited profile/attack/boss/fort cards, result animation/fallback, mobile usability, minimal-message policy.  
**Milestone F — launch safety:** Closed simulated event, load/restart tests, rate-limit handling, data backups, audit/export, runbook, host final review.

**Definition of done:** Kat can create and start a seven-day event; multiple participants can register, attack, defend, complete quests and PvE, earn points and see updates; the bot survives restart without duplication; participants cannot exploit the common limits; exactly one individual champion and one city (bragging-rights) champion can be determined transparently; only individual prize winners are exported for payout.

## 18. Launch configuration (illustrative)

```toml
[event]
name = "Operation Snowfall"
duration_days = 7
registration_open_hours_before = 168
start_at_utc = "SET_BY_HOST"
allow_late_join = true
allow_city_change = "admin_next_day_only"
registration_mode = "self_declaration"
prize_mode = "individual_only"
guild_mode = "single_dedicated_server"

[resources]
starting_snowballs = 8
snowball_cap = 12
snowball_regen_seconds = 1200
warmth_max = 100
warmth_regen_amount = 5
warmth_regen_seconds = 1200
throw_cooldown_seconds = 30
knockout_seconds = 1800
knockout_recovery_warmth = 50

[pvp]
score_cap_per_day = 300
scoring_hits_per_pair_day = 2
incoming_hits_window_seconds = 1800
incoming_hits_before_protection = 3
protection_seconds = 900
inactive_target_seconds = 129600

[scoring]
city_individual_contribution_cap = 300
city_top_players = 5
city_min_eligible_active = 3
city_participation_bonus_per_extra = 4
city_participation_bonus_cap = 40
city_siege_clear_bonus = 25

[interface]
public_board_refresh_seconds = 60
private_interactions_ephemeral = true
image_fallback_to_text = true
```

## 19. Approved organiser decisions and remaining setup

**Approved (locked for the v1.0 build):**
1. Registration uses **self-declaration** of MR username and city with no standard approval queue. Staff only investigate disputes or suspected abuse.
2. **Individual prizes only.** The city competition continues for rankings, a ceremonial champion banner and bragging rights; no city payout.
3. Host in a **separate dedicated event Discord server**. Bot commands and persistent controls must reject other guilds/DMs.
4. Registration opens **168 hours (7 days) prior to the event's configured UTC start** and remains available during LIVE. Competition runs for exactly 168 effective hours over seven full game days.

**Still needed from Kat before the production launch (not blockers for development):**
1. Exact UTC start timestamp and dedicated Discord guild/channel IDs.
2. Allowed staff roles and permission/appeals policy.
3. Individual prize amounts, budget and payout procedure.
4. Approval of art style, asset licensing and any MR-community moderation notices.
5. Confirmation of late joining, disqualification and post-finalisation appeals window.

**Acceptance gates added by these decisions:**
- Signups are blocked before `starts_at_utc - 168h`, permitted during REGISTRATION and LIVE, and blocked at final end; time zone does not affect start logic.
- Two Discord users cannot register the same case-folded MR name; false claims require an audit-visible dispute resolution, not an automatic ownership claim.
- City winners appear in boards and announcements but never in prize payout CSV.
- A command invoked in any other Discord guild or DM is rejected before any game mutation.


**Document conclusion:** v1.0 will be a complete seven-day, dedicated-server Discord event with self-declared registration, individual prizes, non-prize city rankings, PvP, two leaderboards, boss and sieges, items, daily objectives, graphics, persistent auditing and an admin operations console. The foundation scaffold and development ticket backlog accompany this specification.
