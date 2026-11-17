# Operation Snowfall v0.2.6 — Christmas Mysteries & Secret Encounters

**Seven fully playable daily detective cases**, with illustrated evidence boards,
three clues, three suspects, a private deduction, a concealed encounter and
an automatically maintained seven-day casebook.

The story is 1930s Christmas/noir, set across the existing six-city
MafiaReturns winter event. These are fictional event investigations, not
mechanics that change the official competition.

## Seven cases

| Event day | Detective mystery |
|---|---|
| 1 | The Vanishing Christmas Ledger |
| 2 | The Ghost Train at Midnight |
| 3 | The Ice Vault Job |
| 4 | The Missing Sleigh Bell |
| 5 | Who Stole the Snow Don's Hat? |
| 6 | The Blizzard Telegram |
| 7 | The Last Gift of Snowfall |

Each case has three separate inspectable leads, three possible suspects and a
storytelling conclusion. Once two leads have been examined, the player may
make a deduction. Each person is allowed at most **two distinct incorrect
or successful accusations per day**; replaying a previous wrong accusation
does not consume another attempt. Correctly solving a case is recognised
in their private casebook, with no prize impact.

## Hidden encounters

Each day also contains a secret vignette. To unlock it, players must
**inspect at least two of the current case's clues** and **either** take
a legitimate scored daily action **or** complete their existing standard
daily surprise encounter. This alternate free path ensures a player can
discover secrets even when PvP targets are unavailable.

The secret itself is a deterministic daily scene variant, derived from the
season, registered user and game day. Players choose to **follow, assist or
listen**. Their choice creates one permanent, non-tradeable **casebook
souvenir** for that day. A repeated click or a second choice cannot grant
a second item. Souvenirs are only story records, not inventory items or
shop cosmetics, so they cannot affect gear, score or paid prizes.

Players can revisit the seven-day **My Casebook** to view examined clues,
solved cases, used guesses and unique secret souvenirs. After the event
closes, it remains readable even though new actions are disabled.

## Discord experience

- `/snowfun mystery` opens a new private detective desk (the `/snow`
  command group is already at Discord's 25-command limit).
- **Game Menus → Mystery Casebook** and **Winter Activities → Mystery Casebook**
  reach the same system.
- **Case File**, **Inspect Evidence**, **Name Suspect**, **Secret Encounter**,
  **My Casebook**, **Winter Activities**, **Game Menus** and **Home** all
  operate within the existing owner-checked one-message navigation pattern.
- Illustrations include a 960×540 sealed-evidence corkboard, casebook roster
  and secret-encounter postcard. Plain text remains available if image
  generation or attachment fails. No AI image generation or network calls are
  needed at runtime.
- The **Today** panel includes the current mystery title, clue progress,
  solved status and secret discovery notifications (private only).

## Persistence, security and scoring fairness

**SQLite schema v9 migration.** The three new tables are:
`mystery_clues`, `mystery_guesses`, `mystery_secrets`. Each is
season-, user- and day-scoped, keyed by the original Discord interaction ID,
with unique per-day clue and secret constraints, and immutable update/delete
triggers. SQLite's `BEGIN IMMEDIATE` serialises overlapping clicks.
The migration runs automatically and idempotently on bot startup; there is
no deletion or rewriting of historical v1–v8 data.

The mystery engine writes only to these three tables. It **never calls the
combat, world or economy scoring actions**, changes ammunition, deducts
Snowflakes, opens paid gift boxes, creates official leaderboard entries,
changes prize payouts, or grants additional event bonuses. Official quests
and the existing surprise-encounter system continue unchanged.

The current event day follows the host's authoritative clock, respects
pauses and remains isolated from Practice Manager test days. Future cases
are not interactable before their day. Flagged or disqualified identities
cannot act. Suspect solutions are not shown before a successful deduction,
and unrelated players cannot use another person's interactive controls.

## Deployment

**Back up the live SQLite file before the first v0.2.6 launch**, because
the upgrade from schema v8 to v9 is forward-only. Stop the bot, then in
PyCharm terminal:

```powershell
git checkout main
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

In the isolated Test Centre: inspect two leads, guess incorrectly, guess
correctly, claim the ordinary encounter, uncover the secret vignette,
check one-time souvenir persistence after restarting, then switch days.
Verify the old individual leaderboard and prize export remain untouched.
Check the private menus on Discord desktop and mobile.
