# Operation Snowfall v0.2.7 — Winter Arcade & Social Games

This release introduces **five genuinely playable, stateful mini-games**, not
static menu text. Every move is confirmed server-side, saved in SQLite and
visible within the existing private, single-message Discord navigation.

## Five playable games

| Game | Rounds | Mechanic | Maximum |
|---|---:|---|---:|
| 🎯 Snowball Target Gallery | 5 | Pick the called-out target from three changing objects | 100 |
| 🔐 Frozen Safecracker | 3 | Decode three different arithmetic/logic icy dial clues | 100 |
| ☃️ Snowman Builder | 4 | Match parts to the seasonal blueprint | 100 |
| ❄️ Snowflake Catch | 5 | Predict a snowflake's landing lane from start and wind; edges wrap | 100 |
| 🎄 Christmas Trivia | 5 | Random five-question multiple-choice festive quiz, with explanations | 100 |

Original clue/question banks are shuffled at the start of each game, then
**persisted unchanged**. The answer key is never passed to a Discord control
or revealed in its prompt before the player's choice. It is revealed only
after committing that turn; the next round then appears.

A successful move scores 20 arcade points in Target Gallery, Snowflake Catch
and Trivia, 25 in Snowman Builder, or 30 in Safecracker. A perfect three-digit
Safecracker adds a 10-point completion bonus. Each game is capped at 100.

**None of these arcade points are official Operation Snowfall points.**

## Fair play, personal records and friendly competitions

- **Three starts per game per event day** (15 possible new game starts daily).
  Switching menus, interrupting a game or restarting the bot does **not**
  consume another run: the game resumes from its saved round.
- Players keep **personal bests**, number of completed games and currently
  active sessions. Record boards are available for **today** or the full
  **season**, and show each eligible player's **best completed attempt**.
- The **City Cup** is a secondary, honorary team display: sum of the best
  completed arcade scores per player and game in each city. City totals
  cannot change territory control, paid city honours or prize qualification.
- Player names are displayed as registered in MafiaReturns and escaped to
  prevent unwanted Discord mentions. Flagged or disqualified players are
  excluded from public-style casual rankings and cannot take new actions.
- The arcade requires **zero snowballs, zero Snowflakes and no consumable
  item**. Knocked-out or temporarily protected players can still play
  these casual games during a live event day.

## Cosmetic-only seasonal collection

A dedicated **Winter Arcade Passport** features 11 non-tradeable decorative
stamps: one participation ticket per game (5), one perfect-score mastery
ribbon per game (5), and the **Winter Arcade Grand Tour** badge after
completing all five games at least once.

These are stored as *display records*, never added to shop inventory,
official player titles, score ledgers, coin wallets, paid-prize claims or
combat buffs. Your unlocked stamp count also appears on the player's
illustrated collector card.

## Discord navigation

- `/snowfun arcade` opens the five-game arcade lobby with its record board.
- **Game Menus → Winter Arcade**, **Winter Activities → Winter Arcade**, and
  **Today → Winter Arcade** also navigate to it.
- Selecting a game starts or resumes a run. Three reply buttons per round
  make it easy to play on mobile. The server then updates the **same private
  message** with the result and next question.
- **My Passport**, **High Scores**, **City Cup**, **Today's Best** and
  **Season Best** are reachable from the arcade buttons.
- The existing three training minigames (Target Practice, Blizzard Dodge
  and Boss Drill) remain available through **Winter Activities →
  Arcade Modes**; their costs, caps and specialist equipment are unchanged.
- When a player has **no snowballs** or is **recovering from a knockout**,
  Do Next now directs them to the full Winter Arcade.

All five game screens, passport and rankings have 960×540 illustrated
Pillow cards using the existing city artwork. Discord edit/follow-up
methods automatically provide accessible text if graphics fail.

## Data integrity and migration

**SQLite schema v10** introduces three independently scoped tables:
`social_arcade_runs`, `social_arcade_turns` and
`social_arcade_stamps`. A new run saves the randomly drawn puzzle sequence,
player, season, day, mode and numbered attempt. Its current step and total
are persisted. A unique *active run* constraint and the three-attempt
cap are enforced inside `BEGIN IMMEDIATE` SQLite transactions.

Each move includes the Discord interaction ID and the exact current round.
Duplicate callbacks return the saved result without awarding a second score.
Stale buttons cannot advance a game; submitting a different choice with
an existing interaction ID is rejected. Narrative moves and awarded stamps
cannot be updated or deleted. Completed runs cannot be altered.

The change is isolated from combat, world, season prizes, existing arcade
training, quests, equipment, Snowflakes and the historic v0.2.6 mystery
casebook. **No new paid prizes or additional official points are possible.**

The event day follows the authoritative pause-adjusted clock. Pauses disable
new actions; rollover disables old-day games and permits new daily starts.
Practice Manager sessions use their isolated disposable test database.

## Upgrade and verification

Back up the current SQLite database before the first v0.2.7 launch (schema
v9 → v10 is forward-only). Stop the bot, then in the PyCharm terminal:

```powershell
git checkout main
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

In Kat's Test Centre, finish each of the five games, verify one 100-point
arcade result and its mastery stamp, check the Grand Tour and passport,
restart mid-game, try a double-click, complete three attempts in one day,
switch to the next day, and verify flagged players are removed from the
honorary scoreboards. Check both the original training modes and the
illustrated collector card. Confirm that the official scoreboard and
prize exports remain unchanged.
