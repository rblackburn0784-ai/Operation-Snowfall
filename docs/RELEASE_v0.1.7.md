# Operation Snowfall v0.1.7 — Player Experience Upgrade

One Discord application, existing server and existing isolated Day 1–7 test channel.
No new database schema, permissions, scoring rules or MR prizes.

## New commands and navigation

- `/snow hq` — private **My Headquarters** with personalised city and account, rank when within the top 100 scoring players, today/season points, snowballs, warmth, snowflakes, fort armour, quest progress and claim status, daily present availability, today's boss/siege attempts, and a recommended next action.
- `/snow guide` — private three-step onboarding: declare your own MR username and city; enter the arena with `/snow ready` and challenge rival cities; then complete quests, claim gifts, and fight boss/siege. City selection goes through the existing self-declaration modal, without any bypass.
- Buttons for **My Headquarters** in the persistent public dashboard and Main Menu / Game Menus / My Player; a **Guided Start** button in My Player and on Headquarters; Home / Game Menus navigation preserved.
- **Find a Fight**: existing target select menu now also offers a Recommended Rival (legal targets with more remaining scoring hits, then higher current warmth) and a random Surprise Me choice. Both refresh eligibility before choosing and never spend snowballs until the player confirms an ordinary throw. Ineligible opponents, anti-camping shield, KO protection, same-city restrictions, 36-hour activity and two scoring hits per rival remain enforced in CombatEngine.

## Timer accuracy

- Snowball and warmth generation: the current 20-minute lazy-regeneration schedule from CombatEngine.snapshot, not guessed timestamps.
- Throw: existing shared 30-second cooldown from last_throw_at.
- Event-day reset: anchored to `Season.started_at` and each full 24-hour effective day (not midnight); converted to Discord relative timestamps.
- While PAUSED, no false countdowns: effective-clock timers are explicitly frozen.
- Unregistered accounts see a clear welcome state with no invented scores, items or ranks. Before kickoff, no fake countdowns or actionable PvE attempts are displayed.
- Rank is exact within the existing canonical top-100 leaderboard; otherwise shows unranked/outside top 100 rather than inventing a position.

## Testing

1. Stop the bot and back up `data/snowfall.sqlite3`.
2. From PyCharm: `git pull origin main` then `python -m pip install -e ".[dev]"` and `python -m pytest -q`.
3. Restart with `python bot.py`.
4. In the existing dedicated server run `/snow guide`, `/snow hq`, and `/snow menu` → My Headquarters.
5. In `#snowfall-testing`, run a disposable Day 1 session from `/snowadmin panel`; register a second test player in another city, choose `/snow ready`, use Find a Fight → Surprise Me / Recommended Rival, then verify quest status, timers and reset/stop.

The experience service is covered by deterministic pure-Python tests for live and paused clocks, zero-point rank, gifts, Day 4, pre-registration and unregistered players. Discord-only UI contracts run on GitHub Actions for Python 3.12/3.13 and Windows Python 3.13. Live guild interaction/permissions and Kat sign-off still require a hands-on dry run.
