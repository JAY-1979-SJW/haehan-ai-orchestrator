"""Audit residual UI surfaces before desktop release.

The goal is to distinguish active UI entrypoints from legacy UI that must not
return and from local generated artifacts that should stay out of release
packages. This script is intentionally read-only.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LEGACY_UI_FORBIDDEN = (
    "desktop/tray_app.py",
    "desktop/webview_app.py",
    "desktop/webview_app_pywebview.py",
    "desktop/ui",
    "desktop/electron",
)

ACTIVE_UI_REQUIRED = (
    "admin-web/package.json",
    "admin-web/src/app/layout.tsx",
    "admin-web/src/app/page.tsx",
    "desktop/local_server.py",
    "desktop/ui_dist/index.html",
    "desktop/ui_new/shell_html.py",
    "desktop/admin_webview.py",
)

FALLBACK_UI_ALLOWED = (
    "ai_orchestrator/admin_ui_router.py",
    "local_agent/user_present_ui_server.py",
)

API_BACKED_APPROVAL_UI = {
    "ai_orchestrator/local_agent/browser/approval_server.py": (
        "approval_api_client",
        "HAEHAN_LOCAL_APPROVAL_UI_FALLBACK",
    ),
}

GENERATED_RESIDUE_WARN = (
    "admin-web/.next",
    "admin-web/node_modules",
    "admin-web/vendor/@haehan/design-system/node_modules",
    "desktop/__pycache__",
    "desktop/ui_new/__pycache__",
)

EMPTY_RESIDUE_WARN = (
    "desktop/local_ui",
)


@dataclass(frozen=True)
class Finding:
    status: str
    path: str
    detail: str


def repo_path(rel: str) -> Path:
    return ROOT / rel


def normalize(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def has_files(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(child.is_file() for child in path.rglob("*"))


def audit() -> list[Finding]:
    findings: list[Finding] = []

    for rel in LEGACY_UI_FORBIDDEN:
        path = repo_path(rel)
        if path.exists():
            findings.append(Finding("FAIL", rel, "forbidden legacy UI path exists"))
        else:
            findings.append(Finding("PASS", rel, "legacy UI path absent"))

    for rel in ACTIVE_UI_REQUIRED:
        path = repo_path(rel)
        if path.exists():
            findings.append(Finding("PASS", rel, "active UI entrypoint present"))
        else:
            findings.append(Finding("FAIL", rel, "active UI entrypoint missing"))

    for rel in FALLBACK_UI_ALLOWED:
        path = repo_path(rel)
        if path.exists():
            findings.append(Finding("WARN", rel, "allowed fallback/approval UI; remove only after API replacement"))

    for rel, markers in API_BACKED_APPROVAL_UI.items():
        path = repo_path(rel)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if all(marker in text for marker in markers):
            findings.append(Finding("PASS", rel, "API approval is default; local UI requires explicit fallback env"))
        else:
            findings.append(Finding("WARN", rel, "approval UI still lacks default API approval path"))

    for rel in GENERATED_RESIDUE_WARN:
        path = repo_path(rel)
        if path.exists():
            findings.append(Finding("WARN", rel, "local generated artifact; keep ignored and exclude from packages"))

    for rel in EMPTY_RESIDUE_WARN:
        path = repo_path(rel)
        if path.exists():
            detail = "empty local residue dir" if not has_files(path) else "local residue dir contains files"
            findings.append(Finding("WARN", rel, detail))

    return findings


def summarize(findings: list[Finding]) -> tuple[str, int, int, int]:
    failed = sum(1 for finding in findings if finding.status == "FAIL")
    warned = sum(1 for finding in findings if finding.status == "WARN")
    passed = sum(1 for finding in findings if finding.status == "PASS")
    result = "FAIL_UI_RESIDUE_AUDIT" if failed else "PASS_UI_RESIDUE_AUDIT"
    return result, passed, warned, failed


def print_report(findings: list[Finding]) -> None:
    for finding in findings:
        print(f"[{finding.status}] {finding.path} - {finding.detail}")
    result, passed, warned, failed = summarize(findings)
    print(f"RESULT={result} passed={passed} warned={warned} failed={failed}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit active, fallback, and residual UI paths")
    parser.add_argument("--strict-warn", action="store_true", help="treat WARN findings as process failures")
    args = parser.parse_args(argv)

    findings = audit()
    print_report(findings)
    result, _, warned, failed = summarize(findings)
    if failed or (args.strict_warn and warned):
        return 1
    return 0 if result == "PASS_UI_RESIDUE_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
