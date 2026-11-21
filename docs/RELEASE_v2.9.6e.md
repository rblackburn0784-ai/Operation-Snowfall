# v2.9.6e — Winter Market & Cosmetic Showcase Overhaul

Reuses all committed Discord artwork: original shop and HQ backgrounds, 18 catalogue cosmetic images (including female variants), and four workshop items. No new images. Browse category/rarity/ownership/search filters, server catalogue prices, manual featured-item rotation, actual equipped/owned status, and preview multiple cosmetic slots with the exact same rendering helper as the HQ.

Preview is browser-memory only, reset on identity change, not added to inventory or shared state. Reset individual slots or all. The preview cost is informational, not a bundle or checkout. Purchase confirmation is explicit, and buying never auto-equips. Existing authenticated purchase/equip/craft endpoints, idempotency keys, price checks, ownership and game phase rules remain authoritative. No changes to scoring, gameplay, schema, prize policy or Discord bot. Gear benefits remain arcade-only as indicated in the server descriptions.

QA web-only, retain banner, Snow Don and HQ. Run CI plus live browser smoke. Rollback: pin Snowfall-Web-QA back to 98fd41d82e9d329bfb8e342edfc84f02d699b7f2.
