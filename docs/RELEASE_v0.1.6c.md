# Operation Snowfall v0.1.6c — Progressive Snow Don Artwork

The Snow Don in **WINTER WARZONE** and the **PvE battle result card** now uses the
organiser's ten original transparent character portraits instead of the tiny
starter snowman icon. The selection reads *actual remaining shared boss HP*.
Boss fights, scoring, cooldown, sieges, pause/restart behaviour and launch
settings have not changed. Production and disposable test days use the same
art selector with their own corresponding HP.

## Health thresholds (HP remaining)

| HP remaining | Image |
|---|---|
| More than 90% up to 100% | snow_don_100.png |
| More than 80% up to 90% | snow_don_90.png |
| More than 70% up to 80% | snow_don_80.png |
| More than 60% up to 70% | snow_don_70.png |
| More than 50% up to 60% | snow_don_60.png |
| More than 40% up to 50% | snow_don_50.png |
| More than 30% up to 40% | snow_don_40.png |
| More than 20% up to 30% | snow_don_30.png |
| More than 10% up to 20% | snow_don_20.png |
| 0% up to 10% | snow_don_10.png; DEFEATED at 0 HP |

For example, at **133 / 150 HP**, the game selects **snow_don_90.png**;
when HP drops to **120 / 150**, it switches to **snow_don_80.png**.
The boss's visual stages progress automatically, with no extra database field.
The same stage appears in the boss's health screen and the result after an attack.

## Import your original transparent artwork ZIP

The pre-created **Snow_Don_Health_Transparent.zip** from the earlier Snow Don
artwork conversation is *not present in the repository or this coding session*.
No replacement character imagery has been substituted for it. **You must
install that existing ZIP once** before the new portrait graphics will appear.

Copy the ZIP to the PyCharm Operation-Snowfall project root (alongside `bot.py`).
From the activated project's PowerShell terminal:

```powershell
python -m snowfall.graphics.snow_don .\Snow_Don_Health_Transparent.zip
```

The installer validates **all ten transparent PNGs** before copying them to
`src/snowfall/graphics/art/boss/` and rejects partial/opaque packs. The folder
must contain `snow_don_100.png`, `snow_don_90.png`, ..., `snow_don_10.png`.
No path in the original ZIP is extracted directly, avoiding ZIP path traversal.

For deployment on another machine, commit those ten original images into the
repo (or install the same ZIP there). The Python package automatically includes
all installed boss images when built.

If images are missing or corrupt, the old safe fallback icon is used for that
card; scoring continues to work. The siege retains its existing artwork.

## Install update / test

```powershell
git pull origin main
python -m pip install -e ".[dev]"
python -m pytest -q
python -m snowfall.graphics.snow_don .\Snow_Don_Health_Transparent.zip
python bot.py
```

In Discord: `/snow menu` → Game Menus → Snow Don / City Siege.
From the Admin / Test panel, start a disposable rehearsal day and hit the boss;
refresh the warzone card after a hit to see the current stage. At 0 HP the
last damaged image is accompanied by a defeated label. No test data carries
into the real event.

## Automated verification

Tests cover integer threshold boundaries (including non-round max HP),
complete ZIP validation and rejection, stage-specific pixels in both card
renderers, unchanged siege graphics, missing-art fallback and no scoring
mutations. Existing Windows, Linux and Discord UI tests remain in CI.
