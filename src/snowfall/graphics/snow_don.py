"""Snow Don's health-stage portraits (100% to 10%) and safe ZIP importer.

The source images are supplied separately by the organiser. The renderer works
without them, but never fabricates a different character or changes game data.
"""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError

STAGES = tuple(range(100, 0, -10))
PORTRAITS = Path(__file__).resolve().parent / "art" / "boss"
MAX_BYTES_PER_PORTRAIT = 15_000_000
MAX_DIMENSION = 4096


def health_stage(remaining_hp: int, max_hp: int) -> int:
    """Choose the portrait for health *remaining*, in 10% downward bands.

    91-100% -> 100; 81-90% -> 90; 71-80% -> 80; and so on.
    The next damaged portrait appears when a 10% HP threshold is crossed.
    0-10%/defeated -> 10, the most damaged existing portrait.
    Integer division avoids float-rounding changes at the thresholds.
    """
    maximum = int(max_hp)
    remaining = int(remaining_hp)
    if maximum <= 0:
        return 10 if remaining <= 0 else 100
    remaining = max(0, min(remaining, maximum))
    return max(10, ((remaining * 10 + maximum - 1) // maximum) * 10)


def portrait_path(stage: int, directory: Path | None = None) -> Path | None:
    """Return the exact stage PNG if installed; do not pretend to use another stage."""
    if stage not in STAGES:
        return None
    candidate = (directory or PORTRAITS) / f"snow_don_{stage}.png"
    return candidate if candidate.is_file() else None


def draw_portrait(canvas: Image.Image, remaining_hp: int, max_hp: int,
                  box: tuple[int, int, int, int], *, directory: Path | None = None) -> int | None:
    """Alpha-composite the original portrait into the right-side card space.

    Returns the artwork stage actually drawn, or None so the caller can fall back
    to the legacy small boss icon. Read errors never affect saved attack results.
    """
    stage = health_stage(remaining_hp, max_hp)
    path = portrait_path(stage, directory)
    if path is None:
        return None
    try:
        if path.stat().st_size > MAX_BYTES_PER_PORTRAIT:
            return None
        with Image.open(path) as source:
            if source.width > MAX_DIMENSION or source.height > MAX_DIMENSION:
                return None
            portrait = source.convert("RGBA")
        alpha_bounds = portrait.getchannel("A").getbbox()
        if alpha_bounds is None:
            return None
        portrait = portrait.crop(alpha_bounds)
        x, y, right, bottom = box
        width, height = right - x, bottom - y
        if width <= 0 or height <= 0:
            return None
        portrait.thumbnail((width, height), Image.Resampling.LANCZOS)
        center_x = x + (width - portrait.width) // 2
        bottom_y = bottom - portrait.height
        canvas.alpha_composite(portrait, (center_x, bottom_y))
        return stage
    except (OSError, ValueError, UnidentifiedImageError):
        return None


def install_portraits(archive: Path | str, directory: Path | None = None) -> tuple[Path, ...]:
    """Import the *existing* Snow_Don_Health_Transparent.zip safely.

    All ten files are validated before writing. A bad or incomplete ZIP is
    refused rather than silently loading a different image for a health stage.
    """
    archive = Path(archive)
    destination = directory or PORTRAITS
    imported: dict[int, bytes] = {}
    try:
        with ZipFile(archive) as zipped:
            for info in zipped.infolist():
                filename = Path(info.filename).name.lower()
                for stage in STAGES:
                    if filename != f"snow_don_{stage}.png":
                        continue
                    if stage in imported:
                        raise ValueError(f"Duplicate artwork for {stage}% health")
                    if info.file_size > MAX_BYTES_PER_PORTRAIT:
                        raise ValueError(f"{filename} is too large")
                    data = zipped.read(info)
                    if len(data) > MAX_BYTES_PER_PORTRAIT:
                        raise ValueError(f"{filename} is too large")
                    # Pillow requires verify() immediately after opening; it
                    # cannot run after converting or loading the image pixels.
                    with Image.open(BytesIO(data)) as check:
                        if check.format != "PNG":
                            raise ValueError(f"{filename} must be PNG")
                        if check.width > MAX_DIMENSION or check.height > MAX_DIMENSION:
                            raise ValueError(f"{filename} is too large in pixels")
                        check.verify()
                    with Image.open(BytesIO(data)) as image:
                        if image.convert("RGBA").getchannel("A").getextrema()[0] == 255:
                            raise ValueError(f"{filename} needs a transparent background")
                    imported[stage] = data
    except (OSError, BadZipFile, UnidentifiedImageError) as exc:
        raise ValueError(f"Could not read Snow Don artwork ZIP: {exc}") from exc
    missing = set(STAGES) - imported.keys()
    if missing:
        raise ValueError(f"Missing Snow Don portraits: {', '.join(f'{n}%' for n in sorted(missing, reverse=True))}")
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for stage in STAGES:
        path = destination / f"snow_don_{stage}.png"
        path.write_bytes(imported[stage])
        paths.append(path)
    return tuple(paths)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install the ten transparent Snow Don damage portraits")
    parser.add_argument("zip", type=Path, help="Snow_Don_Health_Transparent.zip from your previous artwork download")
    args = parser.parse_args(argv)
    try:
        files = install_portraits(args.zip)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Installed {len(files)} Snow Don portraits to {PORTRAITS}")
    print("Restart the bot (or refresh a card) to see his current health-stage artwork.")


if __name__ == "__main__":
    main()
