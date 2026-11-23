# v2.9.8l1 — Railway static artwork packaging repair

The original v2.9.8l integration was merged and all source-tree tests passed, but the live Snowfall-Web-QA HTTP logs recorded **404 Not Found** for several `/art/v290/status/v298l/*.webp` URLs. This was a packaging omission, not a resource/gameplay bug.

## Root cause
The website serves public artwork from `snowfall.graphics` in the **installed Python package**. The new 21 WebP images existed in GitHub under `src/snowfall/graphics/art/v290/status/v298l/`, but the setuptools `[tool.setuptools.package-data]` allowlist in `pyproject.toml` did not include that new nested directory. The build used `pip install .[postgres,web]`, so the installed wheel silently omitted the art. Earlier tests checked source-tree file existence instead of the built package.

## Fix
- Add `art/v290/status/v298l/*.webp` to the existing `snowfall.graphics` package-data list. This preserves all other artwork paths and packages the new twenty dynamic resources **plus** the winter street backdrop.
- Add `tests/check_v298l_wheel_assets.py`, which opens the actual wheel and checks all 21 images are present, valid WebP files, and that the previously split worn scarf remains packaged.
- Require that wheel-integrity test in GitHub CI alongside the existing Linux, Windows and PostgreSQL suites.

This is a staging web packaging hotfix. **No resource thresholds, graphics, HTML, JavaScript, game rules, database schemas, Discord bot commands, score or prizes are changed.** The web UI remains v2.9.8l.

## Final acceptance
1. CI wheel packaging assertion passes along with all existing browser/Python/PostgreSQL jobs.
2. Deploy the corrected commit **only** to Snowfall-Web-QA and confirm Railway readiness returns HTTP 200.
3. Confirm live requests to `/art/v290/status/v298l/snowballs_4.webp`, `currency_2.webp`, `points_3.webp`, and `winter_street.webp` return 200 rather than 404.
4. Check HQ, Winter Market, Snowball Alley and City Wars actual art display in-browser; visually inspect mobile layout.
5. Leave the independent Discord worker service unchanged.
