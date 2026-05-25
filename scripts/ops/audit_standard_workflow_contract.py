"""Read-only audit for the locked standard workflow and report template."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKFLOW = ROOT / "docs" / "baseline" / "STANDARD_WORKFLOW.md"
REPORT_TEMPLATE = ROOT / "docs" / "templates" / "STANDARD_REPORT_TEMPLATE.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"
GOVERNANCE = ROOT / "docs" / "architecture" / "development_governance_rules_20260515.md"

REQUIRED_WORKFLOW_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-STANDARD-WORKFLOW-01",
    "goal",
    "scope",
    "allowed files",
    "forbidden actions",
    "input/output contract",
    "authorization boundary",
    "state changes",
    "regression gate",
    "rollback or recovery plan",
    "Target App Scope Rule",
    "act only on the approved target app or repository",
    "do not stop, modify, delete, stage, or commit anything for that external app",
    "ask for separate approval before taking any action on that external app",
    "Server-First Operating Rule",
    "The server is the final operational source of truth for HAEHAN.",
    "treat desktop and local-agent code as subordinate execution layers",
    "do not add persistent local autostart",
    "docs/templates/STANDARD_REPORT_TEMPLATE.md",
)

REQUIRED_TEMPLATE_PHRASES = (
    "Start HEAD",
    "End HEAD",
    "Git status",
    "Changed files",
    "Input/output contract",
    "Authorization boundary",
    "State changes",
    "Regression gate",
    "Function:",
    "Why it exists:",
    "Failure behavior:",
    "Security or state boundary:",
    "Verification",
    "Final Verdict",
)

REQUIRED_REFERENCE_PHRASES = (
    "docs/baseline/STANDARD_WORKFLOW.md",
    "docs/templates/STANDARD_REPORT_TEMPLATE.md",
    "The server is the final operational source of truth for HAEHAN.",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    paths = (WORKFLOW, REPORT_TEMPLATE, APP_BASELINE, GOVERNANCE)
    missing_paths = [str(path.relative_to(ROOT)) for path in paths if not path.exists()]
    if missing_paths:
        return False, ["missing required path(s): " + ", ".join(missing_paths)]

    workflow_text = WORKFLOW.read_text(encoding="utf-8", errors="replace")
    template_text = REPORT_TEMPLATE.read_text(encoding="utf-8", errors="replace")
    app_baseline_text = APP_BASELINE.read_text(encoding="utf-8", errors="replace")
    governance_text = GOVERNANCE.read_text(encoding="utf-8", errors="replace")

    missing_workflow = missing_phrases(workflow_text, REQUIRED_WORKFLOW_PHRASES)
    if missing_workflow:
        failures.append("standard workflow missing phrase(s): " + ", ".join(missing_workflow))

    missing_template = missing_phrases(template_text, REQUIRED_TEMPLATE_PHRASES)
    if missing_template:
        failures.append("standard report template missing phrase(s): " + ", ".join(missing_template))

    combined_references = app_baseline_text + "\n" + governance_text
    missing_references = missing_phrases(combined_references, REQUIRED_REFERENCE_PHRASES)
    if missing_references:
        failures.append("governance/app baseline missing reference(s): " + ", ".join(missing_references))

    return not failures, failures or [
        "STANDARD_WORKFLOW exists and is locked",
        "STANDARD_REPORT_TEMPLATE contains required report fields",
        "app baseline and governance rules reference the standard workflow",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_STANDARD_WORKFLOW_CONTRACT' if ok else 'FAIL_STANDARD_WORKFLOW_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
