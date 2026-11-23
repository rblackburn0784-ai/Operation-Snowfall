# v2.9.8k — Scarf Asset Split

**Scope:** isolated QA website cosmetics presentation only. No gameplay, database, score, Market inventory, price, unlock, Discord bot, or other cosmetic changes.

## Why

The original Snow Don Scarf image looks good as a product thumbnail, but its broad chest-front design appears pasted over characters' coats. The user supplied a new transparent crimson-and-gold neck-wrapped scarf PNG specifically for worn appearance.

## Two independent presentation assets

- Existing **Market/catalogue/featured art** remains exactly `/art/v290/cosmetics/gear/scarf.png` — original file and hash are unchanged.
- New **worn avatar art** is `/art/v290/cosmetics/gear/scarf_worn.png`. It is a web-optimised transparent 220 × 224 PNG derived from the user's newly supplied image, cropped to the actual garment rather than including the surrounding transparent canvas.

Both represent the *same* existing cosmetic key `scarf`, category `gear`. There are **no new shop items**, unlocks, balances or equipment records.

## Where each appears

| Surface | Scarf artwork |
| --- | --- |
| Winter Market product card | **Original** `scarf.png` |
| Winter Market featured item | **Original** `scarf.png` |
| Headquarters equipped avatar | **New** `scarf_worn.png` |
| Winter Market fitting/try-on portrait | **New** `scarf_worn.png` |
| Snowball Alley selected rival portrait | **New** `scarf_worn.png` |

The split happens at `profileLayers()` and `fittingLayers()`, so no product-card, purchase, unlock or server data paths change.

## Fit and layering

- Worn scarf has a compact transparent canvas with a true open-neck silhouette and hanging tassels.
- Portrait-specific `neck` landmarks are retained for all eight existing avatar poses.
- Render width is 90% of existing neck landmark width, placed 3.5 portrait-coordinate points below its neck anchor, so it sits beneath the chin rather than over the mouth.
- The old gradient alpha fade is disabled for the worn scarf. The new PNG's original tassels, transparent background and edge treatment remain visible.
- Avatar frames stay in front of gear; goggles, boots, snow trails and foreground snowball retain their existing z-index and logic.

## Release checks

- New transparent PNG and unchanged original Market PNG both exist.
- Catalogue and featured-item rendering continue to reference `COSMETIC_ART.scarf`; HQ/fitting/rival use `WORN_COSMETIC_ART.scarf`.
- Market preview does not buy or equip an item. Existing player unlock and equipped-slot validation is unchanged.
- JavaScript regression coverage verifies all 8 portrait poses, fit positions, source paths and PNG transparency; prior tests and PostgreSQL integration still pass.
- Deploy only the Snowfall-Web-QA website branch after full Linux/Windows/PostgreSQL CI.
- Manual visual QA at desktop and mobile widths is required to judge the actual scarf layering against each selected portrait.

**Note:** The original full-resolution user PNG remains in the user's supplied conversation; the repository includes an optimised transparent web rendering appropriate for the small avatar overlay.
