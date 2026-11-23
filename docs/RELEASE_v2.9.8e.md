# v2.9.8e — Test Lab 2.0

## Implementation

Version 2.9.8e extends the isolated web staff Test Lab. Its temporary PracticeStore uses a separate SQLite database that cannot update the shared PostgreSQL season played via Discord and Underworld. No production scoring, prizes, migrations, player balances, event timing or Discord worker settings change.

### Scenario controls

- Select one of six fictional players. Adjust snowballs 0–12, warmth 0–100, armour 0–25, remaining throw cooldown 0–30 seconds, and today's Snow Don HP up to initial boss HP.
- Select normal random results, or force a hit/miss with the genuine CombatEngine and WorldEngine. Forced RNG is used only in the private Test Lab.
- Exercise any of five Social Arcade games (gallery, safe, snowman, catch, trivia) with perfect or incorrect answers, using the actual server-side sealed puzzles and move engine.
- Prepare and claim any daily mission (throws/rivals/community), using actual combat events and EconomyEngine. Check 20-point rewards and Day 3 theme bonus.
- Simulate a continuous seven-day event timeline on a fresh disposable PracticeStore. The report covers themes, actual PvP/boss/siege results, a mission claim and an arcade completion each day. The temporary simulated season is deleted immediately; any separately open staff rehearsal is preserved.
- Reset all disposable data belonging to the staff identity, including temporary sessions, comparisons, report history and seven-day simulation.
- Download complete test-only results from the browser as JSON.

### Accounting evidence

Each real-engine action records its reported awarded points and compares those against its actual temporary score_ledger delta; per-row difference and PASS/REVIEW are shown. Arcade game score is checked against the original server-side round deltas, while its official score ledger delta must be zero. These are *ledger-consistency* tests, not an independent mathematical reimplementation of the game balance.

### Safeguards

Only verified allowlisted Discord OAuth staff can use the web Test Lab; Underworld is required for gameplay but not staff login. Mutation requires session CSRF, same-origin validation and staff reason. Start, day reset, refill, week simulation, end and reset-all require a typed confirmation. Lab session IDs prevent stale-tab writes; request IDs are idempotent. Six staff labs maximum, idle timeout 90 minutes. No shared QA writes, no official awards or chat messages. The separate Discord bot test commands are unchanged and not operated remotely by this website.

### QA gates

Tests cover configuration bounds, forced combat outcomes, all five arcade modes, daily mission reward outcomes, seven-day simulation, reset all and replay, unauthorised access and shared database isolation. Playwright tests cover desktop, 390px mobile and 320px narrow mobile. Staff acceptance should verify the live admin UI against a disposable rehearsal before the v2.9.9 release freeze.
