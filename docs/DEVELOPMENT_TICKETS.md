# Development backlog — Operation Snowfall v1.0

**Scope:** full-feature 7-day event; dedicated Discord server, self-declared MR identities, prizes for individuals only.
**Status:** Milestones A–C implemented in v0.1.1–v0.1.3; **Milestone D SNOW-017–021 and SNOW-032 implemented in v0.1.4** (automated tests; live-server smoke test pending). Milestone E SNOW-022–025 implemented in v0.1.5 (live Discord review pending). Milestone F tools SNOW-026–031 implemented in v0.1.6; **Kat sign-off, live Discord gateway and off-site recovery drill remain external launch gates**. Sizes are relative (S/M/L/XL), not delivery promises.
**P0:** blocks launch. **P1:** full-feature launch requirement. **P2:** polish if time allows.

## Milestones / order

| Stage | Target | Exit criterion |
|---|---|---|
| A | Foundation — v0.1.1 implemented; gateway smoke test pending | Self-declaration works only within event guild; registration opens 7d before; schema and admin audit present |
| B | Snowball Combat — v0.1.2 implemented; Discord smoke test pending | All PvP rules transactionally safe; daily score caps work |
| C | Economy — v0.1.3 implemented; Discord smoke test pending | Items, crafting, quests and gifts |
| D | Group gameplay — v0.1.4 implemented; Discord smoke test pending | Boss, sieges, city rankings, late-player echo and seven-day scheduler |
| E | Presentation — v0.1.5 implemented (Discord smoke test pending) | Art, cards, mobile UI and animation fallback |
| F | Launch tooling — v0.1.6; external sign-off pending | Individual prize export, correction audits, backups, simulation; Kat approval and on-server test required |

## Issue list

### SNOW-001 · Python package, CI, pytest and lint
- **Phase:** A · **Priority:** P0 · **Size:** S · **Epic:** Project
- **Depends on:** None
- **Acceptance:** Editable project installs; lint and unit tests pass

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-002 · One dedicated guild and secure environment config
- **Phase:** A · **Priority:** P0 · **Size:** S · **Epic:** Configuration
- **Depends on:** SNOW-001
- **Acceptance:** Foreign guilds and DMs rejected; no token in repo

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-003 · UTC season clock and registration-open boundary
- **Phase:** A · **Priority:** P0 · **Size:** M · **Epic:** Lifecycle
- **Depends on:** SNOW-002
- **Acceptance:** Registration starts exactly 168h before launch; event lasts 168 effective hours

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-004 · Schema, migrations and crash-safe SQLite
- **Phase:** A · **Priority:** P0 · **Size:** L · **Epic:** Database
- **Depends on:** SNOW-001
- **Acceptance:** Unique MR names per season; WAL, integrity check and migration tests

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-005 · Self-declared MR username/city registration
- **Phase:** A · **Priority:** P0 · **Size:** M · **Epic:** Identity
- **Depends on:** SNOW-003;SNOW-004
- **Acceptance:** No approval queue; duplicate names case insensitive; explicit declaration

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-006 · Dispute flags, staff review and audit log
- **Phase:** A · **Priority:** P0 · **Size:** M · **Epic:** Admin
- **Depends on:** SNOW-005
- **Acceptance:** Staff can flag/clear without silently altering ledger; no standard verification

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-007 · Welcome, rules and permanent dashboard navigation
- **Phase:** A · **Priority:** P1 · **Size:** L · **Epic:** Guild UX
- **Depends on:** SNOW-002;SNOW-005
- **Acceptance:** Welcome/rules visible; buttons survive restart and use private replies

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-008 · Host-only setup and lifecycle controls
- **Phase:** A · **Priority:** P0 · **Size:** L · **Epic:** Operations
- **Depends on:** SNOW-003;SNOW-006
- **Acceptance:** Start/pause/resume/finalize confirmed and audited

- **Status:** Implemented in v0.1.1; Discord smoke-test/CI gate pending

### SNOW-009 · Snowball and warmth lazy regeneration
- **Phase:** B · **Priority:** P0 · **Size:** M · **Epic:** Economy
- **Depends on:** SNOW-004;SNOW-003
- **Acceptance:** Caps respected over restart and while at cap

- **Status:** Implemented in v0.1.2; live Discord gateway smoke test pending

### SNOW-010 · Transactional PvP, hit/critical RNG and cooldown
- **Phase:** B · **Priority:** P0 · **Size:** XL · **Epic:** Combat
- **Depends on:** SNOW-009
- **Acceptance:** No duplicate actions, negative ammo, self/same-city hits

