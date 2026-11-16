# ❄️ Operation Snowfall — v0.1.3 Christmas Economy (Milestones A + B + C)

Kat (MK)'s **unofficial** MafiaReturns Christmas snowball competition for **one dedicated Discord event server**. This release implements all eight Foundation tickets (SNOW-001–008), five Combat tickets (SNOW-009–013) and three Economy/Quest/Gift tickets (SNOW-014–016). **Not full v1.0:** Snow Don, city sieges, season themes, artwork and prize exports remain future milestones.

## Approved event configuration

- **7 days / 168 effective hours** after Kat or a configured host issues `/snowadmin start START` on or after the scheduled kickoff.
- **Registration opens exactly 7 days before** the scheduled kickoff, remains open until the season closes, and is based on self-declared MR username + one of six cities.
- **Chicago, New York, Detroit, Philadelphia, Las Vegas and Los Angeles** compete for honorary city titles; **only individuals receive real prizes** in the final release.
- The bot accepts interactions only in the configured **dedicated Discord guild** (not DMs/other servers). No MR passwords, MR API access, or account scraping.
- Staff may review disputed claims without a mandatory verification queue; only configured host user IDs may control the game clock.

## Installation / upgrade (PyCharm, Python 3.13)

**Stop the bot and back up `data/snowfall.sqlite3` first** (for a running bot use the SQLite online backup API). v0.1.3 upgrades the schema from v3 to **v4**, preserving all accounts, previous combat and scores. Keep your local `.env`, `config.toml` and database when pulling. They are ignored by Git.

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

If setting up a new instance:
1. Copy `config.example.toml` to **`config.toml`**. Enter a dedicated server `guild_id`, at least one host `admin_user_ids`, optional `staff_role_ids`, and an ISO-8601 UTC future `starts_at_utc`.
2. Copy `.env.example` to **`.env`** and set `DISCORD_TOKEN` there only.
3. Invite your Discord application using the `bot` and `applications.commands` scopes. Grant **View Channel, Send Messages, Embed Links and Read Message History** in the event channel. No privileged Message Content intent required.
4. Run the commands above. In the server, use `/snowadmin status` and `/snowadmin publish-dashboard` as the host.

**Important:** `/snowadmin start START` is deliberately manual and begins the actual 168-hour clock. Don't test it on your real Christmas season before launch. Use a separate `season_key` and database for practice. A host can pause and resume the season; game-day time, regeneration, protections, and cooldowns freeze during pauses.

## Combat commands and controls

| Command | Purpose |
|---|---|
| `/snow dashboard` | Open private dashboard (public pinned dashboard also has Throw button) |
| `/snow join` | Self-declare MR username and city |
| `/snow ready` | **Opt in** to being targeted for 36 active event hours, with **zero** bonus points |
| `/snow targets` | Show up to 25 currently eligible rival-city targets in a private picker |
| `/snow throw` | Choose a target; or `/snow throw target:@player` to jump to attack style |
| `/snow profile` | Snowballs, warmth, snowflakes, day/season PvP totals |
| `/snow leaderboard` | Top 10 individual scores (no city prize implication) |
| `/snow cities` | City registration totals (honorary only) |
| `/snow rules` | Gameplay, gifts and identity policy |
| `/snow inventory` | Private inventory with Craft, Use, Guard and Quests buttons |
| `/snow craft item:<item>` | Spend Snowflakes on cocoa, fort, mittens or bomb |
| `/snow use item:<item>` | Restore warmth, deploy fort or arm a throwing buff |
| `/snow guard mode:on/off` | Temporary 30m defence; 2h activation cooldown |
| `/snow quests` | Show three day-scoped quest objectives, claim buttons and gifts |
| `/snow claim quest:<quest>` | Claim 20 points plus up to 2 Snowflakes once per quest/day |
| `/snow present` | Claim one quest-earned gift per day; bonus:true on Day 4 after all three quests |
| `/snowadmin status`, `setup`, `start`, `pause`, `resume`, `finalize`, `review`, `export-registrations`, `publish-dashboard` | Staff/host foundation controls |

