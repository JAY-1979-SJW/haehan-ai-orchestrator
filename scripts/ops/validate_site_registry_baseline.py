"""Validate the official site automation registry baseline."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "configs" / "site_automation_status_index.json"
SITE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("registry root must be an object")
    return data


def _as_set(contract: dict[str, Any], key: str) -> set[str]:
    values = contract.get(key)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError(f"registry_contract.{key} must be a string list")
    return set(values)


def _require_string_list(site: dict[str, Any], field: str, errors: list[str]) -> list[str]:
    values = site.get(field)
    site_id = site.get("site_id", "<missing>")
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        errors.append(f"{site_id}: {field} must be a string list")
        return []
    return values


def _check_site_id(site, errors, seen_site_ids):
    site_id = site.get("site_id")
    if not isinstance(site_id, str) or not SITE_ID_PATTERN.match(site_id):
        errors.append(f"{site_id or '<missing>'}: site_id must be snake_case")
        site_id = str(site_id or "<missing>")
    if site_id in seen_site_ids:
        errors.append(f"{site_id}: duplicated site_id")
    seen_site_ids.add(site_id)
    return site_id


def _check_required(site, site_id, required_fields, errors):
    missing = sorted(field for field in required_fields if field not in site)
    if missing:
        errors.append(f"{site_id}: missing required fields {', '.join(missing)}")

    for field in (
        "display_name",
        "category",
        "status",
        "execution_policy",
        "login_policy",
        "risk_level",
        "owner_module",
    ):
        if not isinstance(site.get(field), str) or not site.get(field):
            errors.append(f"{site_id}: {field} must be a non-empty string")


def _check_enums(site, site_id, status_values, execution_values, login_values, risk_values, errors):  # noqa: PLR0913 - validate_registry 누적 상태를 그대로 넘기는 private 헬퍼(동작 불변 분리)
    if site.get("status") not in status_values:
        errors.append(f"{site_id}: invalid status {site.get('status')!r}")
    if site.get("execution_policy") not in execution_values:
        errors.append(f"{site_id}: invalid execution_policy {site.get('execution_policy')!r}")
    if site.get("login_policy") not in login_values:
        errors.append(f"{site_id}: invalid login_policy {site.get('login_policy')!r}")
    if site.get("risk_level") not in risk_values:
        errors.append(f"{site_id}: invalid risk_level {site.get('risk_level')!r}")


def _check_tools_tests(site, site_id, errors):
    tools = _require_string_list(site, "tools", errors)
    tests = _require_string_list(site, "tests", errors)
    _require_string_list(site, "domains", errors)
    _require_string_list(site, "notes", errors)

    if site.get("status") in {"active", "partial", "cataloged"} and not tools:
        errors.append(f"{site_id}: status {site.get('status')} requires at least one tool")
    if site.get("status") in {"active", "partial", "cataloged"} and not tests:
        errors.append(f"{site_id}: status {site.get('status')} requires at least one test")
    return tools


def _collect_script_dirs(site, tools, covered_script_dirs):
    owner_module = str(site.get("owner_module", ""))
    for path_value in [owner_module, *tools]:
        if path_value.startswith("scripts/"):
            parts = Path(path_value).parts
            if len(parts) >= 2:
                covered_script_dirs.add(parts[1])


def validate_registry(path: Path = REGISTRY_PATH) -> tuple[bool, list[str], dict[str, Any]]:
    data = _load_registry(path)
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != 2:
        errors.append("schema_version must be 2")

    contract = data.get("registry_contract")
    if not isinstance(contract, dict):
        errors.append("registry_contract must be present")
        contract = {}

    required_fields = _as_set(contract, "required_fields") if contract else set()
    status_values = _as_set(contract, "status_values") if contract else set()
    execution_values = _as_set(contract, "execution_policy_values") if contract else set()
    login_values = _as_set(contract, "login_policy_values") if contract else set()
    risk_values = _as_set(contract, "risk_level_values") if contract else set()
    required_dirs = _as_set(contract, "script_dirs_requiring_registry") if contract else set()

    sites = data.get("sites")
    if not isinstance(sites, list):
        errors.append("sites must be a list")
        sites = []

    seen_site_ids: set[str] = set()
    covered_script_dirs: set[str] = set()

    for site in sites:
        if not isinstance(site, dict):
            errors.append("each site must be an object")
            continue

        site_id = _check_site_id(site, errors, seen_site_ids)

        _check_required(site, site_id, required_fields, errors)

        _check_enums(site, site_id, status_values, execution_values, login_values, risk_values, errors)

        tools = _check_tools_tests(site, site_id, errors)

        _collect_script_dirs(site, tools, covered_script_dirs)

    missing_dirs = sorted(required_dirs - covered_script_dirs)
    if missing_dirs:
        errors.append("script directories missing registry coverage: " + ", ".join(missing_dirs))

    result = {
        "site_count": len(seen_site_ids),
        "required_script_dirs": sorted(required_dirs),
        "covered_script_dirs": sorted(covered_script_dirs & required_dirs),
        "warnings": warnings,
    }
    return not errors, errors, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable validation output")
    args = parser.parse_args(argv)

    ok, errors, result = validate_registry()
    if args.json:
        print(json.dumps({"ok": ok, "errors": errors, **result}, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] site registry baseline")
        print(f"site_count={result['site_count']}")
        print("covered_script_dirs=" + ",".join(result["covered_script_dirs"]))
        for error in errors:
            print(f"ERROR: {error}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
