"""v2.9.9h — validate the deployable wheel includes EVERY arcade UI module.

A source-tree test can pass while Railway's installed Python wheel omits a
new static file. This gate checks the built artifact itself, without running
a web server, touching the database or performing any remote requests.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

STATIC = "snowfall/platform/static/"
ART = "snowfall/graphics/art/v290/arcade/"
GAME_MODULES = (
    "arcade-v299.js", "arcade-gallery-v299a.js", "arcade-safe-v299b.js",
    "arcade-snowman-v299c.js", "arcade-catch-v299d.js",
    "arcade-trivia-v299e.js", "arcade-hub-v299f.js",
)
GAME_ART = ("gallery.webp", "safe.webp", "snowman.webp", "catch.webp",
            "trivia.webp")


def verify(output: Path) -> dict:
    wheels = list(output.glob("operation_snowfall-*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one built Operation Snowfall wheel")
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        required = {
            *(STATIC + name for name in GAME_MODULES),
            STATIC + "app.js", STATIC + "app.css",
            STATIC + "index.html",
            STATIC + "adventure-office.svg", STATIC + "adventure-alley.svg",
            *(ART + name for name in GAME_ART),
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError("Wheel missing arcade deployment assets: " +
                             ", ".join(missing))
        page = wheel.read(STATIC + "index.html").decode("utf-8")
        if 'name="snowfall-interactive-arcade-release" content="2.9.10"' not in page:
            raise ValueError("Built arcade HTML has a stale release stamp")
        if 'name="snowfall-adventure-release" content="2.9.10"' not in page:
            raise ValueError("Built adventure HTML has a stale release stamp")
        for name in ("adventure-office.svg", "adventure-alley.svg"):
            if b"<svg" not in wheel.read(STATIC + name):
                raise ValueError("Invalid bundled adventure art: " + name)
        for name in GAME_MODULES:
            if "/static/" + name not in page:
                raise ValueError("Game module missing from entrypoint: " + name)
            if len(wheel.read(STATIC + name)) < 300:
                raise ValueError("Game module empty or truncated: " + name)
        for name in GAME_ART:
            data = wheel.read(ART + name)
            if not data.startswith(b"RIFF") or data[8:12] != b"WEBP":
                raise ValueError("Invalid bundled arcade art: " + name)
        if len(wheel.read(STATIC + "app.css")) < 2000:
            raise ValueError("Arcade stylesheet appears truncated")
        if len(wheel.read(STATIC + "app.js")) < 3000:
            raise ValueError("Arcade website controller appears truncated")
    return {
        "wheel": wheels[0].name, "modules": len(GAME_MODULES),
        "arcade_art": len(GAME_ART), "release": "2.9.10",
    }


if __name__ == "__main__":
    try:
        report = verify(Path(sys.argv[1] if len(sys.argv) > 1 else "output/wheels"))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from None
    print("PASS:", report["release"], report["modules"],
          "arcade JavaScript modules and", report["arcade_art"],
          "artworks bundled in", report["wheel"])
