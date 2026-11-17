# Operation Snowfall v0.2.4 — Snow Don Boss Evolution

v0.2.4 deepens the existing Abominable Snow Don fight, using the ten existing
transparent damage portraits and immutable shared-boss battle records. **No new
boss HP, hit probability, damage, attempt cap, personal score, PvP score, clear
bonus, city prize or other competitive rule is introduced.**

## Snow Don personality and phases

- The existing **75%**, **50%** and **25%** HP announcements now have stronger
  1930s winter mobster narratives. The announcement publisher keeps its
  season/day/phase keys in the persisted `published_messages` table so restarts
  do not produce duplicates. When the boss is defeated before the next
  scheduler tick, the single defeat notice takes precedence over any outstanding
  phase announcements.
- Every real Snow Don attack has additional deterministic banter for a hit,
  miss, training echo or final blow. The line is selected from the already
  saved Discord interaction ID, not the combat RNG. It cannot change gameplay.
- When a real attack crosses an HP milestone, an original **nine-frame**
  damaged-portrait transition animates from the pre-hit damage stage to the
  newly injured one. Crossing multiple thresholds in one attack is shown in
  the textual result; no extra score is generated.
- Ten original 100%–10% Snow Don portraits continue to be selected by the
  authoritative remaining shared HP, not simulated damage.

## Co-operative raid features

Use **Game Menus → Snow Don Raid**, **World Battles → Raid Headquarters** or
`/snowfun raid`. The original `/snow` group is already full (25 subcommands).

- **Raid Overview:** current shared HP, percentage progress, unique real
  contributors, shared hits, damage, milestone ladder at 25/50/75/100%, and your
  real shared-hit record.
- **Top Raiders:** up to eight named raiders ranked by actual non-echo shared
  damage, with an illustrated top-four card.
- **City Crews:** real shared damage and unique contributors grouped by city.
  All cities remain one co-operative raid alliance; city prizes are unchanged.
- **Co-op Goals:** visual achievements for three contributing players,
  two participating cities, 100 genuine shared HP damage and final defeat.
  These goals provide *recognition only*. They do not write any points, award
  snowflakes or create inventory items.
- **Attack Snow Don** still opens the original confirmation screen and
  `WorldEngine.attack` transaction. Boss attacks still use one regular
  snowball, the same shared 30-second cooldown and six attempts/day.
- Training echoes after the boss falls remain eligible for their normal
  individual points, but are separated from *real shared HP damage* and
  do not earn additional raid honours or clearing rewards.

All raid data is calculated from the existing season/day-scoped immutable
`pve_events`, `world_days` and `players` tables. The entire raid read
model is reconstructed on demand and survives restarts. There is **no
database migration**: schema version remains 8.

## Cinematic final defeat

- A genuine **first final blow** plays a new **16-frame 480×270 Snow Don
  cinematic** with the pre-final and defeated damage portraits, icy shockwave,
  flying snow and a gold victory banner.
- The private **Victory Replay** button reconstructs the stored unique final
  blow and replays its animation without invoking `WorldEngine.attack`,
  recording an additional score or spending ammunition.
- The existing standard static PNG and text fallbacks remain in place if
  generation or upload fails. GIF output is capped at four megabytes.
- One public defeat announcement/day is retained. Once the final blow has
  actually occurred, the announcement includes the historical raid's
  contributor count, shared damage, city participation and final-hitter
  credit. Restart recovery and deduplication remain unchanged.

## Player fairness / operational constraints

Official boss scaling, the 65% PvE hit probability, random damage, one-time
contributor clear bonuses, 50-point daily boss cap, six-attempt limit and
late-player echo policy **remain exactly as in v0.2.3**. Cosmetic raid goals
never affect the formal score ledger or prize exports. The raid menus are
private and owner-checked; no new publicly pinging notifications are added.

If the boss has been disabled by Kat, Raid HQ displays a disabled state and
no final replay can be unlocked. The existing Test Centre uses its isolated
store with the same feature set.

## Update and test

Back up the current SQLite file, stop the bot, then:

```powershell
git checkout main
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python bot.py
```

In an isolated test day, check phase thresholds, boss damage-stage portrait
selection, raid participation from multiple cities, defeat and contributor
bonuses, late echoes, public one-time announcements, **Victory Replay**,
paused-day restrictions and no duplicate prizes. GitHub CI runs compile,
Ruff fatal lint and full tests on Ubuntu Python 3.12/3.13 and Windows 3.13.
Live Discord gateway and mobile presentation should still be smoke-tested
before the event.
