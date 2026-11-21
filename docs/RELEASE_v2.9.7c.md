# v2.9.7c — Full-page five-box newspaper edition

Use the supplied complete 4:5 artwork, including its existing masthead. Do not crop the image or add a second visible masthead.

Upload the supplied snowfall-wire-frontpage.webp to src/snowfall/platform/static/. The existing branding config activates the full-page layout when the asset is present. Without it, the original masthead and readable five-box parchment layout remain available.

The live issue data sits in the blank strip immediately beneath the masthead. Theme and headline sit in the large frame above its printed rule, and the main detail sits below that rule. The four small framed boxes retain stable keys: streets/combat, boss, cities and community. Missing reports remain explicitly unavailable. The update/verification notice is below the artwork, leaving its illustrated footer clear.

The full page uses calibrated percentage coordinates, responsive typography and extra minimum height for narrow displays. Forced colors uses normal document flow. Existing archive selection, refresh and verified-only text escaping remain unchanged. No database, bot, or gameplay changes.

Inspect the deployed page at desktop and mobile widths with waiting, live, archived and final editions. Confirm the new static image returns HTTP 200 and config branding.wire_template is true.
