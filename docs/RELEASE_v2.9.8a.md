# v2.9.8a — Winter Arcade & Activities

Add the existing five Discord social arcade games to the website with original gallery, safe, snowman, catch and trivia art. The game server owns all prompts, choices, scoring, caps and stamps. Players resume the same current-day runs on either platform. Each game has three starts per event day. Seasonal and daily per-game high scores and City Cup are honorary; no score ledger, resources, prizes or extra reward logic.

The authenticated web endpoints return only the current puzzle projection, never the sealed answers. Starts validate the displayed day and attempt counter atomically; retries return the existing run even if finished meanwhile. Turns use the existing expected-step and interaction-ID validation. All UI game writes use the existing canonical identity and CSRF gates. No schema migration or worker upgrade required; the extra optional start parameters preserve existing Discord behavior. Web release 2.9.8a, shared API compatibility version 2.9.7.

QA: verify all five games, start and move replays, day rollover, private sessions, rankings, passport, responsive controls and original art bytes. Browser smoke uses fictional data and intercepts writes. Deployment does not mean production launch.
