from pathlib import Path
import sys
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1] / "src"
expected = {p.relative_to(root).as_posix() for p in root.glob("snowfall/graphics/art/v290/arcade/v299k*/*.webp")}
assert len(expected) == 149, len(expected)
wheel, = Path(sys.argv[1]).glob("operation_snowfall-*.whl")
with ZipFile(wheel) as archive:
    missing = expected - set(archive.namelist())
    assert not missing, sorted(missing)
    assert all(archive.getinfo(p).file_size > 0 for p in expected)
print("All 149 arcade assets packaged")
