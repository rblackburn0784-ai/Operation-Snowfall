"""v2.9.0a: every Pack A–J PNG/WebP must be used by a renderer path."""
from pathlib import Path
from snowfall.graphics.art_coverage_v290a import audit


def test_every_art_asset_has_executed_renderer_path():
    project=Path(__file__).resolve().parents[1]
    result=audit(project)
    assert not result['uncovered']
    assert not result['unrecognized_paths']
    assert result['covered_assets']==result['expected_assets']==111
