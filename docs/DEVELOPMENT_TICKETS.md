# Development backlog — Operation Snowfall v1.0

**Scope:** full-feature 7-day event; dedicated Discord server, self-declared MR identities, prizes for individuals only.
**Status:** SNOW-001 through SNOW-008 implemented in v0.1.1 (24 local tests passed; on-server smoke test and CI verification pending). SNOW-009 onward remain open. Sizes are relative (S/M/L/XL), not delivery promises.
**P0:** blocks launch. **P1:** full-feature launch requirement. **P2:** polish if time allows.

## Milestones / order

| Stage | Target | Exit criterion |
|---|---|---|
| A | Foundation — v0.1.1 implemented; gateway smoke test pending | Self-declaration works only within event guild; registration opens 7d before; schema and admin audit present |
| B | Combat | All PvP rules transactionally safe; daily score caps work |
| C | Economy | Items, crafting, quests and gifts |
| D | Group gameplay | Boss, sieges, city rankings and seven-day scheduler |
| E | Presentation | Art, cards, mobile UI and animation fallback |
| F | Launch | Individual prize export, abuse tests, backups, load simulation, Kat approval |

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

### SNOW-010 · Transactional PvP, hit/critical RNG and cooldown
- **Phase:** B · **Priority:** P0 · **Size:** XL · **Epic:** Combat
- **Depends on:** SNOW-009
- **Acceptance:** No duplicate actions, negative ammo, self/same-city hits

### SNOW-011 · Target selection and shields/KO protection
- **Phase:** B · **Priority:** P0 · **Size:** L · **Epic:** Safety
- **Depends on:** SNOW-010
- **Acceptance:** 2 scoring hits per pair/day; passive shield and 36h inactivity rules

### SNOW-012 · Immutable ledger, daily caps and tie breakers
- **Phase:** B · **Priority:** P0 · **Size:** L · **Epic:** Scoring
- **Depends on:** SNOW-010
- **Acceptance:** Scores reconcile; PvP cap 300/day; no score duplicates

### SNOW-013 · Throw selection, confirmation and result view
- **Phase:** B · **Priority:** P1 · **Size:** L · **Epic:** UI
- **Depends on:** SNOW-010;SNOW-007
- **Acceptance:** Buttons, slash path share engine; result fallback as text

### SNOW-014 · Inventory, crafting, buffs and guard
- **Phase:** C · **Priority:** P1 · **Size:** L · **Epic:** Items
- **Depends on:** SNOW-009;SNOW-010
- **Acceptance:** Costs, usage caps, expiry and guards tested

### SNOW-015 · Three deterministic daily quests and claim logic
- **Phase:** C · **Priority:** P1 · **Size:** L · **Epic:** Quests
- **Depends on:** SNOW-012
- **Acceptance:** 3 x 20 points/day, no duplicate claims

### SNOW-016 · Daily mystery gifts and Golden Snowball rarity
- **Phase:** C · **Priority:** P1 · **Size:** M · **Epic:** Gifts
- **Depends on:** SNOW-014;SNOW-015
- **Acceptance:** One gift/day and seasonal golden limit, reward odds validated

### SNOW-017 · Daily Snow Don boss with echo fallback
- **Phase:** D · **Priority:** P0 · **Size:** L · **Epic:** PvE
- **Depends on:** SNOW-012;SNOW-009
- **Acceptance:** 6 scored attempts/day; reliable HP, capped awards

### SNOW-018 · Six daily NPC fort sieges
- **Phase:** D · **Priority:** P0 · **Size:** L · **Epic:** Cities
- **Depends on:** SNOW-012;SNOW-009
- **Acceptance:** Each city gets its own fortress; 4 scored throws/player/day

### SNOW-019 · Normalized city leaderboard and snapshots
- **Phase:** D · **Priority:** P0 · **Size:** L · **Epic:** Cities
- **Depends on:** SNOW-012;SNOW-018
- **Acceptance:** Top-five averages, bonus caps, min-active threshold tested

