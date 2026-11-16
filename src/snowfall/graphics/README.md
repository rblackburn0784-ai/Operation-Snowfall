# Operation Snowfall — visual rendering

All v0.1.5 graphics are generated **locally using Pillow**. Game transactions,
resource changes and score ledgers never depend on graphics, files or uploads.

- `art/cities/*.webp`: six matching 16:9 painted winter city backdrops.
- `art/items/*.png`: transparent icons for equipment, Snow Don and sieges.
- `cards.py`: 960×540 PNG profile, PvP, Snow Don, city siege and champions cards.
- `cards.hit_animation` and `cards.world_animation`: on-demand 480×270 GIFs
  only for critical/KO and final blows; enforce a 4 MB image budget.
- `delivery.py`: Discord interaction edits and private replies, with full text
  retained; on image render/upload errors, users see full text instead.

Assets ship inside the Python wheel and require no external image host, API key,
web browsing or new Discord intents. They have been specifically generated for
Operation Snowfall. See `docs/ASSET_LICENSE.md`.

`assets/previews/` in the release ZIP provides examples; not required at runtime.
