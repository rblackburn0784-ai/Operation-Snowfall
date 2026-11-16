# ❄️ Operation Snowfall v0.1.2 — Snowball Combat

**Scope:** Milestone B / SNOW-009 through SNOW-013, built on v0.1.1 Foundation. Python 3.12+ (including PyCharm 3.13).

## Implemented

- **SNOW-009 · Resource clock:** per-player lazy snowball and warmth regeneration, event-start vs late-join seeding, 12/100 caps, 20-minute ticks, no banking at caps, pause-aware effective clock, KO recovery and effective-end clamping.
- **SNOW-010 · Transactional combat:** secure server-side hit + crit rolls; three balanced attack styles; 30s cooldown; one-snowball consumption; `BEGIN IMMEDIATE` SQLite locking; idempotent `interaction.id` retries; no negative ammo, self-hits or friendly fire.
- **SNOW-011 · Safe targeting:** `/snow ready` opt-in for 36 effective hours (zero score), target menu with rival city, inactivity/KO/shield guards, 2 scored hits per pair/day, 3-incoming-hits/30m shield that renews only on 3 new hits, 30m KO recovery to >=50 warmth, expiry of defence armour where applicable.
- **SNOW-012 · Ledger:** insert-only `combat_events` and `score_ledger` with SQLite update/delete refusal triggers; hit and crit RNG evidence; 300-point combined daily PvP/defence cap; +5 first rival city, +10 KO up to 3 per day, +2 on fortified defences, +1 Snowflake per scoring hit; individual board with distinct-rival / earliest-score tie break; disqualification filtering without deleting history.
- **SNOW-013 · Discord menus:** `/snow throw`, `/snow targets`, `/snow ready`, `/snow leaderboard`, improved `/snow profile`, persistent Throw dashboard button; private target selection → attack stance preview → explicit confirmation → text result with retry, avoiding channel spam. Slash and button paths invoke one domain engine.

## Database migration

- **Schema 3** adds `player_resources`, `combat_events`, `score_ledger`, indexes and immutable history triggers; preserves version 1/2 registrations, review states and lifecycle/audit tables.
- New preregistered player resources seed when the host starts; late registrations seed at the paused/live effective time of joining. Reboots do not reset resources, score, cooldown or KO/shield state.
- The ledger is designed for future compensating entries instead of destructive corrections; operators should back up before upgrading.

## Balance and gameplay policy

| Throw | Chance | Damage | Hit points |
|---|---:|---:|---:|
| Quick | 75% | 8 | 8 |
| Standard | 60% | 14 | 12 |
| Power | 40% | 22 | 18 |

- A critical hit has 10% probability after a successful hit, +4 damage, +3 points.
- PvP cap 300 points/day includes attacker/defence bonuses. Scoreless practice attacks are **off** for v0.1.2 (prevents griefing).
- `/snow ready` is a zero-score explicit opt-in needed to bootstrap combat when boss/quest scored actions are unavailable; it makes a player targetable for 36 effective hours. It does not change registration or rewards.
- Fort armour is honoured and can expire, but **crafting and guard items are not available yet** (SNOW-014).
- City rankings, PvE boss, sieges, quests, image rendering and prize payouts are **not** included in v0.1.2.

## Update an existing PyCharm installation

1. Back up SQLite with a consistent database backup before upgrading; stop the bot during the upgrade.
2. `git pull origin main` (or overwrite project files using the release ZIP). **Keep** your local `.env`, `config.toml`, database and any uncommitted work.
3. `python -m pip install -e ".[dev]"`
4. `python -m pytest -q` and `python -m compileall -q src bot.py`
5. `python bot.py` and verify `/snowadmin status`, `/snow profile`, `/snow ready`, `/snow targets`, `/snow throw` in the **dedicated event Discord**.
6. Only use a separate test season to try host START/PAUSE/RESUME before the public event.

## Acceptance and remaining work

- Locally tested with deterministic unit/integration checks for migration, hit/crit/cap, concurrent spends, idempotent requests, KO/shield, last-scored activity, pauses and end boundary. CI runs for 3.12 and 3.13 on GitHub.
- A real Discord server smoke test (slash command options, ephemeral edits, permission handling and persistent button after restart) must be done before relying on this release publicly.
- **Next:** v0.1.3 Economy (SNOW-014–016), including crafting, guard, daily quests and daily present rewards.