- **Status:** Implemented in v0.1.2; live Discord gateway smoke test pending

### SNOW-011 · Target selection and shields/KO protection
- **Phase:** B · **Priority:** P0 · **Size:** L · **Epic:** Safety
- **Depends on:** SNOW-010
- **Acceptance:** 2 scoring hits per pair/day; passive shield and 36h inactivity rules

- **Status:** Implemented in v0.1.2; live Discord gateway smoke test pending

### SNOW-012 · Immutable ledger, daily caps and tie breakers
- **Phase:** B · **Priority:** P0 · **Size:** L · **Epic:** Scoring
- **Depends on:** SNOW-010
- **Acceptance:** Scores reconcile; PvP cap 300/day; no score duplicates

- **Status:** Implemented in v0.1.2; live Discord gateway smoke test pending

### SNOW-013 · Throw selection, confirmation and result view
- **Phase:** B · **Priority:** P1 · **Size:** L · **Epic:** UI
- **Depends on:** SNOW-010;SNOW-007
- **Acceptance:** Buttons, slash path share engine; result fallback as text

- **Status:** Implemented in v0.1.2; live Discord gateway smoke test pending

### SNOW-014 · Inventory, crafting, buffs and guard
- **Phase:** C · **Priority:** P1 · **Size:** L · **Epic:** Items
- **Depends on:** SNOW-009;SNOW-010
- **Acceptance:** Costs, usage caps, expiry and guards tested

- **Status:** Implemented in v0.1.3; Discord smoke test pending


### SNOW-015 · Three deterministic daily quests and claim logic
- **Phase:** C · **Priority:** P1 · **Size:** L · **Epic:** Quests
- **Depends on:** SNOW-012
- **Acceptance:** 3 x 20 points/day, no duplicate claims

- **Status:** Implemented in v0.1.3; Discord smoke test pending


### SNOW-016 · Daily mystery gifts and Golden Snowball rarity
- **Phase:** C · **Priority:** P1 · **Size:** M · **Epic:** Gifts
- **Depends on:** SNOW-014;SNOW-015
- **Acceptance:** One gift/day and seasonal golden limit, reward odds validated

- **Status:** Implemented in v0.1.3; Discord smoke test pending


### SNOW-017 · Daily Snow Don boss with echo fallback
- **Phase:** D · **Priority:** P0 · **Size:** L · **Epic:** PvE
- **Depends on:** SNOW-012;SNOW-009
- **Acceptance:** 6 scored attempts/day; reliable HP, capped awards

- **Status:** Implemented in v0.1.4; Discord smoke test pending

### SNOW-018 · Six daily NPC fort sieges
- **Phase:** D · **Priority:** P0 · **Size:** L · **Epic:** Cities
- **Depends on:** SNOW-012;SNOW-009
- **Acceptance:** Each city gets its own fortress; 4 scored throws/player/day

- **Status:** Implemented in v0.1.4; Discord smoke test pending

### SNOW-019 · Normalized city leaderboard and snapshots
- **Phase:** D · **Priority:** P0 · **Size:** L · **Epic:** Cities
- **Depends on:** SNOW-012;SNOW-018
- **Acceptance:** Top-five averages, bonus caps, min-active threshold tested

- **Status:** Implemented in v0.1.4; Discord smoke test pending

### SNOW-020 · Seven daily themes and idempotent scheduler
- **Phase:** D · **Priority:** P1 · **Size:** L · **Epic:** Events
- **Depends on:** SNOW-003;SNOW-015;SNOW-017;SNOW-018
- **Acceptance:** One daily rollover; no double rewards after restart

- **Status:** Implemented in v0.1.4; Discord smoke test pending

### SNOW-021 · Personal and city boards with throttled edits
- **Phase:** D · **Priority:** P1 · **Size:** M · **Epic:** UI
- **Depends on:** SNOW-019;SNOW-007
- **Acceptance:** Individual prize board separate from city non-prize board

- **Status:** Implemented in v0.1.4; Discord smoke test pending

### SNOW-022 · Create reusable licensed asset pack and city scenes
- **Phase:** E · **Priority:** P1 · **Size:** L · **Epic:** Art
- **Depends on:** SNOW-007
- **Acceptance:** Six matched city backgrounds; item art and fallback

- **Status:** Implemented in v0.1.5; Discord gateway and mobile screenshot test pending

### SNOW-023 · Pillow PNG cards and accessible alt-text
- **Phase:** E · **Priority:** P1 · **Size:** L · **Epic:** Graphics
- **Depends on:** SNOW-022;SNOW-013
- **Acceptance:** Render profile, battle, boss, siege, champions; no state loss on failure

