# v2.9.6h — Quick Play & Whole-Site Usability

No artwork modifications: the existing hero, splash damage stages, portraits, frames, market, city map, and Wire remain intact. Play-first HQ (resources, actions, assignments before character collection), collapsible extra details, compact sticky resources, mobile six-section navigation, browser history, keyboard focus, market quick links, direct configured Underworld sign-in route and optional Discord linking. QA credentials and technical verification remain available but collapsed.

Existing server rules and identity checks remain authoritative. UI action hints use actual snapshot balance, HQ wall-clock deadlines, existing game constants, and available target results. No auto-attack or auto-PvP opt-in. Explicit action only, existing CSRF and idempotency handling retained, including exact replay of uncertain throws. Persistent outcome and errors, refresh controls, and conservative visible-page refreshes.

Web QA only; no production deployment, schema, scoring, prize or artwork changes. Rollback to 56415e9728a7efa2839b3b514f0e2a20a02c7669.
