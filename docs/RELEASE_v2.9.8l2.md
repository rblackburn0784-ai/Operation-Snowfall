# v2.9.8l2 — Resource Card Layout Fixes

This is the requested **v2.9.8j — Resource Card Layout Fixes** visual adjustment, applied as a forward-only hotfix on top of v2.9.8l1. Version 2.9.8j is already assigned to the earlier scarf/banner release, so the actual branch and patch identifier use **v2.9.8l2** to preserve every intervening release.

## Changes

- Headquarters **Snowflakes** (left) uses the crystal-snowflake illustration (`points_*.webp`) while retaining the spendable **snowflakes** balance and original snowflake stage thresholds.
- Headquarters **Total Points** (right) uses the gold-token illustration (`currency_*.webp`) while retaining the official **score** and point-stage thresholds.
- This intentionally swaps **only the two Headquarters card images**, not the labels, live values, currencies, score ledgers or unrelated Market wallet / leaderboard artwork.
- The warmth thermometer image moves out of the upper portrait row to the bottom of the warmth card, following the exact warmth value and cold-status explanation. It takes the place of the previously visible thin progress line; `hqWarmthMeter` is retained invisibly so existing read-only UI update code remains compatible.
- The snowball stockpile artwork moves down with responsive top spacing and bottom-anchored image content so it no longer collides with the Snowballs heading.
- Static CSS/JS cache keys advance from `298l-r1` to `298l-r2`; all other layout, artwork and gameplay mechanics are unchanged.

## QA

CI now runs `tests/test_v298l2_resource_card_layout.mjs`, and the existing `tests/test_v298l_resources.mjs` verifies that snowflakes and points can have **different stage numbers** even after swapping illustrations. Source artwork remains the exact set delivered in v2.9.8l. No images are recreated or repackaged here.

Acceptance after deployment: refresh the isolated Snowfall-Web-QA website, verify the left/right visual swap and live values, check the thermometer at the bottom, and check snowball art at desktop, resized browser, 390px and 320px. Confirm the existing Market wallet, leaderboard, old resource behaviour, account linking and independent Discord bot remain untouched.

**No migration, no economic/score/combat change and no Discord worker update.**
