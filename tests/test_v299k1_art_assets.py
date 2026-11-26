"""v2.9.9k1 packaging gates: artwork is mandatory before staging launch."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src/snowfall/graphics/art/v290/arcade/v299k1"

def test_trivia_approved_artwork_is_packaged():
    expected = {
        "trivia-stage.webp": 1,
        "trivia-answer-blue.webp": 6,
        "trivia-answer-red.webp": 6,
        "trivia-answer-gold.webp": 6,
        "trivia-answer-green.webp": 6,
    }
    missing = [name for name in expected if not (ASSETS / name).is_file()]
    assert not missing, "Missing v2.9.9k1 approved artwork: " + ", ".join(missing)
    from PIL import Image
    for name, frames in expected.items():
        with Image.open(ASSETS / name) as image:
            assert image.format == "WEBP", name
            assert getattr(image, "n_frames", 1) == frames, name
            assert image.width >= 270 and image.height >= 60, name