### SNOW-020 · Seven daily themes and idempotent scheduler
- **Phase:** D · **Priority:** P1 · **Size:** L · **Epic:** Events
- **Depends on:** SNOW-003;SNOW-015;SNOW-017;SNOW-018
- **Acceptance:** One daily rollover; no double rewards after restart

### SNOW-021 · Personal and city boards with throttled edits
- **Phase:** D · **Priority:** P1 · **Size:** M · **Epic:** UI
- **Depends on:** SNOW-019;SNOW-007
- **Acceptance:** Individual prize board separate from city non-prize board

### SNOW-022 · Create reusable licensed asset pack and city scenes
- **Phase:** E · **Priority:** P1 · **Size:** L · **Epic:** Art
- **Depends on:** SNOW-007
- **Acceptance:** Six matched city backgrounds; item art and fallback

### SNOW-023 · Pillow PNG cards and accessible alt-text
- **Phase:** E · **Priority:** P1 · **Size:** L · **Epic:** Graphics
- **Depends on:** SNOW-022;SNOW-013
- **Acceptance:** Render profile, battle, boss, siege, champions; no state loss on failure

### SNOW-024 · Special hit/boss GIF effects
- **Phase:** E · **Priority:** P2 · **Size:** M · **Epic:** Animation
- **Depends on:** SNOW-023
- **Acceptance:** Static fallback always functional; reasonable file sizes

### SNOW-025 · Mobile layouts and minimal-message navigation
- **Phase:** E · **Priority:** P1 · **Size:** M · **Epic:** Polish
- **Depends on:** SNOW-021;SNOW-023
- **Acceptance:** No chat spam; buttons edit views; screenshot review

### SNOW-026 · Individual-only awards and export
- **Phase:** F · **Priority:** P0 · **Size:** L · **Epic:** Prizes
- **Depends on:** SNOW-012;SNOW-019;SNOW-006
- **Acceptance:** Payout CSV excludes city awards; city champ banner remains

### SNOW-027 · Admin corrections, fraud review and reconciliations
- **Phase:** F · **Priority:** P0 · **Size:** L · **Epic:** Integrity
- **Depends on:** SNOW-012;SNOW-006
- **Acceptance:** Compensating ledger entries and reproducible standings

### SNOW-028 · Backup, restore, logging and health checks
- **Phase:** F · **Priority:** P0 · **Size:** M · **Epic:** Operations
- **Depends on:** SNOW-004;SNOW-020
- **Acceptance:** Recovery drill and alerts pass

### SNOW-029 · 7-day simulation, load and crash regression
- **Phase:** F · **Priority:** P0 · **Size:** XL · **Epic:** Quality
- **Depends on:** SNOW-010;SNOW-017;SNOW-018;SNOW-026
- **Acceptance:** No scoring duplication, fair city scores, results export stable

### SNOW-030 · Kat approvals, staff training and dry run
- **Phase:** F · **Priority:** P0 · **Size:** M · **Epic:** Launch
- **Depends on:** SNOW-028;SNOW-029;SNOW-025
- **Acceptance:** Checklist signed; server IDs/date/prizes set; dry-run exported

### SNOW-031 · Rules post and privacy/identity dispute policies
- **Phase:** F · **Priority:** P1 · **Size:** M · **Epic:** Community
- **Depends on:** SNOW-005;SNOW-006
- **Acceptance:** Clear unofficial status; usernames public; disputes and retention explained

### SNOW-032 · Protect late time zones from boss exhaustion
- **Phase:** D · **Priority:** P0 · **Size:** M · **Epic:** Fairness
- **Depends on:** SNOW-017
- **Acceptance:** Training echoes earn normal capped points without extra shared boss clear

## Definition of done

A feature is complete only when it has deterministic automated tests, staff-facing error states, audit for administrative mutations, no secrets in output, and a restart-safety demonstration where applicable. No city credit/perk prize may be emitted.

## Recommended first development sprint

Start with SNOW-001 through SNOW-006 (package, dedicated guild, UTC event window, schema, registration and dispute review). The accompanying starter project implements a minimal subset of these and deliberately does not pretend PvP, graphics or prizes are ready.
