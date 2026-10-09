"""Audit root-level Python legacy residuals.

This is a read-only guard. It does not move, delete, or rewrite files.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
CONFIG = ROOT / "configs" / "root_legacy_scripts.json"


@dataclass(frozen=True)
class Finding:
    status: str
    code: str
    detail: str


def normalize(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def root_python_files(root: Path = ROOT) -> list[str]:
    return sorted(path.name for path in root.glob("*.py") if path.is_file())


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_config_schema(config: dict) -> tuple[list[Finding], list]:
    findings: list[Finding] = []
    scripts = config.get("scripts")
    if config.get("schema_version") != 1:
        findings.append(Finding("FAIL", "SCHEMA_VERSION", "schema_version must be 1"))
    if config.get("status") != "locked":
        findings.append(Finding("FAIL", "STATUS_UNLOCKED", "status must be locked"))
    if not isinstance(scripts, list):
        findings.append(Finding("FAIL", "SCRIPTS_SCHEMA", "scripts must be a list"))
        scripts = []
    return findings, scripts


def _validate_script_entries(scripts: list, allowed_categories: set) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    configured: list[str] = []
    for index, item in enumerate(scripts):
        path = str(item.get("path", ""))
        category = str(item.get("category", ""))
        next_action = str(item.get("next_action", ""))
        if not path.endswith(".py") or "/" in path or "\\" in path:
            findings.append(Finding("FAIL", "INVALID_PATH", f"scripts[{index}] path={path!r}"))
            continue
        configured.append(path)
        if category not in allowed_categories:
            findings.append(Finding("FAIL", "INVALID_CATEGORY", f"{path}: {category!r}"))
        if not next_action:
            findings.append(Finding("FAIL", "MISSING_NEXT_ACTION", path))
    return findings, configured


def _check_duplicate_entries(configured: list[str]) -> list[Finding]:
    duplicates = sorted({path for path in configured if configured.count(path) > 1})
    return [Finding("FAIL", "DUPLICATE_ENTRY", path) for path in duplicates]


def _check_root_script_set_matches(actual: set, configured_set: set) -> list[Finding]:
    findings = [Finding("FAIL", "UNCLASSIFIED_ROOT_SCRIPT", path) for path in sorted(actual - configured_set)]
    findings += [Finding("FAIL", "MISSING_ROOT_SCRIPT", path) for path in sorted(configured_set - actual)]
    return findings


def audit(root: Path = ROOT, config_path: Path = CONFIG) -> list[Finding]:
    # 2026-09-29 STD-08(복잡도) 리팩터: 독립 검증 단계를 _validate_*()/_check_*() 함수로 분리
    # (순서·조건·문자열 그대로) — #48 과 같은 계열.
    if not config_path.exists():
        return [Finding("FAIL", "CONFIG_MISSING", normalize(config_path.relative_to(root)))]

    config = load_config(config_path)
    allowed_categories = set(config.get("allowed_categories") or [])
    findings, scripts = _validate_config_schema(config)

    entry_findings, configured = _validate_script_entries(scripts, allowed_categories)
    findings.extend(entry_findings)
    findings.extend(_check_duplicate_entries(configured))

    actual = set(root_python_files(root))
    configured_set = set(configured)
    findings.extend(_check_root_script_set_matches(actual, configured_set))

    if not any(finding.status == "FAIL" for finding in findings):
        findings.append(Finding("PASS", "ROOT_LEGACY_LOCKED", f"{len(actual)} root scripts classified"))
    return findings


def print_report(findings: list[Finding]) -> None:
    for finding in findings:
        print(f"[{finding.status}] {finding.code} - {finding.detail}")
    failed = sum(1 for finding in findings if finding.status == "FAIL")
    print(f"RESULT={'FAIL_ROOT_LEGACY_SCRIPT_AUDIT' if failed else 'PASS_ROOT_LEGACY_SCRIPT_AUDIT'} failed={failed}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit classified root-level Python legacy scripts")
    parser.parse_args(argv)
    findings = audit()
    print_report(findings)
    return 1 if any(finding.status == "FAIL" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
