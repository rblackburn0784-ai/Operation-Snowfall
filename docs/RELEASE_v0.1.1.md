# Operation Snowfall v0.1.1 — Milestone A release notes

## Completed scope

- **SNOW-001:** pip editable Python package v0.1.1; 3.12/3.13 CI, compile, fatal-error lint, pytest.
- **SNOW-002:** dedicated-server checks for slash commands and persistent views; env-only token; host user allow-list plus optional staff roles.
- **SNOW-003:** UTC planned kickoff and 168-hour preregistration; actual host start, effective 168-hour play, pause/resume/finalize time persisted across restarts.
- **SNOW-004:** SQLite version-2 additive migration preserving starter records, WAL, transactional admin writes, `quick_check`.
- **SNOW-005:** six-city self-declared registration, transaction-checked open window, per-season Discord/MR identity uniqueness, idempotent retry.
- **SNOW-006:** staff review with required reason, old/new audit state, no points mutation or approval queue.
- **SNOW-007:** public welcome and rules, single re-editable published dashboard, persistent buttons with private responses.
- **SNOW-008:** host-only schedule setup/start/pause/resume/finalize; explicit confirmation strings and audit trails.

## Deploy / update

1. **Back up** any existing SQLite database before first v0.1.1 launch.
2. `git pull` into PyCharm (or extract the released ZIP over the project, preserving your local `.env`, `config.toml`, and database).
3. In PyCharm's venv run `python -m pip install -e ".[dev]"` and `python -m pytest -q`.
4. Copy missing config fields from `config.example.toml` (especially `staff_role_ids`); fill at least one `admin_user_ids` host ID.
5. `python bot.py` and test `/snowadmin status` in the **dedicated event Discord**.
6. Host runs `/snowadmin publish-dashboard` in the selected channel, then manually pins the message.
7. **Do not press START on the live event ahead of kickoff.** The season remains READY until a host starts it.

## Behaviour / limitations

- A configuration start date is seeded only once per `season_key`; subsequent host setup changes live in SQLite. This prevents accidental rescheduling after restarts.
- No external MafiaReturns authentication. Admin disputes are investigations, not automatic identity verification.
- A restart during PAUSED keeps paused time frozen; on resume the total suspension extends the end date.
- Finalisation is blocked until all seven effective days elapse; this foundation cannot issue prizes.
- No PvP, warmth, graphics, bosses, sieges, points or daily objectives in this version.
- Discord gateway interactions still require a smoke test in a real server; tests run against the local domain/database, not the Discord API.

## Acceptance gates

- Python unit tests pass; schema upgrade verified from original unversioned DB.
- Guild/DM and staff/host checks unit-tested (gateway-level checks need on-server verification).
- Registration timing (exact opening, closing, late entry), duplicate identities and restart persistence tested.
- Repeated start/resume, early finalise, paused end time and audit history tested.
- Publish/edit dashboard correctly works on an existing message, and buttons work after a restart (verify in dedicated guild).
