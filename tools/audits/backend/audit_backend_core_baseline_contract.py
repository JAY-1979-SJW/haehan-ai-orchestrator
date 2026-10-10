"""Read-only audit for the locked backend_core baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKEND_BASELINE = ROOT / "docs" / "baseline" / "modules" / "BACKEND_CORE_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_BACKEND_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-BACKEND-CORE-BASELINE-01",
    "authentication defaults and enforcement",
    "user authorization and role checks",
    "approval policy and approval state",
    "task creation and validation",
    "local-agent dispatch contract",
    "audit event creation",
    "authenticated user request",
    "local-agent WebSocket authentication using `agent_id + device_token`",
    "task id",
    "task state",
    "approval decision",
    "redacted response body",
    "AUTH_ENABLED",
    "waiting_approval -> queued -> delivered -> running -> completed | failed",
    "run Playwright directly",
    "Bearer admin-token",
    "hardcoded admin bearer token",
    "hide auth failures behind mock data",
    "dispatch unapproved high-risk work to a local agent",
    "python tools/audits/backend/audit_backend_runtime_contract.py",
    "python tools/quality/module_quality_gate.py --module backend_core",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### backend_core",
    "docs/baseline/modules/BACKEND_CORE_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    from scripts.common.audit_cli import BaselineRefSpec, audit_baseline_with_module_ref

    return audit_baseline_with_module_ref(
        BaselineRefSpec(
            baseline=BACKEND_BASELINE,
            baseline_missing="docs/baseline/modules/BACKEND_CORE_BASELINE.md missing",
            baseline_phrases=REQUIRED_BACKEND_PHRASES,
            baseline_fail_prefix="backend_core baseline missing phrase(s): ",
            module_baseline=MODULE_BASELINE,
            module_missing="docs/baseline/MODULE_BASELINE.md missing",
            module_phrases=REQUIRED_MODULE_BASELINE_PHRASES,
            module_fail_prefix="module baseline missing backend_core reference(s): ",
            success=[
                "BACKEND_CORE_BASELINE exists and is locked",
                "backend auth/approval/task/dispatch boundaries are documented",
                "module baseline references BACKEND_CORE_BASELINE",
            ],
        ),
        missing_phrases,
    )


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "BACKEND_CORE_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
