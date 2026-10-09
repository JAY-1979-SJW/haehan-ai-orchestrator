"""Read-only audit for the locked module baseline document."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"

MODULES = (
    "repo_guard",
    "backend_core",
    "common_tool_runtime",
    "common_engine_commercialization",
    "local_agent_e2e",
    "local_agent_connection_recovery",
    "approval_flow",
    "playwright_ai",
    "desktop_auth_runtime",
    "release_preflight",
    "release_runtime",
)

REQUIRED_BASELINE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-MODULE-BASELINE-01",
    "responsibility",
    "input",
    "output",
    "allowed paths",
    "forbidden behavior",
    "security boundary",
    "state changes",
    "required verification",
    "known WARN",
    "docs/baseline/APP_BASELINE.md",
    "docs/baseline/STANDARD_WORKFLOW.md",
    "docs/templates/STANDARD_REPORT_TEMPLATE.md",
    "no raw secret, token, cookie, session, password, or OTP output",
    "no OUT_OF_SCOPE file modification, staging, or commit",
)

REQUIRED_APP_BASELINE_PHRASES = ("docs/baseline/MODULE_BASELINE.md",)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]
    if not APP_BASELINE.exists():
        return False, ["docs/baseline/APP_BASELINE.md missing"]

    baseline_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")
    app_baseline_text = APP_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_required = missing_phrases(baseline_text, REQUIRED_BASELINE_PHRASES)
    if missing_required:
        failures.append("module baseline missing phrase(s): " + ", ".join(missing_required))

    missing_modules = [module for module in MODULES if f"### {module}" not in baseline_text]
    if missing_modules:
        failures.append("module baseline missing module section(s): " + ", ".join(missing_modules))

    missing_app_refs = missing_phrases(app_baseline_text, REQUIRED_APP_BASELINE_PHRASES)
    if missing_app_refs:
        failures.append("app baseline missing module baseline reference(s): " + ", ".join(missing_app_refs))

    return not failures, failures or [
        "MODULE_BASELINE exists and is locked",
        "12 module contracts are present",
        "app baseline references MODULE_BASELINE",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "MODULE_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
