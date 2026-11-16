# ❄️ Operation Snowfall — v0.1.2 Snowball Combat (Milestones A + B)

Kat (MK)'s **unofficial** MafiaReturns Christmas snowball competition for **one dedicated Discord event server**. This release includes all eight Foundation tickets (SNOW-001–008) and all five Snowball Combat tickets (SNOW-009–013). It is not a full v1.0 event release: items/crafting, daily quests, Snow Don, city sieges, artwork and prize exports are still future milestones.

## Approved event configuration

- **7 days / 168 effective hours** after Kat or a configured host issues `/snowadmin start START` on or after the scheduled kickoff.
- **Registration opens exactly 7 days before** the scheduled kickoff, remains open until the season closes, and is based on self-declared MR username + one of six cities.
- **Chicago, New York, Detroit, Philadelphia, Las Vegas and Los Angeles** compete for honorary city titles; **only individuals receive real prizes** in the final release.
- The bot accepts interactions only in the configured **dedicated Discord guild** (not DMs/other servers). No MR passwords, MR API access, or account scraping.
- Staff may review disputed claims without a mandatory verification queue; only configured host user IDs may control the game clock.

## Installation / upgrade (PyCharm, Python 3.13)

**Back up `data/snowfall.sqlite3` first**, before running the new code; v0.1.2 upgrades the schema from version 2 to **version 3**. Keep your local `.env`, `config.toml` and database when pulling. They are ignored by Git.

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
| `/snow rules` | Gameplay and identity policy |
| `/snowadmin status`, `setup`, `start`, `pause`, `resume`, `finalize`, `review`, `export-registrations`, `publish-dashboard` | Staff/host foundation controls |

The Throw button and slash path use the same engine: **pick target → choose Quick / Standard / Power → preview → confirm → result**. The private interaction message is edited, avoiding channel spam. Failed validations don't spend snowballs or add a score.

### Exact combat rules in v0.1.2

| Type | Hit chance | Warmth damage | Personal points on hit |
|---|---:|---:|---:|
| Quick Lob | 75% | 8 | 8 |
| Standard Throw | 60% | 14 | 12 |
| Power Shot | 40% | 22 | 18 |

- Start with **8** snowballs (cap **12**) and **100** warmth. Gain **1 snowball every 20 minutes**, **5 warmth every 20 minutes** outside KO. At cap, no regeneration is banked. Late registrations start with 8 balls and don't receive pre-join regeneration.
- **30 seconds** between throws; **one** snowball spent only on a legal attempt, even when it misses. Server-side cryptographic RNG decides hit and 10%-chance critical (+4 damage, +3 points). Critical roll occurs only on a hit.
- **Bonuses:** first scored hit against each rival city per day +5 points; knockout +10, maximum 3 awarded KO bonuses/day. Scored successful hits grant +1 Snowflake, capped at 100. Fort armour (once item systems are built) absorbs damage first; fort absorption grants defender +2 points within the daily cap.
- **Daily PvP cap: 300 points per player**, shared across attacks and fort-defence bonuses. After reaching it, further PvP throws are blocked (no unscored harassment). Day uses pause-adjusted effective UTC.
- **Anti-camping:** two scored successful hits per attacker/target/day; after 3 scored incoming hits within 30 active minutes, target receives 15 active minutes of protection, retriggered only after 3 *new* hits. Players cannot hit themselves, same-city members, disqualified users, KO'd or shielded users.
- Knockout at 0 warmth means **30 minutes** of protection (no attacking). Recovery restores **at least 50 warmth** before normal regeneration resumes.
- **36-hour inactivity shield**: only players who've used `/snow ready` or earned an eligible scoring action within 36 effective hours appear as targets. `/snow ready` is a combat-only onboarding exception to bootstrap battles before the boss/quest systems can supply scored actions. It gives **no points, ammo or rewards**.
- **No score or ammo awarded during pauses**, and no attack may occur outside LIVE. Resource regeneration stops at the effective 168-hour endpoint.
- Every attack has an **immutable log with recorded RNG rolls** and a unique Discord interaction ID. The personal score ledger is insert-only; duplicate interaction retries return their previously stored outcome without spending again. Player totals can be reconciled from the ledger.

## Verification / rollout

```powershell
python -m compileall -q src bot.py
python -m pytest -q
```

Tests include SQLite v1/v2→v3 migrations, a crash-safe last-snowball simultaneous attack, replay protection, daily cap, shield expiry, resource clocks, restart persistence, and pause/resume. GitHub Actions runs on **Python 3.12 and 3.13**. **The Discord gateway interaction flows still need an in-server smoke test** before the production event.

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
- Combat is functional at the domain/database level and exposed via Discord commands/buttons, but **v1.0 launch readiness is not claimed**. Artwork, items, boss, siege, full city scoring and individual prize exports remain upcoming milestones.

See [`docs/RELEASE_v0.1.2.md`](docs/RELEASE_v0.1.2.md), [`docs/DEVELOPMENT_TICKETS.md`](docs/DEVELOPMENT_TICKETS.md), and [`docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md`](docs/GAME_DESIGN_SPEC_v1.0_APPROVED.md).
