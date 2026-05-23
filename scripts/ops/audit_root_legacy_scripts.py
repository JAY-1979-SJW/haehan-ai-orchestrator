"""Audit root-level Python legacy residuals.

This is a read-only guard. It does not move, delete, or rewrite files.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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


def audit(root: Path = ROOT, config_path: Path = CONFIG) -> list[Finding]:
    findings: list[Finding] = []
    if not config_path.exists():
        return [Finding("FAIL", "CONFIG_MISSING", normalize(config_path.relative_to(root)))]

    config = load_config(config_path)
    scripts = config.get("scripts")
    allowed_categories = set(config.get("allowed_categories") or [])
    if config.get("schema_version") != 1:
        findings.append(Finding("FAIL", "SCHEMA_VERSION", "schema_version must be 1"))
    if config.get("status") != "locked":
        findings.append(Finding("FAIL", "STATUS_UNLOCKED", "status must be locked"))
    if not isinstance(scripts, list):
        findings.append(Finding("FAIL", "SCRIPTS_SCHEMA", "scripts must be a list"))
        scripts = []

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

    duplicates = sorted({path for path in configured if configured.count(path) > 1})
    for path in duplicates:
        findings.append(Finding("FAIL", "DUPLICATE_ENTRY", path))

    actual = set(root_python_files(root))
    configured_set = set(configured)
    for path in sorted(actual - configured_set):
        findings.append(Finding("FAIL", "UNCLASSIFIED_ROOT_SCRIPT", path))
    for path in sorted(configured_set - actual):
        findings.append(Finding("FAIL", "MISSING_ROOT_SCRIPT", path))

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
