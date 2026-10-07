"""Read-only audit for the locked backend_core baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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
    "python scripts/ops/audit_backend_runtime_contract.py",
    "python scripts/ops/quality/module_quality_gate.py --module backend_core",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### backend_core",
    "docs/baseline/modules/BACKEND_CORE_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BACKEND_BASELINE.exists():
        return False, ["docs/baseline/modules/BACKEND_CORE_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    backend_text = BACKEND_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_backend = missing_phrases(backend_text, REQUIRED_BACKEND_PHRASES)
    if missing_backend:
        failures.append("backend_core baseline missing phrase(s): " + ", ".join(missing_backend))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing backend_core reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "BACKEND_CORE_BASELINE exists and is locked",
        "backend auth/approval/task/dispatch boundaries are documented",
        "module baseline references BACKEND_CORE_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_BACKEND_CORE_BASELINE_CONTRACT' if ok else 'FAIL_BACKEND_CORE_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

