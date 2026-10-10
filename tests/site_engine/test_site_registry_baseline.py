from __future__ import annotations

from scripts.site_engine.validate_site_registry_baseline import validate_registry


def test_site_registry_baseline_passes() -> None:
    ok, errors, result = validate_registry()

    assert ok, errors
    assert result["site_count"] >= 10


def test_site_registry_covers_current_site_script_dirs() -> None:
    ok, errors, result = validate_registry()

    assert ok, errors
    assert set(result["required_script_dirs"]).issubset(set(result["covered_script_dirs"]))
