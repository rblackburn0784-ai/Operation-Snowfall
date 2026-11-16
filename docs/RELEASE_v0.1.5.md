# Operation Snowfall v0.1.5 — Milestone E: Graphics and Presentation

## Completed tickets

- **SNOW-022** — six matched original painted winter-noir backgrounds and eight
  transparent equipment/event icons, bundled in the installed wheel; offline
  fallback when a background is absent.
- **SNOW-023** — 960×540 illustrated Pillow cards for individual profile,
  PvP hit/miss/critical/KO, Snow Don, siege, boss/fort status and podium.
  Text output remains complete and uploaded files carry accessibility descriptions.
- **SNOW-024** — compact original 480×270 multi-frame GIFs for special
  critical/KO and final-blow events, with automatic static PNG fallback.
- **SNOW-025** — narrow-phone-friendly text and card layout, same-message
  view transitions and stale media cleanup, persistent dashboard Podium button,
  in-place Refresh, and private view navigation to Inventory.

## Setup / update

1. Stop the bot; back up `data/snowfall.sqlite3` and local config before updating.
2. `git pull origin main`
3. `python -m pip install -e ".[dev]"`
4. `python -m pytest -q`
5. `python bot.py`

The database schema is unchanged from v0.1.4a. Existing registrations, event
states, combat history, rankings and published-message IDs are preserved.

**Discord permissions:** View Channel, Send Messages, Read Message History,
Embed Links, and **Attach Files** are needed for cards. If Attach Files is
missing, or the renderer/upload fails, the bot sends the same battle outcome
as text. No extra privileged intents are required.

## Test in the dedicated server

1. Confirm the previous Discord 403 Missing Access problem is fixed: bot is
   installed into the exact `guild_id` with bot + `applications.commands` scopes.
2. Use `/snow dashboard` and the public dashboard's Profile, World, Podium,
   Inventory and Refresh buttons; ensure one original message is edited for
   private view transitions and that menus remain usable on mobile.
3. Use a **separate test season/database**; do not start the real Christmas season
   early. Join with different-city test users, `/snow ready`, then throw a ball.
4. Check PNG/text for hits and misses, GIFs for a critical/KO, and animated
   Snow Don final blows. An ordinary miss should not require animation.
5. Remove Attach Files permission temporarily and confirm text still appears
   and score/ball counts are correct. Restore permission afterwards.
6. Restart the process; the already published public dashboard and the
   five-minute leaderboard message must remain reusable.
7. Review `assets/previews/` or run tests for image output sizes and bundled art.

## Non-goals / pending

- **Milestone F** (prize exports, fraud corrections, load/backups/dry-run) is not
  implemented yet. The championship podium before closure is explicitly
  provisional and does **not** issue prizes or crown a city for money.
- Discord gateway/channel smoke tests must be done on the dedicated server.
- Generated cards intentionally show numeric text as well as images, so
  players using assistive technology are not excluded.
