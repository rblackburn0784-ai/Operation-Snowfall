# v2.9.7c — Five-box newspaper edition

The original Snowfall Wire masthead and live issue strip remain unchanged. New body artwork is cropped to 1197 × 1051 to remove the generated fixed Day 2 strip and duplicate masthead.

Upload the supplied snowfall-wire-frontpage.webp to src/snowfall/platform/static/. The branding config detects the asset and activates calibrated overlays. Without it, a readable five-box parchment layout remains available.

Slots are keyed, not dependent on response order: lead (full width), streets/combat (upper left), boss (upper right), cities (lower left), community (lower right). Missing data remains explicitly unavailable. All text is escaped; editions retain their dynamic day/status. Notice is below the artwork to avoid the illustrated footer. Mobile preserves the same mapping with extra height. Final edition retains dynamic archive labels and border treatment.

No changes to verified ledgers, shared gameplay, database or Discord. Inspect artwork alignment on desktop and narrow viewports after asset upload.
