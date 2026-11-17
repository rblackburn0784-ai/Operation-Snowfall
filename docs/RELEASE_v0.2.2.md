# Operation Snowfall v0.2.2 — Visual Identity & Customisation

This release turns the v0.2.0 Snowflake shop and v0.1.8 Trophy Cabinet into one illustrated player-collection system.

## Player-facing changes

- All **purchased and equipped** frames, banners, trails and specialist arcade gear are now visible on the new **960×540 collector profile card**. The original six city backgrounds remain bundled and rendered offline.
- **Character portraits:** original, procedurally drawn 1930s winter characters. The default recruit is free; players may buy and equip **Noir Detective**, **Winter Enforcer**, or **Frost Spectre** portrait styles in a new `portrait` slot.
- **Themed cards:** Midnight Mob, Aurora Skyline and Gilded Speakeasy banners; Icy Noir, Golden Gutter and Holly & Ivy frames; snowstorm/candy-cane trails; goggles/scarf/boots equipment details. Background portraits and borders actually change rather than just being text labels.
- **Fixed rarity** labels: Common, Rare, Epic, Legendary. These are assigned to catalogue items; there are no random rolls, loot boxes, rarity-based scoring effects or extra prize rights.
- **Collector badges:** three new trophies derived from the existing authoritative cosmetic unlock and equipped-slot rows: first cosmetic, five collected cosmetics, and a complete five-slot outfit. The Trophy Cabinet now contains **16** achievements and the image depicts all sixteen, colour-coded by rarity. Up to three legitimately earned badges decorate the profile card; the equipped earned title receives priority.
- **Menus:** `/snow profile`, public dashboard **My Profile**, and the Player Menu now show the collectible card. **My Card** buttons from Wardrobe and Trophy Cabinet let players preview changes without new channel messages.
- **Opt-in public sharing:** `/snowfun showcase` publishes the player's own card and accessible text in the current event-server channel. Discord's per-user per-guild 10-minute cooldown discourages spam. Test-day sessions cannot publish; flagged and disqualified identities are not permitted to post. Only this explicit command posts publicly.
- Original fallbacks retained: media-generation/upload errors return text instead of failing gameplay.

## Fair play and data

- Every displayed cosmetic must match an existing `cosmetic_unlocks` purchase/unlock row **and** the correct `cosmetic_equipped` slot.
- Milestone progress is calculated from the database and existing earned-trophy history; players cannot equip a locked title or invent an earned badge.
- The renderer does **not** touch `score_ledger`, `prize_awards`, attack RNG, boss, siege, or city rankings. Arcade equipment still affects arcade minigames only.
- Public sharing is self-initiated by the player; `/snow profile` and menu previews remain ephemeral/private.
- Slash-command cooldowns are process-local and reset when the bot process restarts. Existing Discord/server moderation and slowmode controls remain available.
- This release preserves **SQLite schema version 8** and all existing player collections, gifts, historical combat and prize data.

## Deployment and checks

After backing up the SQLite data, stop the bot, pull `main`, run `python -m pip install -e ".[dev]"`, `python -m pytest -q`, and restart with `python bot.py`.

Check in a disposable test day: buy and equip a cosmetic, open **My Card**, view the badge count, try a different frame, confirm no official scoring changes, verify the six city cards and render fallbacks. In a production-only channel, separately verify the self-initiated public sharing permission and its cooldown.

CI runs compile, fatal lint checks and all pytest tests on Ubuntu (Python 3.12/3.13) and Windows (Python 3.13). A real Discord gateway check is still recommended before launch.
