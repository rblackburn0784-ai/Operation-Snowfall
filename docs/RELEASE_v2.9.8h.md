# v2.9.8h — Real Rival Avatars, Snowball Looks & Collector Banner Polish

**Scope:** appearance and read-only PvP target metadata only. Shared combat engine v2.9.7, player IDs, eligibility, resource costs, damage, official ledger, and Discord bot commands remain unchanged.

## Player appearance and Market

- **HQ and Market fitting:** original portraits are scaled down and centred within their purchased frame artwork. Eye/neck equipment and trails use the same calibration function at the new 10% framed / 4% unframed portrait inset.
- **Name banner:** the equipped banner artwork sits directly **above the portrait frame** rather than across the entire office backdrop. The current character's own name appears centred over it in a decorative serif font. Without a banner equipped, a simple art-deco nameplate remains.
- **Snowball over tommy gun:** a decorative foreground snowball is drawn above the weapon layer of the original profile frame, with the player's **equipped Market snowball trail** (Snowstorm or Candy Cane) colour and trail art. No additional art assets are required. Any unequipped or unowned trail cannot appear.
- **Preview vs actual:** Market try-on previews display proposed cosmetics **only** in the fitting room. The HQ and Snowball Alley use saved **equipped** slots, not temporary previews.

## Snowball Alley

- The rival chooser's left-hand illustration has been replaced with a compact rival portrait/card. Selecting an eligible rival displays the **rival's actual server-side outfit**: portrait, frame, banner, gear and trail, using the same art/validation rules as HQ.
- The selected rival's character name appears centred in the banner above their portrait. A placeholder is shown while no rival is selected; a pending throw whose target is no longer on the eligible list **never substitutes somebody else's outfit**.
- The player's own Snowball Alley loadout displays the **equipped Market trail** and the selected combat throwing style. **Quick, Standard, Power and Golden** remain *gameplay styles* and are **not** cosmetic items sold in the Market. The Market currently sells Snowstorm and Candy Cane **trails**, not alternate combat snowballs. Golden Snowball still requires an actual inventory item.
- The player selection and loadout update on refreshed wardrobe/targets or dropdown changes; custom cosmetics have **no combat bonus**.

## Cross-platform data safety

`SharedGame.targets()` calls the existing `CombatEngine.targets` eligibility logic unchanged, then reads `cosmetic_equipped` joined to `cosmetic_unlocks` for **those eligible target IDs and the current season only**. A single parameterised, batched read avoids per-rival queries. Only valid canonical cosmetic slots with unlocked category-matched keys are returned.

The `/v1/game/targets` response is authenticated and has `Cache-Control: no-store`. It shares **only the five public cosmetic slot keys**, not account identities, inventory, purchase history or other private data. No schema migration, writes or score modifications.

## Layout and accessibility

The new left-side rival preview fits into a two-column action card on wide screens and stacks above the controls when narrow. The name overlays use HTML text nodes, not inserted HTML from player names. Decorative snowball artwork is marked as such; portrait alternate text includes the selected rival's actual name.

## Acceptance checks

- Existing real game PvP eligibility, targeting and styles unchanged; real selected rival equipment returned and unowned/bad-slot keys rejected.
- Choose each rival and verify portrait, border, banner, gear and trail follow that character rather than the viewer. Clear/logout/rival change cannot retain a stale portrait.
- Equip and unequip Snowstorm/Candy Cane in the Market and verify HQ, fitting and Snowball Alley loadout; Market preview must not equip without confirmation.
- Confirm framed portraits are smaller, centred and keep eye/neck gear aligned. Banner above frame and centred stylised character name. Snowball/trail rendered **in front of** the tommy-gun decoration.
- Test desktop and 1100, 700, 390 and 320 pixel layouts, as well as keyboard focus and existing navigation menus.
- Run Python, Node/browser, lint and PostgreSQL CI before merging into QA website branch; keep separate Discord worker pinned and unchanged.

**Operator note:** CI and Railway readiness are necessary but not substitutes for a final visual pass at the requested resolutions.
