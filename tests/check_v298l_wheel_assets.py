"""Verify the BUILT distribution ships the new resource art, not just the Git checkout.

The Railway website imports snowfall.graphics from the installed package.
The v2.9.8l source-tree tests passed while its wheel omitted new PNG/WebP
package-data, causing HTTP 404s in the live staging container.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

if __name__ == "__main__":
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "output/wheels")
    packages = list(output.glob("operation_snowfall-*.whl"))
    if len(packages) != 1:
        raise SystemExit(f"Expected exactly one built Snowfall wheel in {output}; found {len(packages)}")
    required = {
        f"snowfall/graphics/art/v290/status/v298l/{kind}_{number}.webp"
        for kind in ("snowballs", "warmth", "cold", "currency", "points")
        for number in range(1, 5)
    }
    required.add("snowfall/graphics/art/v290/status/v298l/winter_street.webp")
    with zipfile.ZipFile(packages[0]) as wheel:
        names = set(wheel.namelist())
        missing = sorted(required - names)
        if missing:
            raise SystemExit("Wheel package-data missing original status artwork: " + ", ".join(missing))
        for name in sorted(required):
            content = wheel.read(name)
            if content[:4] != b"RIFF" or content[8:12] != b"WEBP" or len(content) <= 3000:
                raise SystemExit(f"Invalid WebP payload inside wheel: {name}")
        # Preserve a known old image to catch accidental narrowing of the art list.
        old = "snowfall/graphics/art/v290/cosmetics/gear/scarf_worn.png"
        if old not in names:
            raise SystemExit("Previous equipped-scarf artwork was lost during packaging")
    print(f"PASS: {len(required)} current status illustrations + existing scarf asset in {packages[0].name}")
