"""Read-only audit for the locked approval_flow baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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
    "python scripts/module_quality_gate.py --module backend_core",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### approval_flow",
    "docs/baseline/modules/APPROVAL_FLOW_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not APPROVAL_BASELINE.exists():
        return False, ["docs/baseline/modules/APPROVAL_FLOW_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    approval_text = APPROVAL_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_approval = missing_phrases(approval_text, REQUIRED_APPROVAL_PHRASES)
    if missing_approval:
        failures.append("approval_flow baseline missing phrase(s): " + ", ".join(missing_approval))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing approval_flow reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "APPROVAL_FLOW_BASELINE exists and is locked",
        "approval auth/API/default-fail/state boundaries are documented",
        "module baseline references APPROVAL_FLOW_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_APPROVAL_FLOW_BASELINE_CONTRACT' if ok else 'FAIL_APPROVAL_FLOW_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

