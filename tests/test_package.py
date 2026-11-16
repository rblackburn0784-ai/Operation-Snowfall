"""The combat service must be included in the built distribution, not just pytest's src path."""
from setuptools import find_packages


def test_combat_package_is_distributable():
    names = find_packages(where="src")
    assert "snowfall" in names
    assert "snowfall.services" in names
    assert "snowfall.ui" in names
