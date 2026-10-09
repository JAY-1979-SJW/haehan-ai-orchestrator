"""Read-only audit for the locked approval_flow baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APPROVAL_BASELINE = ROOT / "docs" / "baseline" / "modules" / "APPROVAL_FLOW_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_APPROVAL_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-APPROVAL-FLOW-BASELINE-01",
    "high-risk task approval request creation",
    "API approval default flow",
    "approval/denial/failure result handling",
    "task state update after approval decision",
    "local UI fallback restriction",
    "Approval failure must fail closed.",
    "authenticated user identity",
    "task id",
    "risk level",
    "configured approval API endpoint",
    "unconfigured API endpoint treated as success",
    "mock approval success in production",
    "approved",
    "denied",
    "failed",
    "safe error summary",
    "Approval requests must be tied to an authenticated user identity.",
    "HAEHAN_LOCAL_APPROVAL_UI_FALLBACK=1",
    "API misconfiguration, timeout, network failure, or denied response must not",
    "waiting_approval -> queued",
    "waiting_approval -> denied",
    "waiting_approval -> failed",
    "api_failed -> queued",
    "allow high-risk task queue entry without approval",
    "python tools/quality/module_quality_gate.py --module backend_core",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### approval_flow",
    "docs/baseline/modules/APPROVAL_FLOW_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    from scripts.common.audit_cli import BaselineRefSpec, audit_baseline_with_module_ref

    return audit_baseline_with_module_ref(
        BaselineRefSpec(
            baseline=APPROVAL_BASELINE,
            baseline_missing="docs/baseline/modules/APPROVAL_FLOW_BASELINE.md missing",
            baseline_phrases=REQUIRED_APPROVAL_PHRASES,
            baseline_fail_prefix="approval_flow baseline missing phrase(s): ",
            module_baseline=MODULE_BASELINE,
            module_missing="docs/baseline/MODULE_BASELINE.md missing",
            module_phrases=REQUIRED_MODULE_BASELINE_PHRASES,
            module_fail_prefix="module baseline missing approval_flow reference(s): ",
            success=[
                "APPROVAL_FLOW_BASELINE exists and is locked",
                "approval auth/API/default-fail/state boundaries are documented",
                "module baseline references APPROVAL_FLOW_BASELINE",
            ],
        ),
        missing_phrases,
    )


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "APPROVAL_FLOW_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
