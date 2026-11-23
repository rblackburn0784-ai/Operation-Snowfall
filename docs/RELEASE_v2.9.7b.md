# v2.9.7b — Snowfall Wire newspaper layout

- Retain the existing masthead, issue labels and verified ledger content.
- Use the existing front-page and final edition template illustrations as decorative backgrounds beneath the live editorial and story grid.
- Remove the redundant inline template image and its JS switching. CSS selects the final background via the existing edition state.
- Center lead headline and preserve two-column desktop / single-column mobile stories; no fixed content height.
- Preserve QA markings, historical edition selector, refresh and warning messages.
- Web-only revision; no database or Discord changes. Existing v2.9.7 gameplay API version remains unchanged.
- Validate waiting, live, archive, final and narrow/mobile editions visually before production release.
