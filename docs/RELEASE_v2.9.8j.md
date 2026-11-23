# v2.9.8j — Banner Text Fit & Scarf Layer Polish

**Scope:** QA website only, focused CSS and browser display-calibration changes. All original cosmetics, portrait images, player equipment records, market purchases, combat, scoring, event and Discord bot operations remain unchanged. No schema migration.

## Banner text

The previous single-line name renderer constrained all names to 85% of the overall banner box, used `overflow:hidden`, and did not account for the narrower central ribbon inside the actual selected banner images. This clipped the ends of names such as `SnowDude` on Gilded, Aurora and Midnight banners.

- Username text now has intrinsic (unclipped) width, with its centre aligned to the banner image centre using independent CSS `translate` and JavaScript horizontal scaling.
- Different **central safe writing areas** are used: Gilded 34%, Aurora 37%, Midnight 38% of the full displayed banner width. A player with no banner retains 94% of the available width.
- JavaScript reads the displayed banner width and the text's actual width, reduces font size as necessary and compresses horizontally only when a name still cannot fit at the 8px lower bound.
- Refitting occurs on render, on the following animation frame, on page switches and on browser resize. No overflow clipping, forced line break, new nameplate box, added ornament or custom assets.
- The name remains live text rather than baked into an image. HQ, Winter Market and eligible rival previews share the same code.

## Scarf collar alignment

The existing `scarf.png` is a decorative chest-front overlay. The previous placement used the portrait's neck x/y landmark but rendered the scarf at *100%* of the broad chest-based width, making it appear pasted across the torso.

- The existing original PNG is now rendered at **78%** of its previous landmark width and begins **6.5 portrait-coordinate percentage points higher**, targeted at the throat/collar region in each of the eight original portrait poses.
- A soft lower-edge alpha fade blends the hanging tail into the coat and avoids an abrupt sticker edge. Eye goggles, other equipment and Market trails are not changed.
- The original PNG is preserved, so a genuinely 3D scarf wrapping behind illustrated lapels is **not** claimed. If after visual QA the fabric still does not follow a specific portrait's coat collar naturally, a newly illustrated transparent neck-wrapped PNG or per-portrait layered mask will be needed. This release first tries the non-destructive placement correction requested.

## Acceptance checks

- Gilded, Aurora, Midnight and no-banner previews of SnowDude and TheSnowman show every character on **one centred line** without missing letters at full width and at 1100, 768, 390 and 320px.
- Changing banners instantly recalculates the central safe area without carrying another banner's font size. No opaque UI rectangle is introduced.
- Scarf lies closer to the throat and no longer fills the entire front of the coat; it stays scaled appropriately on both framed and unframed portraits. Other cosmetics still align to portrait landmarks.
- Test HQ, Winter Market preview and Snowball Alley selected rival; no stale cross-account outfit leaks.
- Full GitHub CI: Node UI tests, Python unit/integration tests on Linux and Windows, PostgreSQL compatibility.
- Railway staging health and QA-release audit after deploying **only Snowfall-Web-QA**. The independent Discord worker stays pinned and unchanged.

**Manual appearance checks still matter.** Tests cannot certify natural artwork occlusion or exact legibility of every font and ribbon texture.
