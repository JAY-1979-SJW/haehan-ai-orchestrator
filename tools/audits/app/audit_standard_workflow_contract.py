"""Read-only audit for the locked standard workflow and report template."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKFLOW = ROOT / "docs" / "baseline" / "STANDARD_WORKFLOW.md"
REPORT_TEMPLATE = ROOT / "docs" / "templates" / "STANDARD_REPORT_TEMPLATE.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"
GOVERNANCE = ROOT / "docs" / "architecture" / "development_governance_rules_20260515.md"
APP_STRUCTURE = ROOT / "docs" / "architecture" / "APP_STRUCTURE.md"
TOOL_INVENTORY = ROOT / "docs" / "inventory" / "TOOL_INVENTORY.md"
CONNECTION_INVENTORY = ROOT / "docs" / "inventory" / "CONNECTION_INVENTORY.md"

REQUIRED_WORKFLOW_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-STANDARD-WORKFLOW-01",
    "Work Overview And Final-Approval-Only Rule",
    "work overview before implementation",
    "one overview approval",
    "user performs the final approval action only",
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
    "Local smoke, local stress, and local build results are preliminary evidence",
    "server smoke plus server stress checks pass",
    "server `git status --short --branch`",
    "server-local changes with an explicit stash or report-only decision",
    "Auto-Run Rule",
    "Automation is allowed only for safe, bounded work inside the approved scope.",
    "baseline and contract audits",
    "The worker may commit only when the user explicitly requests commit",
    "The worker may push only when the user explicitly requests push",
    "Auto-run must never perform server deploy/restart",
    "Tool Inventory And Report Rule",
    "docs/inventory/TOOL_INVENTORY.md",
    "docs/inventory/CONNECTION_INVENTORY.md",
    "Logs alone are not sufficient as final work evidence.",
    "App Structure Rule",
    "docs/architecture/APP_STRUCTURE.md",
    "The app must remain a server-first control surface.",
    "Task History And Audit Log Rule",
    "The server task state and server audit events are the final source of truth.",
    "Every runtime task path must attempt structured audit logging by default.",
    "Local-agent and desktop logs are diagnostic evidence only.",
    "AI Agent Work Record Rule",
    "Every AI agent task, in every operating mode, must leave a user-verifiable",
    "ordered work steps performed",
    "decisions made and the reason for each material decision",
    "User Data Contribution Consent Rule",
    "explicit user data contribution consent",
    "Development material must be redacted, minimized, and purpose-bound.",
    "If consent is missing, expired, revoked, or outside the recorded purpose",
    "docs/templates/STANDARD_REPORT_TEMPLATE.md",
)

REQUIRED_TEMPLATE_PHRASES = (
    "Start HEAD",
    "End HEAD",
    "Git status",
    "Changed files",
    "Agent Work Record",
    "User request summary",
    "Agent role or execution mode",
    "Ordered work steps performed",
    "Decisions and reasons",
    "User-visible evidence path",
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
    "Auto-Run Rule",
    "Tool Inventory And Report Rule",
    "docs/architecture/APP_STRUCTURE.md",
)

REQUIRED_INVENTORY_PHRASES = (
    "Owner baseline: `docs/baseline/APP_BASELINE.md`",
    "Workflow rule: `docs/baseline/STANDARD_WORKFLOW.md`",
    "Lock Needed Queue",
)

REQUIRED_TOOL_INVENTORY_PHRASES = ("Status: ACTIVE",) + REQUIRED_INVENTORY_PHRASES

REQUIRED_CONNECTION_INVENTORY_PHRASES = (
    "Status: LOCKED",
    "Connection Logic Lock",
    "authenticated user instruction",
    "local-agent WebSocket authentication",
    "The server is the final operational source of truth for connection state",
    "must not call local-agent, desktop, browser, Gmail, or site-work execution",
    "paths directly",
    "agent_id + device_token",
    "background_approved=True",
    "AI Agent Work Record",
    "Unknown or unclassified connections must fail closed before command execution.",
) + REQUIRED_INVENTORY_PHRASES

REQUIRED_APP_STRUCTURE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-APP-STRUCTURE-01",
    "The app must be developed as a server-first control surface.",
    "The server is the final operational source of truth for HAEHAN.",
    "## Structural Layers",
    "## Canonical Flow",
    "## Forbidden Structure",
    "## Recovery Boundary",
    "## Task History And Audit Log Boundary",
    "## User Data Contribution Consent Boundary",
    "## Development Order",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    paths = (
        WORKFLOW,
        REPORT_TEMPLATE,
        APP_BASELINE,
        GOVERNANCE,
        APP_STRUCTURE,
        TOOL_INVENTORY,
        CONNECTION_INVENTORY,
    )
    missing_paths = [str(path.relative_to(ROOT)) for path in paths if not path.exists()]
    if missing_paths:
        return False, ["missing required path(s): " + ", ".join(missing_paths)]

    workflow_text = WORKFLOW.read_text(encoding="utf-8", errors="replace")
    template_text = REPORT_TEMPLATE.read_text(encoding="utf-8", errors="replace")
    app_baseline_text = APP_BASELINE.read_text(encoding="utf-8", errors="replace")
    governance_text = GOVERNANCE.read_text(encoding="utf-8", errors="replace")
    app_structure_text = APP_STRUCTURE.read_text(encoding="utf-8", errors="replace")
    tool_inventory_text = TOOL_INVENTORY.read_text(encoding="utf-8", errors="replace")
    connection_inventory_text = CONNECTION_INVENTORY.read_text(encoding="utf-8", errors="replace")

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

    missing_tool_inventory = missing_phrases(tool_inventory_text, REQUIRED_TOOL_INVENTORY_PHRASES)
    if missing_tool_inventory:
        failures.append("tool inventory missing phrase(s): " + ", ".join(missing_tool_inventory))

    missing_connection_inventory = missing_phrases(
        connection_inventory_text,
        REQUIRED_CONNECTION_INVENTORY_PHRASES,
    )
    if missing_connection_inventory:
        failures.append("connection inventory missing phrase(s): " + ", ".join(missing_connection_inventory))

    missing_app_structure = missing_phrases(app_structure_text, REQUIRED_APP_STRUCTURE_PHRASES)
    if missing_app_structure:
        failures.append("app structure missing phrase(s): " + ", ".join(missing_app_structure))

    return not failures, failures or [
        "STANDARD_WORKFLOW exists and is locked",
        "STANDARD_REPORT_TEMPLATE contains required report fields",
        "app baseline and governance rules reference the standard workflow",
        "tool and connection inventories exist",
        "app structure baseline exists",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "STANDARD_WORKFLOW_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
