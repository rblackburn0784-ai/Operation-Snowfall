# v2.9.8b — The Streets & Community

- New read-only community hub with daily aggregate activity, verified milestones, six city noticeboards, daily rivals and cooperative objectives.
- Reuses the existing season-scoped records and original city crests and newsroom art. No names, player IDs, chat messages, private submissions or exact action timestamps in the public community projection.
- Polls on visible community page every 30 seconds, with manual refresh and explicit stale-state handling.
- Discord remains the moderated chat. Set SNOWFALL_DISCORD_STREETS_URL in the web service to the exact HTTPS channel link copied from Discord. No bot token, message ingestion or chat relay required; no fabricated channel ID.
- Fixes lost private-page refresh during navigation into Winter Arcade or Activities; enables arcade polling.
- No schema changes, prizes, score rules or worker restart.
- Live browser regression covers community and reruns arcade checks. QA only.
