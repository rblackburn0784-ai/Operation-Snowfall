# v2.9.7d — Full Release Consolidation

This is a staging release, not a production event launch. Shared API and schema compatibility remain 2.9.7; the independently identified website revision is 2.9.7d. Main is fast-forwarded from the previous baseline via the complete tested development history.

- Live smoke derives both API and website versions from release.py, waits for the correct deployment, compares deployed HTML/CSS/JS bytes and all branding/art bytes, checks readiness, the isolated season and security headers.
- Browser smoke intercepts all writes. It tests six game sections, fictional siege/retry, portrait layers, new newspaper's four mapped stories, edition switching, refresh, geometry, narrow mobile menu and screenshots. Never writes real game history.
- Adds a startup-only, aggregate, read-only QA audit using the existing isolation guard and audit implementation. No public endpoint, credentials, player IDs or names. Inspect QA_RELEASE_AUDIT in Railway logs; blockers or unavailable are not a clean sign-off.
- Retains original assets, scoring, reward rules, idempotency and database schema. The currently deployed Discord worker is kept unchanged until shared live verification and a planned worker upgrade/rollback. Production cutover is not implied by main consolidation.

Release gates: green CI (Linux, Windows, PostgreSQL), green real-browser smoke, latest Railway deployment, QA_RELEASE_AUDIT without blockers, manual desktop/mobile visual review and real linked fictional-player Discord/Underworld round trip plus daily rollover. No duplicate reward or exploit guarantee beyond tested cases. Do not promote the QA database or award prizes.

Rollback QA web to 0c0e25ee99b5e0d12d6d7445ab2212b6374d0a33 if required.
