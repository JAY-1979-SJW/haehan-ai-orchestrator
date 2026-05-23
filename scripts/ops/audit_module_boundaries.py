"""Audit the locked module boundary map."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "module_boundaries.json"
DOC = ROOT / "docs" / "architecture" / "module_boundary_map_20260523.md"


@dataclass(frozen=True)
class Finding:
    status: str
    item: str
    detail: str


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _path_exists(path: str) -> bool:
    rel = _normalize(path)
    return (ROOT / rel).exists()


def audit() -> list[Finding]:
    findings: list[Finding] = []
    if not CONFIG.exists():
        return [Finding("FAIL", "config", "configs/module_boundaries.json missing")]
    if not DOC.exists():
        findings.append(Finding("FAIL", "doc", "module boundary map doc missing"))

    config = _load_config()
    if config.get("status") == "locked":
        findings.append(Finding("PASS", "status", "locked"))
    else:
        findings.append(Finding("FAIL", "status", "module boundary config must be locked"))

    modules = config.get("modules") or []
    names = [str(module.get("name", "")) for module in modules]
    required_names = {
        "repo_guard",
        "local_agent_browser_runtime",
        "desktop_runtime",
        "admin_web",
        "portable_install",
        "server_api",
        "site_automation",
        "legacy_root_quarantine",
    }
    missing_names = sorted(required_names - set(names))
    if missing_names:
        findings.append(Finding("FAIL", "modules", "missing: " + ", ".join(missing_names)))
    else:
        findings.append(Finding("PASS", "modules", f"{len(modules)} modules registered"))

    seen_paths: dict[str, str] = {}
    overlaps: list[str] = []
    for module in modules:
        name = str(module.get("name", ""))
        if not module.get("owner") or not module.get("layer") or not module.get("required_gate"):
            findings.append(Finding("FAIL", f"module:{name}", "owner/layer/required_gate required"))
        for path in module.get("paths") or []:
            rel = _normalize(str(path))
            if rel in seen_paths:
                overlaps.append(f"{rel} in {seen_paths[rel]} and {name}")
            seen_paths[rel] = name
            if not _path_exists(rel):
                findings.append(Finding("FAIL", f"path:{rel}", f"missing for module {name}"))
    if overlaps:
        findings.append(Finding("FAIL", "path_overlaps", "; ".join(overlaps)))
    else:
        findings.append(Finding("PASS", "path_overlaps", "none"))

    workflow_dir = ROOT / ".github" / "workflows"
    workflow_files = []
    if workflow_dir.exists():
        workflow_files = [p.name for p in workflow_dir.iterdir() if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}]
    if workflow_files:
        findings.append(Finding("FAIL", "github_actions_disabled", ", ".join(sorted(workflow_files))))
    else:
        findings.append(Finding("PASS", "github_actions_disabled", "no workflow files"))

    archive_state = ROOT / "scripts" / "archive" / "data" / "chrome_ui_monitor_state.json"
    if archive_state.exists() and archive_state.stat().st_size != 120:
        findings.append(Finding("FAIL", "archive_runtime_state", "archive chrome monitor state changed shape"))
    else:
        findings.append(Finding("PASS", "archive_runtime_state", "not active runtime target"))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = audit()
    failed = [finding for finding in findings if finding.status == "FAIL"]
    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], ensure_ascii=False, indent=2))
    else:
        for finding in findings:
            print(f"[{finding.status}] {finding.item}: {finding.detail}")
        print(f"RESULT={'PASS_MODULE_BOUNDARY_AUDIT' if not failed else 'FAIL_MODULE_BOUNDARY_AUDIT'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
