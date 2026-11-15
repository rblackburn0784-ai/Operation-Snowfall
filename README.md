# ❄️ Operation Snowfall — v0.1.1 Foundation (Milestone A)

Kat (MK)'s unofficial MafiaReturns Christmas snowball event for **one dedicated Discord server**.

**This is the completed FOUNDATION milestone (SNOW-001 to SNOW-008), not the finished game.**
You can register, review claims, publish a restart-safe welcome/dashboard, and control the game clock.
PvP, resources, quests, bosses, sieges, graphics and prize payout are **not enabled** until subsequent milestones.

## Approved rules

- **168 hours (seven days)** of effective play after the host presses START on or after the configured kickoff.
- Registration automatically opens **168 hours before** the planned kickoff, stays open during the season and does not need routine approval.
- Players self-declare their **MafiaReturns username and city**; no MR login or password collection.
- The **six cities** compete for bragging rights; **only individuals receive prizes** in the finished game.
- Kat and explicitly configured **host user IDs** control start, pause, resume, finalise and scheduling.
- Optional **staff role IDs** can flag/clear/disqualify claims, but **cannot** control event lifecycle.
- The game runs **only in the configured dedicated Discord guild**, never in DMs or other guilds.

## Installation on Windows / PyCharm Python 3.13

1. Open the existing `Operation-Snowfall` project in PyCharm. **Back up `data/snowfall.sqlite3` if you're upgrading a real database.**
2. Copy `config.example.toml` to `config.toml`, configure your **dedicated server guild ID**, Kat's/hosts' **Discord USER IDs**, optional staff **role IDs**, and a real future UTC start date.
3. Copy `.env.example` to `.env`, and put your **Discord bot token** there only. Both files are ignored by Git.
4. In PyCharm's terminal with its venv activated:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

To connect the bot to Discord, invite it to your **dedicated server** with `bot` and `applications.commands` scopes, and grant View Channel, Send Messages, Embed Links, and Read Message History in your chosen dashboard channel. No admin privilege and no Message Content intent required.

### Bot commands

| Command | What it does |
|---|---|
| `/snow dashboard` | Private event dashboard with persistent buttons |
| `/snow join` | MR username + six-city self-declaration (registration window checked transactionally) |
| `/snow profile` | Private registration details |
| `/snow cities` | Registration counts per city, not prize standings |
| `/snow rules` | Identity, prizes, event status and fair-play policy |
| `/snowadmin status` | Staff-only lifecycle, signups and disputes |
| `/snowadmin review` | Staff flag/clear/disqualify with audit reason and old/new status |
| `/snowadmin export-registrations` | Staff-only private CSV (not prize payout) |
| `/snowadmin setup` | **Host only**; schedule a future UTC kickoff before registration opens, confirmation `SETUP` |
| `/snowadmin start` | **Host only**; start on or after scheduled kickoff, confirmation `START` |
| `/snowadmin pause` | **Host only**; freeze effective game time, confirmation `PAUSE` |
| `/snowadmin resume` | **Host only**; resume game time, confirmation `RESUME` |
| `/snowadmin finalize` | **Host only**; finalize only after 168 effective hours, confirmation `FINALIZE` |
| `/snowadmin publish-dashboard` | **Host only**; publish/update persistent public dashboard and welcome/rules in a channel |

**Start is deliberately manual.** At the scheduled kickoff the game enters **READY** until a host calls `/snowadmin start START`; if started late, the full 168-hour play window starts at actual start. During a pause the clock stops, and the end shifts by the paused duration. The stored schedule (including host changes) survives a bot restart; `config.toml` is only used to seed a new season.

### Post-install smoke check

1. Before registration opens, `/snow join` should say registration isn't open.
2. As a host, `/snowadmin status` shows registration/opening/kickoff, counts, and phase.
3. `/snowadmin publish-dashboard #your-channel` creates the welcome and rules card. Manually pin it if desired; publishing again updates it, not a second new post.
4. Restart `python bot.py` and check the public buttons still work.
5. At or after the planned kickoff, `/snowadmin start START`. Check that `/snowadmin pause PAUSE reason` and `/snowadmin resume RESUME` preserve the projected end. Do this **in a development season only** if the real event hasn't begun.
6. Confirm a regular player can't run host controls; a staff role can review but not start.

**Never put your token or users' MR passwords in GitHub.** A claim is *not* proof of MR ownership; staff can investigate disputed usernames. Registering in v0.1.1 does not make gameplay available.

## Data migrations and recovery

On startup, SQLite uses WAL and upgrades v0.1.0 databases to **schema version 2** without deleting registrations or existing audits. Migrations are transactional, repeat-safe, and followed by `PRAGMA quick_check`. Back up the DB including any active WAL state before migrating a production deployment. Database file and journal files are ignored by Git. Audit entries include before/after review state and lifecycle changes. Later gameplay needs its own idempotent transaction ledger.

## Project structure

```text
Operation-Snowfall/
├── bot.py                    # entry point
├── config.example.toml       # safe template; copy locally
├── src/snowfall/
│   ├── app.py                 # dedicated-guild command tree + persistent views
│   ├── config.py              # TOML and environment validation
│   ├── commands/{public,admin}.py
│   ├── core/{clock,permissions,scoring}.py
│   ├── db/store.py            # schema migrations, reviews, lifecycle, publication IDs
│   └── ui/dashboard.py        # persistent buttons and modal
├── tests/                    # foundational core tests
├── docs/RELEASE_v0.1.1.md
└── docs/DEVELOPMENT_TICKETS.md
```

Full roadmap: [`docs/DEVELOPMENT_TICKETS.md`](docs/DEVELOPMENT_TICKETS.md). Next: **Milestone B** combat and score ledger (SNOW-009 to SNOW-013).
