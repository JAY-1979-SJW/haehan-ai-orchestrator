"""Read-only audit for the locked Google Workspace module baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "GOOGLE_WORKSPACE_MODULE_BASELINE.md"

WORKSPACE_SURFACES = (
    "gmail",
    "drive",
    "calendar",
    "docs",
    "sheets",
    "slides",
    "forms",
    "meet",
    "chat",
    "contacts",
    "keep",
    "tasks",
)

WORKSPACE_APPROVAL_ACTIONS = (
    "gmail_send_email",
    "drive_upload_share_file",
    "calendar_create_event",
    "docs_create_edit_document",
    "sheets_update_cells",
    "slides_create_presentation",
    "forms_create_publish",
    "meet_create_meeting",
    "chat_send_message",
    "contacts_create_update",
    "keep_create_note",
    "tasks_create_task",
)

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: GOOGLE-WORKSPACE-MODULE-BASELINE-01",
    "Workspace surfaces: 12",
    "Workspace actions: 24",
    "Workspace read actions: 12",
    "Workspace approval actions: 12",
    "Workspace live input supported actions: 12",
    "Workspace prepare/open-only approval actions: 0",
    "All 12 Workspace approval actions support safe live input handoff.",
    "no Google password replay",
    "no mail body, account name, file name, document body, attendee, contact,",
    "no broad Google refactor outside Workspace",
    "python tools/audits/google/audit_google_workspace_module_baseline_contract.py",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/GOOGLE_WORKSPACE_MODULE_BASELINE.md missing"]

    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    if missing:
        failures.append("Google Workspace baseline missing phrase(s): " + ", ".join(missing))

    from scripts.google.common.live_inputs import build_live_input_coverage
    from scripts.google.common.tab_registry import build_google_tab_summary

    summary = build_google_tab_summary()
    workspace = next((tab for tab in summary["tabs"] if tab["key"] == "workspace"), None)
    if workspace is None:
        failures.append("Google workspace tab missing")
        return False, failures

    surfaces = tuple(surface["key"] for surface in workspace["surfaces"])
    if surfaces != WORKSPACE_SURFACES:
        failures.append("Workspace surfaces changed: " + ", ".join(surfaces))

    approval_actions = tuple(action["key"] for action in workspace["actions"] if action["requires_approval"])
    if approval_actions != WORKSPACE_APPROVAL_ACTIONS:
        failures.append("Workspace approval actions changed: " + ", ".join(approval_actions))

    expected_counts = {
        "surface_count": 12,
        "action_count": 24,
        "read_action_count": 12,
        "approval_action_count": 12,
    }
    for key, expected in expected_counts.items():
        if workspace.get(key) != expected:
            failures.append(f"Workspace count mismatch {key}: expected {expected}, got {workspace.get(key)}")

    if summary["host_warnings"]:
        failures.append(f"Google host warnings must stay zero, got {len(summary['host_warnings'])}")

    live_supported = {item["action_key"] for item in build_live_input_coverage()["supported"]}
    workspace_live = [action["key"] for action in workspace["actions"] if action["key"] in live_supported]
    if workspace_live != list(WORKSPACE_APPROVAL_ACTIONS):
        failures.append("Workspace live-input-supported actions changed: " + ", ".join(workspace_live))

    return not failures, failures or [
        "GOOGLE_WORKSPACE_MODULE_BASELINE exists and is locked",
        "Workspace owns 12 surfaces and 24 actions",
        "Workspace approval and live-input boundaries are preserved",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_WORKSPACE_MODULE_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
