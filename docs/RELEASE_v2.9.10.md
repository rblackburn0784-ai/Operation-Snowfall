# v2.9.10 — Winter Activities 2.0: Adventure Engine

- Reusable scene, hotspot, dialogue, item, evidence and conditional-action content rules.
- Opening chapter: The Missing Winter Dispatch, office and loading bay, accessible keyboard/mouse/touch controls, private persistent satchel and notebook.
- Progress is stored by season, canonical player ID and chapter. Current event day gates writes; progress survives day changes, refresh and sign-in. QA reset/restart removes progress and changes the epoch, invalidating stale browser requests.
- Server validates all actions, prerequisites, identity, event phase, epoch, revision and replay identity; no undiscovered clue text or solution flags sent to browser.
- New additive table created on first activities load under the standard write lock; SQLite and PostgreSQL supported. No core schema-version change. No official points, prizes, currency, combat or arcade modifications.
- Original Discord-shared activities remain available below adventure. New adventure is website-only for this foundation release; no Discord commands or integration are removed.
- Existing artwork is preserved; two original lightweight SVG scene illustrations are placeholders for the later artwork pass. City map, seven expanded mysteries and further adventure content are later releases.
- Automated unit, API, PostgreSQL reset and browser regression coverage. Deploy only after CI passes.
