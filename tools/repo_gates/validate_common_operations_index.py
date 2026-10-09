"""Validate the common operations index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
INDEX_PATH = ROOT / "configs" / "common_operations_index.json"


def _load_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_site(errors, seen, index, site):
    if not isinstance(site, dict):
        errors.append(f"sites[{index}] must be an object")
        return
    site_id = str(site.get("site_id") or "")
    if not site_id:
        errors.append(f"sites[{index}].site_id is required")
    elif site_id in seen:
        errors.append(f"duplicate site_id: {site_id}")
    seen.add(site_id)

    for field in ("label", "owner", "status"):
        if not site.get(field):
            errors.append(f"{site_id or index}.{field} is required")

    for field in ("reference_docs", "primary_artifacts", "next_actions"):
        value = site.get(field)
        if not isinstance(value, list):
            errors.append(f"{site_id or index}.{field} must be a list")


def validate_index(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not data.get("updated_at"):
        errors.append("updated_at is required")

    sites = data.get("sites")
    if not isinstance(sites, list) or not sites:
        errors.append("sites must be a non-empty list")
        return errors

    seen: set[str] = set()
    for index, site in enumerate(sites):
        _validate_site(errors, seen, index, site)

    gates = data.get("global_gates")
    if not isinstance(gates, list) or not gates:
        errors.append("global_gates must be a non-empty list")

    return errors


def main() -> int:
    data = _load_index()
    errors = validate_index(data)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print(f"[OK] common operations index: {INDEX_PATH}")
    print(f"[OK] sites: {len(data['sites'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