The Throw button and slash path use the same engine: **pick target → choose Quick / Standard / Power / Golden → preview → confirm → result**. The private interaction message is edited, avoiding channel spam. Failed validations don't spend snowballs or add a score.

### Combat and item rules in v0.1.3

| Type | Hit chance | Warmth damage | Personal points on hit |
|---|---:|---:|---:|
| Quick Lob | 75% | 8 | 8 |
| Standard Throw | 60% | 14 | 12 |
| Power Shot | 40% | 22 | 18 |

- Start with **8** snowballs (cap **12**) and **100** warmth. Gain **1 snowball every 20 minutes**, **5 warmth every 20 minutes** outside KO. At cap, no regeneration is banked. Late registrations start with 8 balls and don't receive pre-join regeneration.
- **30 seconds** between throws; **one** snowball spent only on a legal attempt, even when it misses. Server-side cryptographic RNG decides hit and 10%-chance critical (+4 damage, +3 points). Critical roll occurs only on a hit.
- **Bonuses:** first scored hit against each rival city per day +5 points; knockout +10, maximum 3 awarded KO bonuses/day. Scored successful hits grant +1 Snowflake, capped at 100. Fort armour absorbs damage first; fort absorption grants defender +2 points within the daily cap.
- **Daily PvP cap: 300 points per player**, shared across attacks and fort-defence bonuses. After reaching it, further PvP throws are blocked (no unscored harassment). Day uses pause-adjusted effective UTC.
- **Anti-camping:** two scored successful hits per attacker/target/day; after 3 scored incoming hits within 30 active minutes, target receives 15 active minutes of protection, retriggered only after 3 *new* hits. Players cannot hit themselves, same-city members, disqualified users, KO'd or shielded users.
- Knockout at 0 warmth means **30 minutes** of protection (no attacking). Recovery restores **at least 50 warmth** before normal regeneration resumes.
- **36-hour inactivity shield**: only players who've used `/snow ready` or earned an eligible scoring action within 36 effective hours appear as targets. `/snow ready` is a combat-only onboarding exception to bootstrap battles before the boss/quest systems can supply scored actions. It gives **no points, ammo or rewards**.
- **No score or ammo awarded during pauses**, and no attack may occur outside LIVE. Resource regeneration stops at the effective 168-hour endpoint.
- Every attack has an **immutable log with recorded RNG rolls** and a unique Discord interaction ID. The personal score ledger is insert-only; duplicate interaction retries return their previously stored outcome without spending again. Player totals can be reconciled from the ledger.


## Milestone C — Economy, daily missions and Christmas presents

Each new participant gets **one Hot Chocolate** (seeded exactly once even on migrated accounts). Their inventory and Snowflake balance are private. Snowflakes are earned from scored PvP hits and quest claims, capped at 100, and **cannot be bought**.

| Item | Craft cost | Activation effect | Daily use limit |
|---|---:|---|---:|
| Hot Chocolate (`cocoa`) | 8 ✨ | Restore up to 30 warmth (not while KO) | 2 |
| Fort Kit (`fort`) | 10 ✨ (8 on Day 2) | Deploy 25 armour for 6 effective hours; one active fort | 2 |
| Precision Mittens (`mittens`) | 6 ✨ | Arm +10 percentage point accuracy boost on next legal throw | 2 |
| Blizzard Bomb (`bomb`) | 15 ✨ | Arm +7 damage and +5 hit points for next legal **Power Shot** | 1 |
| Golden Snowball (`golden`) | Not craftable | Special 80% accuracy, 25 damage, 25 base points; consumes Golden instead of ordinary ammo | 1 seasonal award |

