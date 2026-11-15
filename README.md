# ❄️ Operation Snowfall — foundation starter (0.1.0)

Kat (MK)'s **MafiaReturns fan-community Christmas snowball event**, built as a dedicated-server Discord bot.

> **Important:** This zip is a functioning **foundation**, not the full v1.0 game. It implements registration, staff dispute review, UTC preregistration gating, city signup counts, basic dashboard and pure city score math. **It does not yet provide PvP, points, quests, bosses, sieges, assets, prize payout or a full 7-day runtime scheduler.** Follow `docs/DEVELOPMENT_TICKETS.md` to implement the rest. Full setup, Discord smoke tests, and release gates are documented in `docs/SETUP_AND_RELEASE.md`.

## Locked v1.0 decisions

- One dedicated event Discord server; commands are guild-scoped and guild-checked.
- Registration automatically opens **168 hours before** configured event start; participants self-declare MR username and city. Late joining remains possible while LIVE.
- **Individual prizes only.** City standings are for titles and bragging rights.
- Seven-day / 168-hour main game, with six participating cities.

## Setup in PyCharm / PowerShell

1. Create your separate Discord server and application at the Discord Developer Portal.
2. Copy `config.example.toml` to `config.toml`; set `guild_id`, a real `starts_at_utc` in UTC, and `admin_user_ids` (Kat/staff Discord IDs).
3. Copy `.env.example` to `.env`; set `DISCORD_TOKEN`. Do **not** commit `.env`.
4. Use Python 3.12 or newer, then install and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]" python-dotenv
python -m pytest -q
python bot.py
```

For Linux/macOS, activate `.venv/bin/activate` and run the same pip/pytest/bot commands.

**Bot permissions:** `bot` and `applications.commands` install scopes, View Channels, Send Messages, Use Application Commands; no Administrator permission required. The bot only registers slash commands in the configured guild. Private responses use ephemeral messages.

## Available starter commands

| Command | Starter behavior |
|---|---|
| `/snow dashboard` | Private interactive welcome/dashboard |
| `/snow join` | City dropdown + MR username self-declaration modal |
| `/snow profile` | Displays your stored signup |
| `/snow cities` | Registration counts only (not city competition score) |
| `/snow rules` | Policy summary |
| `/snowadmin status` | Private event and registration status |
| `/snowadmin review` | Staff flag / clear / disqualify with audit reason |
| `/snowadmin export-registrations` | Private staff CSV (NOT the eventual prize payout file) |

## Code layout

```text
Operation_Snowfall_v1.0_Starter/
├── bot.py
├── .env.example
├── config.example.toml
├── Dockerfile
├── pyproject.toml
├── docs/
│   ├── GAME_DESIGN_SPEC_v1.0_APPROVED.md
│   ├── DEVELOPMENT_TICKETS.md
│   ├── DEVELOPMENT_TICKETS.csv
│   ├── ORGANISER_DECISIONS.md
│   └── SETUP_AND_RELEASE.md
├── src/snowfall/
│   ├── app.py, config.py
│   ├── commands/{public,admin}.py
│   ├── core/{clock,scoring}.py
│   ├── db/store.py, db/migrations/
│   ├── ui/dashboard.py
│   ├── services/, jobs/, graphics/   # planned modules
│   └── __main__.py
├── assets/
└── tests/{test_clock,test_registration,test_scoring}.py
```

## Technical notes

- DB stored at `data/snowfall.sqlite3` by default; do not commit it. SQLite uses WAL mode and case-normalised MR-name uniqueness per season.
- No MR credentials, no automatic verification, no external MR integration. The community event is unofficial unless authorised by MafiaReturns.
- Staff reviews are recorded in an audit table. Future moderation and award processing must use the same auditable workflow.
- Dashboard uses classic Embed + persistent View as a starter. Full rich Components v2 art cards are a separate tracked milestone; do not combine traditional embed fields with Components v2 messages.
- Pause/resume logical time and fully transactional gameplay are **not** in this foundation build and must be implemented before the actual event.
- Discord user IDs and MR usernames are personally identifiable game metadata. Restrict export to staff, set retention policy, and protect DB backups.
