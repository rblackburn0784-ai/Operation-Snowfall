# Operation Snowfall v0.2.3 — Snowball Combat 2.0

**Release scope: presentation, combat intelligence and practice-only demonstrations.** No changes to official hit chances, attack damage, combat RNG, shield and KO durations, attack costs, daily and per-pair limits, the scoring ledger or prize allocations.

## New in v0.2.3

### Illustrated combat recaps
- Real throws still use `CombatEngine.throw`. After it commits, the bot reads the immutable combat history and draws an expanded **960×540 broadcast-style** result card, with a headline, shot effect, current/best scored-hit streak and the scored-hit record against that rival.
- New 1930s winter commentary varies reproducibly by the **saved interaction ID**, without consuming extra combat RNG calls. An earned retaliation displays a **REVENGE LANDED** ribbon. Critical/KO GIFs incorporate the enhanced card where possible; image errors still fall back to the authoritative textual result.
- A repeated Discord interaction is clearly described as an existing recorded throw, not a second expenditure or point award. No score or fairness engine changes.

### Private Rivalry Dossier and revenge alerts
- `/snowfun rivalries` (and **Rivalry Dossier** inside Game Menus, combat menus or My Player) shows personal rivals, scored hits exchanged, throw accuracy, knockouts, scored-hit streaks, best streaks, retaliation records and pending revenge opportunities.
- Alerts come from **existing** season-scoped, immutable `combat_events`: a rival owes you a response when they last scored on you and you haven't subsequently landed a scored return hit. A retaliation does not itself award bonus points.
- Open **Today** to see outstanding private revenge notifications. These are **private in-app notices**, not unsolicited Discord DMs or public callouts.
- The model is read-only. No extra table, no replay-sensitive counter, no notifications written to score tables.

### Intelligent Target Finder
- **Recommended Rival** now prioritizes eligible rivals with outstanding revenge opportunities, followed by new scoring opportunities and warmth. **Revenge Rival** chooses an eligible outstanding rival; **Low Warmth** finds the weakest eligible rival. **Surprise Me** remains random.
- The **Rivalry Dossier** and **Refresh Targets** buttons work within one ephemeral message.
- The target finder only sorts the **up to 25 targets returned by the authoritative engine**; it does not create an additional way to attack protected, inactive or same-city players. The engine revalidates the selected target when the throw is confirmed.
- After a throw, **Rematch Preview** returns you to the throw-style menu. It does not auto-attack or bypass cooldown, KO, anti-camping shield, 2-hit cap or 300-point PvP cap.

### Experimental tactics in the isolated Test Centre
- **Tactics Lab** appears inside a target's throw menu **only during an isolated practice day**.
- **Feint Drill** demonstrates a hypothetical +10 percentage-point standard-throw accuracy; **Defensive Stance** demonstrates a hypothetical 2-point reduction in incoming warmth damage. Both are visual simulations using local random examples and no database writes.
- These moves **do not exist in official live combat**, cost no snowballs, do not invoke the guard system, and cannot affect PvP scores or prizes. The existing real guard and mittens remain unchanged.

## Compatibility, safety and performance
- Version: **0.2.3**. SQLite schema remains **version 8**. No migration or data backfill is required.
- Existing `/snow` has Discord's maximum of 25 commands; to preserve those commands, the new slash command is **`/snowfun rivalries`**, not `/snow rivalries`.
- Personal names are rendered safely and Discord mentions are disabled. Rivalry records are not posted publicly.
- Statistics are derived from season-scoped immutable combat events and may include events against accounts subsequently reviewed or disqualified; no extra official scores are created.
- Practice sessions remain channel-scoped and discarded independently of production. After a season ends, historical private rivalries can still be viewed.

## Deployment and verification
1. Back up the SQLite file; stop the bot.
2. `git checkout main` and `git pull origin main`.
3. `python -m pip install -e ".[dev]"`, `python -m compileall -q src bot.py`, `python -m ruff check src tests --select E4,E7,E9,F`, `python -m pytest -q`.
4. Restart with `python bot.py`.
5. In Kat's **Test Centre**, test a hit, miss, critical, KO, repeat request, anti-camping shield, revenge display and both hypothetical drills. Verify official PvP scoring is unchanged and no duplicate messages accumulate. Then check the private `/snowfun rivalries` command in Discord on mobile.

Automated CI runs on Ubuntu 3.12/3.13 and Windows 3.13. Live Discord gateway checks remain a recommended final deployment step.
