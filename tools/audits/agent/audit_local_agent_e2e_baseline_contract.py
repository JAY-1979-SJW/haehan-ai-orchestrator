"""Read-only audit for the locked local_agent_e2e baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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
    "python tools/audits/agent/audit_local_agent_e2e_flow_contract.py",
    "python tools/smoke/live_parallel_task_dispatch_smoke.py --temp-admin --count 5 --concurrency 5 --timeout 90",
    "python tools/quality/module_quality_gate.py --module local_agent_e2e",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### local_agent_e2e",
    "docs/baseline/modules/LOCAL_AGENT_E2E_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    from scripts.common.audit_cli import BaselineRefSpec, audit_baseline_with_module_ref

    return audit_baseline_with_module_ref(
        BaselineRefSpec(
            baseline=LOCAL_AGENT_BASELINE,
            baseline_missing="docs/baseline/modules/LOCAL_AGENT_E2E_BASELINE.md missing",
            baseline_phrases=REQUIRED_LOCAL_AGENT_PHRASES,
            baseline_fail_prefix="local_agent_e2e baseline missing phrase(s): ",
            module_baseline=MODULE_BASELINE,
            module_missing="docs/baseline/MODULE_BASELINE.md missing",
            module_phrases=REQUIRED_MODULE_BASELINE_PHRASES,
            module_fail_prefix="module baseline missing local_agent_e2e reference(s): ",
            success=[
                "LOCAL_AGENT_E2E_BASELINE exists and is locked",
                "local-agent auth/dispatch/state/redaction boundaries are documented",
                "module baseline references LOCAL_AGENT_E2E_BASELINE",
            ],
        ),
        missing_phrases,
    )


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "LOCAL_AGENT_E2E_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
