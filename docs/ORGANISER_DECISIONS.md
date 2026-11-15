# Kat's locked organiser decisions — Operation Snowfall v1.0

| Question | Approved | Implementation rule |
|---|---|---|
| Registration identity | Self-declaration | MR name and city selected by user; no mandatory approval; case-insensitive name uniqueness; review only on dispute |
| Prizes | Individual only | Pay 1st/2nd/3rd and individually defined specials; city rankings, champion banner and bragging rights carry no MR payouts |
| Discord location | Separate dedicated server | Configure one GUILD_ID; deny DMs and other guilds; guild-only commands, guild-targeted sync |
| Registration window | Seven days before start | Automatically open at start UTC minus 168 hours; continue during LIVE; late join no backfill |
| Event duration | Seven days | 168 effective hours of play; day boundaries based on 24h offsets from configured start |

### Still required for production

- Event start UTC timestamp (must be explicitly supplied)
- Dedicated Discord guild ID and chosen public/staff channels
- Host/staff Discord user IDs and roles
- Individual prize amounts and prize rules
- Staff review/appeals and data retention policy
