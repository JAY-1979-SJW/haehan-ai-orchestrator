"""Read-only audit for the locked app baseline document."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"
GOVERNANCE = ROOT / "docs" / "architecture" / "development_governance_rules_20260515.md"

REQUIRED_BASELINE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-APP-BASELINE-01",
    "server task creation",
    "local-agent WebSocket authentication",
    "AUTH_ENABLED",
    "Unapproved high-risk tasks must not appear in the local-agent dispatch queue",
    "python scripts/required_quality_gate.py",
    "python scripts/module_quality_gate.py --module backend_core",
    "python scripts/module_quality_gate.py --module local_agent_e2e",
    "input/output contract",
    "authorization boundary",
    "state changes",
    "regression gate",
)

REQUIRED_GOVERNANCE_PHRASES = (
    "docs/baseline/APP_BASELINE.md",
    "input/output contract",
    "authorization boundary",
    "state changes",
    "regression gate",
)


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/APP_BASELINE.md missing"]
    if not GOVERNANCE.exists():
        return False, ["development governance rules missing"]

    baseline_text = BASELINE.read_text(encoding="utf-8", errors="replace")
    governance_text = GOVERNANCE.read_text(encoding="utf-8", errors="replace")

    missing_baseline = [phrase for phrase in REQUIRED_BASELINE_PHRASES if phrase not in baseline_text]
    if missing_baseline:
        failures.append("baseline missing phrase(s): " + ", ".join(missing_baseline))

    missing_governance = [phrase for phrase in REQUIRED_GOVERNANCE_PHRASES if phrase not in governance_text]
    if missing_governance:
        failures.append("governance missing phrase(s): " + ", ".join(missing_governance))

    return not failures, failures or [
        "APP_BASELINE exists and is locked",
        "governance rules reference APP_BASELINE",
        "4-point development checklist is required",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_APP_BASELINE_CONTRACT' if ok else 'FAIL_APP_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
