# Operation Snowfall v0.1.6 — Kat / Staff Launch Checklist

## Technical checks (SNOW-028, 029, 030)

- [ ] Python 3.12/3.13 tests and Ruff lint green in GitHub Actions; `python -m pytest -q` locally green.
- [ ] `python bot.py --simulate` returns `ledger_ok: true`, 7 days and 42 city-day snapshots.
- [ ] Same application: host starts `/snowadmin test-start day:1 channel:#snowfall-testing confirmation:TEST`, can choose Days 1–7 and ends with `/snowadmin test-end confirmation:END_TEST archive:false`.
- [ ] All test commands, UI buttons, role restrictions, cooldowns, item caps and retry protection checked in the existing server’s TEST channel, including Day 1–7 bonuses and test-data deletion.
- [ ] SQLite backup made using `/snowadmin backup` (or `python bot.py --backup-now`); SHA256 sidecar verified and off-site copy arranged.
- [ ] Offline **restore drill** passed with a disposable copy. Do not test restoring over a running production database.
- [ ] Production Discord guild ID, bot application scopes and permissions confirmed (previous `403 Missing Access` must be resolved); bot has Attach Files in art channels.
- [ ] The *production* `#leaderboard` message is edited every five minutes without duplicate posts; announcements go to the intended channel and appear once per day.
- [ ] Production planned start UTC and seven-day preregistration verified; real season not started during practice.

## Community / rewards checks (SNOW-026, 027, 031)

- [ ] Kat agrees on official **individual** prize places and exact awards; city has **no monetary/perk payouts**.
- [ ] Kat confirms staff roster/user IDs, identity appeal routes, fair-play and refund/dispute wording.
- [ ] Staff posts privacy notice and an **explicit data-retention/deletion date** before registration.
- [ ] Staff runs `/snowadmin launch-check` and `/snowadmin reconcile` before kickoff, and posts rules.
- [ ] Kat records `/snowadmin approve-launch confirmation:APPROVE reason:<review details>`.
- [ ] At/after real UTC kickoff, Kat runs `/snowadmin start confirmation:START`.

## Seven-day finalisation and payouts

- [ ] Review flagged/disqualified accounts; `/snowadmin adjust-score` can correct points **before finalization** and stores an auditable ledger entry.
- [ ] Complete seven effective 24-hour days and review `/snowadmin reconcile` and final standings.
- [ ] Host runs `/snowadmin finalize confirmation:FINALIZE` after 168 effective hours.
- [ ] Host runs `/snowadmin export-prizes`, saving private individual CSV. The first export freezes rank snapshots; subsequent exports re-use them.
- [ ] Kat sets manual awards using `/snowadmin prize-status`; record **paid** only after real rewards are delivered.
- [ ] Keep prize exports restricted to staff and remove/retire data according to published retention schedule.

**Sign-off (manual, not automated):** Kat (MK) ______   Date/UTC ______   Staff witness ______
