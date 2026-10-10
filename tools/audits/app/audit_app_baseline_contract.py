"""Read-only audit for the locked app baseline document."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"
GOVERNANCE = ROOT / "docs" / "architecture" / "development_governance_rules_20260515.md"

REQUIRED_BASELINE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-APP-BASELINE-01",
    "The server is the final operational source of truth for HAEHAN.",
    "The final runtime baseline is server-first:",
    "Desktop and local-agent code are subordinate execution layers.",
    "Desktop and local-agent code must not become an independent source of truth",
    "must not register persistent autostart",
    "server task creation",
    "local-agent WebSocket authentication",
    "AUTH_ENABLED",
    "Unapproved high-risk tasks must not appear in the local-agent dispatch queue",
    "python tools/quality/required_quality_gate.py",
    "python tools/quality/module_quality_gate.py --module backend_core",
    "python tools/quality/module_quality_gate.py --module local_agent_e2e",
    "input/output contract",
    "authorization boundary",
    "state changes",
    "regression gate",
    "local verification is not the final verdict",
    "the server repository HEAD matches the intended release HEAD",
    "server smoke checks pass through the public route or server-side nginx route",
    "server stress checks pass through the public route or server-side nginx route",
    "post-deploy logs are checked for new runtime errors",
)

REQUIRED_GOVERNANCE_PHRASES = (
    "docs/baseline/APP_BASELINE.md",
    "The server is the final operational source of truth for HAEHAN.",
    "Desktop and local-agent code are subordinate execution layers.",
    "Persistent local autostart, background recovery, and always-on monitoring are",
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
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "APP_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
