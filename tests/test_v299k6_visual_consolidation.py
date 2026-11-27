from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "src/snowfall/graphics/art/v290/arcade"
STATIC = ROOT / "src/snowfall/platform/static"

def test_consolidated_artwork():
    expected = {
        "v299k1": ["trivia-stage.webp"] + [f"trivia-answer-{c}.webp" for c in ("blue","red","gold","green")],
        "v299k2": ["gallery-stage.webp"] + [f"gallery-{k}.webp" for k in ("standard","gold","decoy","impact")] + [f"gallery-{k}-{i}.webp" for k in ("standard","gold","decoy","impact") for i in range(9 if k=="impact" else 6)],
        "v299k3": ["safe-stage.webp","safe-panel.webp","safe-wheel.webp"],
        "v299k4": ["catch-stage.webp"] + [f"catch-{k}-{i}.webp" for k in ("white","gold","crystal","hazard","basket") for i in range(6)],
        "v299k5": ["snowman-stage.webp"] + [f"snowman-{k}{suffix}.webp" for k in ("base","torso","head","hat","scarf","nose","arm_left","arm_right","buttons","sunhat","beachball") for suffix in [""]+[f"-{i}" for i in range(6)]],
    }
    from PIL import Image
    for folder, names in expected.items():
        for name in names:
            path = ART / folder / name
            assert path.is_file(), str(path)
            with Image.open(path) as img:
                assert img.format == "WEBP", str(path)
                img.verify()

def test_release_cache_versions():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    import re
    scripts = re.findall(r'/static/arcade-[^"]+\.js\?v=([^"]+)', html)
    assert len(scripts) == 7
    assert scripts.count("299k7a") == 5
    assert scripts.count("299k8") == 2
