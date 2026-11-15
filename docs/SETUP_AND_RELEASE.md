# Setup, hosting and release notes

## 1. Create a separate Discord server

Use a separate **Operation Snowfall** server, not the normal MafiaReturns community server. Suggested permissions: Kat = event owner; trusted helpers = explicitly allow-listed staff; regular users = no admin rights. Suggested channels: `#welcome-and-rules`, `#snowfall-arena`, `#snowfall-leaderboards`, `#announcements`, and a staff-only `#snowfall-admin`.

## 2. Create the Discord application

- Create a Discord application and Bot in the Discord Developer Portal.
- Set its install type to **Guild Install**, with the `bot` and `applications.commands` scopes.
- Give it only View Channels, Send Messages, Embed Links, and Attach Files if/when artwork cards are added. No privileged message-content intent is required for slash commands.
- Invite it to the dedicated server. Save that server's numeric guild ID.
- Never give Kat's bot token to players, hard-code it in the repository, or request MafiaReturns login credentials.

## 3. Configure the project

Copy `config.example.toml` to `config.toml`. Fill in:

- `discord.guild_id`: dedicated Discord server ID.
- `discord.admin_user_ids`: Kat and trusted staff IDs (Discord user IDs, **not** roles).
- `event.starts_at_utc`: an explicit UTC timestamp (e.g. `2026-12-20T19:00:00+00:00` is only an example, not an agreed launch time).
- `event.season_key`: unique for each year/season.
- `storage.database_path`: writable persistent storage location.

Copy `.env.example` to `.env`; set `DISCORD_TOKEN` privately. The registration opening date is **automatically calculated** as start minus 168 hours; never shift it manually based on UK local time.

## 4. Install and start

Python 3.12 or newer is required. Create a virtual environment, `pip install -e ".[dev]"`, run `python -m pytest -q`, then `python bot.py`. The application registers slash commands only for the configured Discord guild. `config.toml` and `.env` are local/private files, not part of the ZIP.

## 5. First smoke test (foundation only)

1. Set a test kickoff timestamp within the next seven days, and launch the bot in a test dedicated guild.
2. Check `/snow dashboard` and `/snow rules`.
3. Register `TestPlayerA` as Chicago with `/snow join`; confirm it appears in `/snow profile` and `/snow cities`.
4. Try to claim `testplayera` using a different Discord user; expect an error.
5. As an allow-listed staff user, run `/snowadmin review` with an explicit reason and export registrations.
6. Verify that ordinary members cannot run staff commands.
7. Restart the process, and verify registrations persist and dashboard buttons still respond.
8. Check command behavior in a second guild; no commands should be registered there, and callbacks reject interactions with another guild ID.

**Not yet available:** PvP, quests, item crafting, boss, siege, score ledger, prizes, image templates, pause/resume, and finalisation. Do not start an advertised competitive event with this foundation build.

## 6. Production gates

- All P0 and P1 tickets closed and reviewed, including anti-abuse controls.
- Full seven-day synthetic replay, boundary tests, concurrent double-click tests, and database restore drill pass.
- Kat approves individual prizes, claims/appeals procedure, moderation rules, and exact event start.
- Staff-only exports tested; city leaderboard is never treated as a prize payout mechanism.
- Daily database backup and confidential handling of Discord IDs/MR names are in place.
- Change season settings only with an audit trail, freeze balance before the competition starts, and announce corrections openly.

## 7. Optional new GitHub repository

In the project folder (after you have made sure `.env`, `config.toml` and database files are ignored):

```powershell
git init
git branch -M main
git add .
git commit -m "Operation Snowfall starter foundation"
git remote add origin https://github.com/YOUR_USERNAME/Operation-Snowfall.git
git push -u origin main
```

Create the empty GitHub repository first. The scaffold has **not** been pushed or deployed anywhere by ChatGPT.
