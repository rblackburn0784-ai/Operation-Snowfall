# v2.9.8b1 — The Streets embedded chat correction

The v2.9.8b link-only community page did not meet the requirement: players must chat within the Snowfall website, not be pushed to Discord.

This amendment adds a mobile-responsive inline WidgetBot chat for the configured `#the-streets` channel. The configured `SNOWFALL_DISCORD_STREETS_URL` is parsed as a strict Discord guild/channel URL and transformed into the official `https://e.widgetbot.io/channels/GUILD_ID/CHANNEL_ID` frame URL. The browser does not load the third-party frame until a logged-in Underworld character explicitly chooses **Enter The Streets chat**. Leaving the in-page session or switching accounts removes the frame source. First-party CSP restricts third-party frames to the exact WidgetBot origin; first-party scripts, API and tokens remain same-origin. No new database columns, worker changes or game rules.

**Manual installation required**: Server owner must approve/invite the official WidgetBot bot and configure its channel access and moderation (see https://docs.widgetbot.io/tutorial/). The existing Operation Snowfall bot alone does not enable WidgetBot. Embedded chat may require WidgetBot guest or Discord login; it does not automatically authenticate as an Underworld character. Disclose the separate service's privacy terms and access before loading it. Verify two-way chat, mobile typing, moderator removal and channel visibility with consenting test accounts before labeling chat fully live. WidgetBot may permit browsing other public channels, so control public permissions carefully.

The old Discord channel link remains an optional fallback, not the primary chat action. Existing aggregated six-city statistics and community milestones stay below the new chat panel.

Longer-term enhancement: replace the third-party frame with first-party Underworld-character chat and an audited opt-in Discord bot relay if verified character name, in-game bans, and full site-native account control are required. That requires separate moderation and privacy design and must not be silently enabled on the current worker.