- **Status:** Implemented in v0.1.5; Discord gateway and mobile screenshot test pending

### SNOW-024 · Special hit/boss GIF effects
- **Phase:** E · **Priority:** P2 · **Size:** M · **Epic:** Animation
- **Depends on:** SNOW-023
- **Acceptance:** Static fallback always functional; reasonable file sizes

- **Status:** Implemented in v0.1.5; Discord gateway and mobile screenshot test pending

### SNOW-025 · Mobile layouts and minimal-message navigation
- **Phase:** E · **Priority:** P1 · **Size:** M · **Epic:** Polish
- **Depends on:** SNOW-021;SNOW-023
- **Acceptance:** No chat spam; buttons edit views; screenshot review

- **Status:** Implemented in v0.1.5; Discord gateway and mobile screenshot test pending

### SNOW-026 · Individual-only awards and export
- **Phase:** F · **Priority:** P0 · **Size:** L · **Epic:** Prizes
- **Depends on:** SNOW-012;SNOW-019;SNOW-006
- **Acceptance:** Payout CSV excludes city awards; city champ banner remains

- **Status:** Implemented in v0.1.6; external live checks pending

### SNOW-027 · Admin corrections, fraud review and reconciliations
- **Phase:** F · **Priority:** P0 · **Size:** L · **Epic:** Integrity
- **Depends on:** SNOW-012;SNOW-006
- **Acceptance:** Compensating ledger entries and reproducible standings

- **Status:** Implemented in v0.1.6; external live checks pending

### SNOW-028 · Backup, restore, logging and health checks
- **Phase:** F · **Priority:** P0 · **Size:** M · **Epic:** Operations
- **Depends on:** SNOW-004;SNOW-020
- **Acceptance:** Recovery drill and alerts pass

- **Status:** Implemented in v0.1.6; external live checks pending

### SNOW-029 · 7-day simulation, load and crash regression
- **Phase:** F · **Priority:** P0 · **Size:** XL · **Epic:** Quality
- **Depends on:** SNOW-010;SNOW-017;SNOW-018;SNOW-026
- **Acceptance:** No scoring duplication, fair city scores, results export stable

- **Status:** Implemented in v0.1.6; external live checks pending

### SNOW-030 · Kat approvals, staff training and dry run
- **Phase:** F · **Priority:** P0 · **Size:** M · **Epic:** Launch
- **Depends on:** SNOW-028;SNOW-029;SNOW-025
- **Acceptance:** Checklist signed; server IDs/date/prizes set; dry-run exported

- **Status:** Launch controls implemented; Kat sign-off and live dry run pending

### SNOW-031 · Rules post and privacy/identity dispute policies
- **Phase:** F · **Priority:** P1 · **Size:** M · **Epic:** Community
- **Depends on:** SNOW-005;SNOW-006
- **Acceptance:** Clear unofficial status; usernames public; disputes and retention explained

- **Status:** Implemented in v0.1.6; external live checks pending

### SNOW-032 · Protect late time zones from boss exhaustion
- **Phase:** D · **Priority:** P0 · **Size:** M · **Epic:** Fairness
- **Depends on:** SNOW-017
- **Acceptance:** Training echoes earn normal capped points without extra shared boss clear

- **Status:** Implemented in v0.1.4; Discord smoke test pending

## Milestone F acceptance status

- SNOW-026: Implemented (individual award CSV requires finalized season, paid/pending audit; prize values remain Kat's decision).
- SNOW-027: Implemented (append-only adjustments, reconciliation and dispute review; post-finalization corrections refused).
- SNOW-028: Implemented (online backup + SHA256 sidecar, offline restore and health status; offsite drill pending).
- SNOW-029: Implemented (seven-day disposable simulation, concurrency/migration tests; live server dry run pending).
- SNOW-030: Launch tooling ready, **Kat sign-off outstanding**; completion requires her approval and event-server rehearsal.
- SNOW-031: Implemented (privacy/fair-play text and `/snow privacy`; retention date must still be published by Kat).
- Extra v0.1.6a: host-selectable Day 1–7 practice within the same Discord application, with channel-scoped disposable database, optional verified archive and in-app start/stop commands.

## Definition of done

A feature is complete only when it has deterministic automated tests, staff-facing error states, audit for administrative mutations, no secrets in output, and a restart-safety demonstration where applicable. No city credit/perk prize may be emitted.

## Recommended first development sprint

Milestones A–F have code and regression tests. Use `docs/TEST_MODE_v0.1.6a.md` to rehearse in a dedicated test channel within the existing Discord server. Obtain Kat approval and complete all live launch checks before starting the actual season.
