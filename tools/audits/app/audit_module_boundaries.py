"""Audit the locked module boundary map."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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


def _check_status_locked(config: dict) -> Finding:
    if config.get("status") == "locked":
        return Finding("PASS", "status", "locked")
    return Finding("FAIL", "status", "module boundary config must be locked")


def _check_required_module_names(modules: list) -> Finding:
    names = [str(module.get("name", "")) for module in modules]
    required_names = {
        "repo_guard",
        "local_agent_browser_runtime",
        "desktop_runtime",
        "admin_web",
        "server_api",
        "site_automation",
        "legacy_root_quarantine",
    }
    missing_names = sorted(required_names - set(names))
    if missing_names:
        return Finding("FAIL", "modules", "missing: " + ", ".join(missing_names))
    return Finding("PASS", "modules", f"{len(modules)} modules registered")


def _check_module_entries_and_paths(modules: list) -> list[Finding]:
    findings: list[Finding] = []
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
    return findings


def _check_github_actions_disabled(config: dict) -> Finding:
    # 2026-09-29 수정(defect_index.json 참고): "GitHub 기능 안 씀" 결정이 커밋 a941e09a
    # (사용자 승인)로 번복돼 .github/workflows/ci.yml 이 정식 도입됐는데, 이 검사가
    # 갱신 안 돼 항상 FAIL을 내고 있었음. 전면 금지 대신 승인된 파일만 허용하는
    # 화이트리스트로 변경 — configs/module_boundaries.json 의 allowed_exceptions.
    workflow_dir = ROOT / ".github" / "workflows"
    workflow_files = []
    if workflow_dir.exists():
        workflow_files = [
            p.name for p in workflow_dir.iterdir() if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}
        ]
    allowed: set[str] = set()
    for rule in config.get("forbidden_cross_boundary") or []:
        if rule.get("rule") == "github_actions_disabled":
            allowed = set(rule.get("allowed_exceptions") or [])
            break
    unexpected = sorted(set(workflow_files) - allowed)
    if unexpected:
        return Finding("FAIL", "github_actions_disabled", ", ".join(unexpected))
    if workflow_files:
        return Finding("PASS", "github_actions_disabled", f"approved only: {', '.join(sorted(workflow_files))}")
    return Finding("PASS", "github_actions_disabled", "no workflow files")


def _check_archive_runtime_state() -> Finding:
    archive_state = ROOT / "scripts" / "archive" / "data" / "chrome_ui_monitor_state.json"
    if archive_state.exists() and archive_state.stat().st_size != 120:
        return Finding("FAIL", "archive_runtime_state", "archive chrome monitor state changed shape")
    return Finding("PASS", "archive_runtime_state", "not active runtime target")


def audit() -> list[Finding]:
    # 2026-09-29 STD-08(복잡도) 리팩터: 독립 체크들을 _check_*() 함수로 분리(순서·조건·문자열
    # 그대로) — #48 과 같은 계열.
    findings: list[Finding] = []
    if not CONFIG.exists():
        return [Finding("FAIL", "config", "configs/module_boundaries.json missing")]
    if not DOC.exists():
        findings.append(Finding("FAIL", "doc", "module boundary map doc missing"))

    config = _load_config()
    findings.append(_check_status_locked(config))

    modules = config.get("modules") or []
    findings.append(_check_required_module_names(modules))
    findings.extend(_check_module_entries_and_paths(modules))
    findings.append(_check_github_actions_disabled(config))
    findings.append(_check_archive_runtime_state())

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
