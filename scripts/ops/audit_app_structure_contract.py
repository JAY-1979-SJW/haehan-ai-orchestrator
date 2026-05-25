"""Read-only audit for the server-first app structure and recovery boundary."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_STRUCTURE = ROOT / "docs" / "architecture" / "APP_STRUCTURE.md"
STANDARD_WORKFLOW = ROOT / "docs" / "baseline" / "STANDARD_WORKFLOW.md"
GOVERNANCE = ROOT / "docs" / "architecture" / "development_governance_rules_20260515.md"
REPORT = ROOT / "docs" / "reports" / "app_structure_guard_20260525.md"

REQUIRED_APP_STRUCTURE_PHRASES = (
    "Status: ACTIVE",
    "The app must be developed as a server-first control surface.",
    "The server is the final operational source of truth for HAEHAN.",
    "## Structural Layers",
    "## Canonical Flow",
    "## Forbidden Structure",
    "## Recovery Boundary",
    "diagnostic-first and server-baseline controlled",
    "automatic server deploy/restart",
    "Docker build, pull, up, restart, or deploy",
    "local-agent token deletion or credential reset",
    "persistent local autostart registration",
    "background recovery registration",
    "always-on monitoring registration",
    "process termination outside the approved target app",
    "audit-first unless their task is separately approved",
    "## Task History And Audit Log Boundary",
    "The server task state and server audit events are the final source of truth.",
    "Local-agent and desktop logs are diagnostic evidence only.",
    "must not contain raw",
    "## Development Order",
)

REQUIRED_WORKFLOW_PHRASES = (
    "App Structure Rule",
    "docs/architecture/APP_STRUCTURE.md",
    "The app must remain a server-first control surface.",
)

REQUIRED_GOVERNANCE_PHRASES = (
    "App Structure Rule",
    "docs/architecture/APP_STRUCTURE.md",
    "The app must remain a server-first control surface.",
)

REQUIRED_REPORT_PHRASES = (
    "App Structure Guard",
    "Recovery Boundary",
    "No live recovery script was added.",
    "Task History And Audit Log Boundary",
    "server-owned task state",
    "Raw secrets, tokens, cookies, sessions, passwords, OTP values",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    paths = (APP_STRUCTURE, STANDARD_WORKFLOW, GOVERNANCE, REPORT)
    missing_paths = [str(path.relative_to(ROOT)) for path in paths if not path.exists()]
    if missing_paths:
        return False, ["missing required path(s): " + ", ".join(missing_paths)]

    app_structure = APP_STRUCTURE.read_text(encoding="utf-8", errors="replace")
    workflow = STANDARD_WORKFLOW.read_text(encoding="utf-8", errors="replace")
    governance = GOVERNANCE.read_text(encoding="utf-8", errors="replace")
    report = REPORT.read_text(encoding="utf-8", errors="replace")

    missing = _missing(app_structure, REQUIRED_APP_STRUCTURE_PHRASES)
    if missing:
        failures.append("app structure missing phrase(s): " + ", ".join(missing))

    missing = _missing(workflow, REQUIRED_WORKFLOW_PHRASES)
    if missing:
        failures.append("standard workflow missing phrase(s): " + ", ".join(missing))

    missing = _missing(governance, REQUIRED_GOVERNANCE_PHRASES)
    if missing:
        failures.append("governance missing phrase(s): " + ", ".join(missing))

    missing = _missing(report, REQUIRED_REPORT_PHRASES)
    if missing:
        failures.append("report missing phrase(s): " + ", ".join(missing))

    return not failures, failures or [
        "APP_STRUCTURE exists and is server-first",
        "recovery boundary forbids live recovery without separate approval",
        "workflow and governance reference app structure",
        "guard report exists",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_APP_STRUCTURE_CONTRACT' if ok else 'FAIL_APP_STRUCTURE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
