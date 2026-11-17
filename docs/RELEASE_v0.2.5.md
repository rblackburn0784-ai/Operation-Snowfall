# Operation Snowfall v0.2.5 — City Wars & Territory Control

**Honorary team play only.** This update introduces a six-city interactive
Discord war map, fictional district control, rivalry challenges, city banners,
daily team missions and cross-city statistics. **Official individual leaderboards,
score caps, paid prize allocations, Snowflakes, player combat rules and boss
rewards are entirely unchanged.**

## Access and navigation

- `/snowfun territory` is the new private map command. The original `/snow`
  slash-command group already uses Discord's 25-command maximum.
- **Game Menus → City Wars Map** and **City Headquarters → Territory Map**
  lead to the same owner-checked, one-message view.
- Two dropdowns make the **960×540 schematic six-city map interactive**:
  choose any of the six cities to inspect its banner and territory, or select
  the current/previous event day to inspect a historical battle.
- Buttons open **Territory Map, Daily Matchups, My City, City Missions, City
  Banners, Rivalry Statistics, City HQ, Refresh, Game Menus and Home**. All
  views edit the *same private message*, clearing previous images to prevent
  Discord chat clutter. Artwork is optional: accessible text is always
  provided if graphics cannot be attached.
- Today's dashboard also identifies the player's assigned rival city and
  current team contribution.
- The map is an **original stylized schematic, not a geographic road map**.

## Six-city banners

Each MafiaReturns city receives an original named home district, colour,
emblem and 1930s winter-themed team banner:

| City | Home district | Banner identity |
|---|---|---|
| Chicago | The Loop | Gutter Saints |
| New York | Midnight Manhattan | Empire Frost |
| Detroit | Motor Yard | Steel Snow |
| Philadelphia | Liberty Square | Liberty Blizzard |
| Las Vegas | Neon Boulevard | Neon Icicles |
| Los Angeles | Sunset District | West Coast Whiteout |

These are fictional event territories and decorative banners, not real claims
of administrative ownership. No purchasing, manual claiming or currency
deduction is needed.

## Districts and daily territory control

Each day has **12 honorary districts**:

1. **Six home strongholds**, one per city: a city temporarily controls its
   home district when its existing v0.1.9 daily co-operative mission has been
   completed for that event day.
2. **Three Rally Frontiers**, one per daily city match: the side with the
   higher *rally marks* controls the named frontier. Rally marks are:
   **4 × distinct eligible daily scorers + 1 × real non-echo successful
   boss/siege hit + 1 × genuine quest claimed + 3 if the existing daily city
   co-operative mission is complete**.
3. **Three Duel Frontiers**, one per match: the side with more **scored
   cross-city PvP hits against that day's assigned opponent** controls the
   district. Misses and hits without awarded score do not count.

**Ties, including 0–0, are always neutral.** No automatic tie-breakers
award empty districts. All six cities receive exactly one daily opponent
in each of three matches. Days 1–5 rotate across every distinct city pairing
exactly once; days 6 and 7 repeat the first two rounds as rematches.

All district control is recalculated from the **existing season- and
day-scoped immutable combat, PvE, quest and score ledgers**, excluding
flagged/disqualified contributors in the war calculations. History survives
restarts and cannot be manually modified through the map. A staff review
can change honorary historical control; these displays are review-adjusted,
not separately locked prize results.

## Daily rivalry challenges and co-operative operations

Every eligible city receives three **display-only** missions:

- **Rally the Crew:** have different members score legitimate individual
  points on the current day. Target scales to 1–3 members, capped by
  the current eligible registered city population.
- **Rival City Ambush:** land two genuine scoring PvP hits collectively on
  the city's daily assigned rival. Normal PvP target protections, cooldowns,
  per-target hit limits, 300-point daily cap and real player registration
  still apply.
- **Local City Mission:** complete the existing daily co-operative mission
  (Opening Salvo, Fortress Breakers, Whiteout Ambush, Supply Run, Don's
  Downfall, Blizzard Brigade or Final Push), under the existing rules.

Mission completion and earned territory **do not** insert into
`score_ledger`, grant Snowflakes/items, consume extra ammunition, affect
official city standings, or produce prize awards.

## Six-city rivalry statistics

Players can inspect real season-to-date city-versus-city throws, hits,
warmth/armour damage, knockouts, incoming hits and incoming knockouts.
Daily matchups additionally display both city's actual rally marks and
qualifying scored-hit counts. No access to another individual player's
private profile or identity verification records is required.

## Integrity, compatibility and deployment

- **Version:** 0.2.5. **SQLite schema remains version 8**; no migration.
- **No writes** in the territory calculation or map/button renderers. Original
  scoring systems remain the source of truth; no extra prizes, rankings
  or winner exports.
- All queries are parameterized and scoped to season + event day, using
  the existing pause-adjusted clock. Future days cannot be inspected early.
  Closed seasons allow read-only inspection of event days 1–7.
- Controls use the existing owner/guild checks and practice-day isolation.
  Names are escaped, and unsolicited public pings are disabled.

### Update in PyCharm

Back up the SQLite database and stop the bot, then:

```powershell
git checkout main
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

**Test Day smoke test:** Have members of Chicago and Los Angeles join and
make legal throws. Verify both city's banners, the rotating opponent map,
neutral ties, co-op home-district claim, duel-control changes, daily
rollover and a staff review; verify that the personal scoreboard, ammo,
Snowflake balance and prize exports are unchanged. Check both dropdowns
and single-message image replacement on mobile.
