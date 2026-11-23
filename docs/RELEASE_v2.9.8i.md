# v2.9.8i — Character Nameplate & Banner Finish

**Scope:** small web-only presentation correction to the v2.9.8h avatar visuals. No asset replacements, backend, game engine, account, rewards, score, or Discord changes.

## Visual corrections

1. The selected Market banner artwork is shown **by itself**: no additional dark blue box, gold border, rounding, drop-shadow frame, or unrelated ornamental corners wrapped around the banner. The original art remains uncropped at `object-fit: contain`.
2. The saved character name appears exactly **once, centred on one line**. The same treatment applies to the Headquarters card, the Winter Market fitting room preview and Snowball Alley's selected rival.
3. A name without an equipped banner is plain gold decorative lettering above the portrait, **not** inside a fabricated nameplate box.
4. For long names, the browser measures available text width and reduces font size only as much as needed. In extremely narrow spaces, it compresses the text horizontally as a final fallback, retaining all characters without line wraps or ellipsis.
5. The name automatically refits when users resize the browser and when they switch pages or rival profiles.

All previously approved portraits, frames, equipment, snowball positions, trailers, combat selectors and game rules are untouched.

## QA acceptance

- Inspect `SnowDude` and `TheSnowman` on HQ/Market/Alley at 1920, 1100, 768, 390 and 320 px widths: **one name on one line**.
- Toggle an equipped Market banner and a temporary preview banner: see the complete original ribbon artwork **without an added backing rectangle**.
- Change to an unbannered rival: name appears as clean lettering, no UI-generated box.
- Try an unusually long name to confirm no wrapping or hidden characters.
- Verify every earlier avatar layer, snowball, Market inventory, player controls, staff tools and Discord worker remain unchanged.
- Run the Linux, Windows, PostgreSQL and JavaScript CI matrix before releasing to the isolated Railway web QA deployment branch.

**Manual visual acceptance is still advisable after CI.**
