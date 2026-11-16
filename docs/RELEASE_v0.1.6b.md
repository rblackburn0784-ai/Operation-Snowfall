# Operation Snowfall v0.1.6b — Main Menu, Game Menus and Admin/Test Panel

**One Discord application, one server and one token.** This release adds a
consistent, private button-driven navigation flow without changing any combat,
scoring, item probabilities, live season dates, prize rules, or database schema.

## Player navigation

- `/snow menu` opens the new **Main Menu**. `/snow dashboard` opens the same menu.
- The existing **public permanent dashboard** retains its established Join,
  Profile, Throw, Inventory, Quests, Snow Don, Siege, Podium and Cities shortcuts,
  and adds **Main Menu**. Old dashboard button IDs remain unchanged.
- **Main Menu → Game Menus** opens Snowball Fight, Inventory & Craft, Daily Quests,
  Snow Don / City Siege and Rankings.
- **Main Menu → My Player** opens registration, illustrated profile, `/snow ready`
  entry and rules.
- **Main Menu → Rankings** opens live individual standings, honorary city
  standings and illustrated individual podium.
- Each deeper fight, crafting, quest or boss/fortress view now includes
  **◀ Game Menus** and **🏠 Home**, including confirmation/result views.
- Menus are **ephemeral and owner-checked**. Buttons replace the same private
  response; navigation clears old attachments. Existing game result cards and
  animations still work. Player actions are *not* automatically executed by
  merely opening a menu.

## Host-only Admin / Test Control Panel

- `/snowadmin panel` opens the private host control panel. The **Admin / Test**
  button also appears on the Main Menu **only** for configured host user IDs.
- **Live Status** reads the official season. **Launch Checks** reads database,
  backup, approval and ledger integrity; it does not approve or start an event.
- **Broadcasts** can manually update the existing public leaderboard or
  current-day announcement **after confirmation**, and always use live data.
- **Test Centre** includes Start Day, Switch Day, Test Status, Stop & Delete,
  Stop & Archive, Back and Home. Start/switch offers a dropdown for Days 1–7,
  then requires a separate confirmation click.
- To start a practice session from the panel, open it **inside the intended
  test channel** (for example `#snowfall-testing`). The test manager refuses
  use of the configured `#leaderboard` / `#Announcements` channels and refuses
  practice after the official event has started.
- **The Test Centre uses a disposable, season-pinned SQLite database.**
  Switch resets the previous practice day's game state while retaining test
  registrations; Stop deletes the database or archives a verified copy. Old
  test UI is rejected after switch/end. Production scores and prizes remain
  untouched. The Discord bot stays running.
- Riskier production changes—launch approval, start, pause/resume, finalize,
  score correction and payout recording—retain their existing typed-confirmation
  and audit-backed slash commands. The host panel does not bypass those checks.

## Setup and commands

Stop the bot, back up `data/snowfall.sqlite3`, then:

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

In Discord:

```text
/snow menu
/snowadmin panel
```

If slash commands need re-syncing, make sure the bot has been installed in the
configured server with `bot` and `applications.commands` scopes and the proper
channel permissions. No new application, token, event channel IDs or migration
are needed for this release.

## Verification and limitations

- Tests cover menu construction, player and host access restrictions, Discord
  component limits, nested navigation, confirmation-based start/switch/end,
  revoked test buttons, archive, and read-only live-season isolation.
- Existing separate `/snowadmin test-start`, `test-day`, `test-status`,
  `test-end` and `test-stop` commands are retained.
- **Production Discord gateway interaction testing is still required** in the
  actual event server. Automated tests do not confirm live server permissions.

## Windows SQLite lock fix (16 November 2026)

- Practice **Stop & Archive** explicitly closes both SQLite backup connections before
  deleting the disposable database (fixes WinError 32 on Windows / Python 3.13).
- The restore regression test now explicitly closes its SQLite checkpoint connection,
  rather than relying on transaction context-manager cleanup (fixes WinError 5).
- Offline restore reports a descriptive error if a destination is still locked;
  it never silently overwrites an open database.
- GitHub Actions now runs Python 3.13 tests on Windows as well as Python 3.12/3.13
  on Linux, with dedicated regression coverage for connection cleanup.
- No event dates, commands, production data or database schema are changed.
