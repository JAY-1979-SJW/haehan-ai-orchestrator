"""Read-only audit for the locked local_agent_e2e baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCAL_AGENT_BASELINE = ROOT / "docs" / "baseline" / "modules" / "LOCAL_AGENT_E2E_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_LOCAL_AGENT_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-LOCAL-AGENT-E2E-BASELINE-01",
    "authenticated local-agent WebSocket connection",
    "`agent_id + device_token` validation flow",
    "receiving only server-dispatched tasks",
    "unapproved high-risk task exclusion from dispatch",
    "authenticated local-agent WebSocket",
    "server-dispatched task",
    "unapproved high-risk task",
    "raw secret, token, cookie, session, password, OTP, or Authorization header",
    "delivered state update",
    "running state update",
    "completed state update",
    "failed state update",
    "Local-agent WebSocket must require `agent_id + device_token`.",
    "Unapproved high-risk tasks must not appear in the local-agent dispatch queue.",
    "A single local-agent WebSocket session must receive at most one active task at",
    "Concurrent server submissions must remain queued and drain one by one",
    "True simultaneous local execution requires multiple registered agents",
    "queued -> delivered -> running -> completed",
    "waiting_approval -> queued -> delivered -> running -> completed | failed",
    "execute server-contract-bypassing user-direct commands",
    "accept unauthenticated WebSocket tasks",
    "python scripts/ops/audit_local_agent_e2e_flow_contract.py",
    "python scripts/ops/live_parallel_task_dispatch_smoke.py --temp-admin --count 5 --concurrency 5 --timeout 90",
    "python scripts/module_quality_gate.py --module local_agent_e2e",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### local_agent_e2e",
    "docs/baseline/modules/LOCAL_AGENT_E2E_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not LOCAL_AGENT_BASELINE.exists():
        return False, ["docs/baseline/modules/LOCAL_AGENT_E2E_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    local_agent_text = LOCAL_AGENT_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_local_agent = missing_phrases(local_agent_text, REQUIRED_LOCAL_AGENT_PHRASES)
    if missing_local_agent:
        failures.append("local_agent_e2e baseline missing phrase(s): " + ", ".join(missing_local_agent))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing local_agent_e2e reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "LOCAL_AGENT_E2E_BASELINE exists and is locked",
        "local-agent auth/dispatch/state/redaction boundaries are documented",
        "module baseline references LOCAL_AGENT_E2E_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_LOCAL_AGENT_E2E_BASELINE_CONTRACT' if ok else 'FAIL_LOCAL_AGENT_E2E_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
