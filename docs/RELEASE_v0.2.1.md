# Operation Snowfall — v0.2.1: UX & Menus

This release upgrades the existing private, single-message navigation without changing the approved Christmas event rules, combat RNG, rewards, city scoring, mystery gift payouts or database schema.

## What's new

- **Today**: a compact, phone-friendly daily hub with individual quest progress, claim-ready indicators, mystery present state, boss and fortress attempts, PvP points, and UTC Discord-relative regeneration/reset timers.
- **Do Next**: a state-aware, one-tap recommendation. It considers registration, pre-launch/paused/finished phases, KO recovery, claimable quests, unlocked gifts, available ammo, throw cooldown, first-time arena participation, remaining world actions and the PvP daily limit.
- **Live, non-mutating navigation**: Do Next re-reads the player's current season and only opens existing menus. It **does not** auto-join, enter arena, throw, claim, craft, spend Snowflakes, open gifts, or change scores. Those actions still require the original player confirmation and server-side checks.
- **Headquarters**: clearer arena eligibility window and recovery/shield timers, plus shortcuts to Today and Do Next.
- **Main Menu and Game Menus**: Today / Do Next accessible directly while preserving the existing Trophy, City, Winter, Help, Rankings, Admin and Test routes.
- **Responsive editing**: each route continues editing the current private ephemeral message, clearing previous artwork. Button row limits and per-user access checks remain in force.
- **Paused events**: no moving recovery or regeneration countdown displayed. Rehearsal sessions remain separate and old test views expire safely.

## Behaviour

Recommendation order when LIVE: recover from KO → claim a completed quest → open an unlocked gift → wait for ammo or cooldown → enter the arena if not active → Snow Don (if enabled and attempts/score remain) → City Siege → rival PvP → optional Winter Activities. Combat/economy engines remain authoritative and may deny an action whose eligibility changes after the menu opens.

Daily progress shows **attempt usage**, not invented rewards for exhausting all attempts. City standings remain honorary; only individual scores determine prizes.

## Developer checks

```bash
python -m pip install -e ".[dev]"
python -m compileall -q src bot.py
python -m ruff check src tests --select E4,E7,E9,F
python -m pytest -q
```

Run through a production-like Discord test day on mobile before publicly announcing the version: open `/snow menu`, use Today, Do Next, refresh after claiming a quest/opening a present, opt in to the arena, verify cooldown and pause behaviour, test navigation back to Home, and check that admin/test panels remain accessible only to configured hosts.

## Upgrade

Back up your SQLite database; stop the existing bot; `git pull origin main`; install dependencies as above; restart with `python bot.py`. No data migration is required (schema version 8).

## Scope

This is a navigation/read-model release, not the later v0.2.2 cosmetics or v0.2.3 combat overhaul. Live Discord gateway behavior and permissions should still be checked at deployment.