- Guard mode lasts **30 effective minutes**, gives attacking rivals −10 percentage points accuracy and −2 warmth damage, prevents the guarding player attacking, and can be reactivated only after **two effective hours**. Lowering guard does not erase this cooldown.
- Item limits are enforced transactionally. Crafting, activating, claiming and gift opening use unique Discord interaction IDs. Throws consume armed buffs only on **legal** attempts (including misses). If a Blizzard Bomb is armed, only Power Shot is allowed until it is used.
- Fort absorption earns the defender up to +2 defence points on a hit, up to a total of **10 defence points/day** and within the 300 daily PvP cap.
- Golden Snowball has only **one award per player per season**, at **1%** from daily presents. It uses its own one-use inventory item, not a standard snowball; its *future* city contribution is capped at 10 points. The actual individual hit score is still capped by daily PvP limits.
- **Daily missions, 20 personal points + up to 2 Snowflakes each**, one claim per mission per game day (maximum 60 quest points/day): (1) Five legal throws, (2) successful scoring hits on two different rivals, (3) Winter Preparation — one legal craft, item use, or guard activation. Objective 3 is a **temporary Milestone C fallback** for the approved boss/siege contribution objective and will switch when PvE launches. Day boundaries use the pause-adjusted 24-hour event days.
- **Mystery present:** Once per game day after claiming any mission. Chances: +3 snowballs to holding cap 40%, cocoa 25%, mittens 20%, fort 10%, bomb 4%, Golden 1%. When a grant exceeds inventory cap or Golden has already been awarded, substitute **up to 5 Snowflakes**. Exactly one regular gift/day; on **Day 4** completing all three missions also unlocks **one extra non-Golden gift**.
- Gifts and claimed quests are persisted and immutable; reconnects/restarts cannot reroll a present or reclaim points. The public leaderboard remains for **individual prizes only**; city rewards are honorary.

## Before starting the bot

If you still see **Discord 403 Missing Access** while syncing slash commands, that's unrelated to crafting. Confirm the `guild_id` in your private `config.toml` matches the dedicated server **ID** and that the *same application* behind your `.env` token is installed in that server with both `bot` and `applications.commands` scopes. The bot needs View Channel / Send Messages / Embed Links / Read Message History for its dashboard. Do not paste tokens or unignored local config files in chat or GitHub.

## Verification / rollout

```powershell
python -m compileall -q src bot.py
python -m pytest -q
```

Tests include SQLite v1/v2/v3→v4 migrations, a crash-safe last-snowball simultaneous attack, replay protection, daily cap, shield expiry, resource clocks, restart persistence, and pause/resume. GitHub Actions runs on **Python 3.12 and 3.13**. **The Discord gateway interaction flows still need an in-server smoke test** before the production event.

For a two-account **development season**, do the following:
1. Start with two Discord members registered in **different cities**; verify `/snow profile` shows 8/12 balls and 100/100 warmth.
2. Host presses `/snowadmin start START` (only in test season). Each player uses `/snow ready`.
3. Player A runs `/snow targets` (or dashboard Throw); chooses B; selects and confirms an attack; inspect their result and profile.
4. Attempt two consecutive throws; the second must be rejected until 30 seconds elapse. A miss consumes ammo but gives no points; hits increase score.
5. Confirm a same-city/self/KO/protected/inactive target cannot be attacked and invalid requests don't consume ammo.
6. Restart `python bot.py` and confirm the permanent dashboard and saved score still work.
7. Confirm `/snowadmin pause PAUSE ...` freezes throws and resources; `/snowadmin resume RESUME` resumes the effective clock. Use a test season only.

## Safety and deployment notes

- Never commit `.env`, `config.toml`, `data/`, a live SQLite database or tokens. SQLite WAL files must be included in a consistent backup using the SQLite online backup API or after safely shutting down the bot.
- This is a **single-process** SQLite service, not a multi-instance distributed bot. `BEGIN IMMEDIATE` serializes competing throws; move to a transactional database before using multiple workers/instances.
- Staff identity flags do not secretly remove scores. Disqualified users disappear from public leaderboards but their historical immutable ledger remains; corrective adjustments are reserved for a later release.
- Combat is functional at the domain/database level and exposed via Discord commands/buttons, but **v1.0 launch readiness is not claimed**. Artwork, boss, siege, full city scoring and individual prize exports remain upcoming milestones.

See [`docs/RELEASE_v0.1.3.md`](docs/RELEASE_v0.1.3.md), [`docs/RELEASE_v0.1.2.md`](docs/RELEASE_v0.1.2.md), [`docs/DEVELOPMENT_TICKETS.md`](docs/DEVELOPMENT_TICKETS.md), and [`docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md`](docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md).
