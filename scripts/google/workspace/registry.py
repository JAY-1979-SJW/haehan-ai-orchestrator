"""Google Workspace registry derived from the locked Google tab registry."""
from __future__ import annotations

from scripts.google.live_inputs import build_live_input_coverage
from scripts.google.tab_registry import build_google_tab_summary

WORKSPACE_TAB_KEY = "workspace"
WORKSPACE_LIVE_INPUT_ACTIONS = (
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


def workspace_summary() -> dict:
    summary = build_google_tab_summary()
    workspace = next(tab for tab in summary["tabs"] if tab["key"] == WORKSPACE_TAB_KEY)
    live_supported = {item["action_key"] for item in build_live_input_coverage()["supported"]}
    workspace["live_input_supported_actions"] = [
        action["key"] for action in workspace["actions"] if action["key"] in live_supported
    ]
    workspace["prepare_or_open_only_approval_actions"] = [
        action["key"]
        for action in workspace["actions"]
        if action["requires_approval"] and action["key"] not in live_supported
    ]
    return workspace


def list_surfaces() -> list[dict]:
    return list(workspace_summary()["surfaces"])


def list_actions() -> list[dict]:
    return list(workspace_summary()["actions"])


def get_surface(surface_key: str) -> dict:
    for surface in list_surfaces():
        if surface["key"] == surface_key:
            return surface
    raise KeyError(f"unknown Google Workspace surface: {surface_key}")


def get_action(action_key: str) -> dict:
    for action in list_actions():
        if action["key"] == action_key:
            return action
    raise KeyError(f"unknown Google Workspace action: {action_key}")


def is_live_input_supported(action_key: str) -> bool:
    return action_key in WORKSPACE_LIVE_INPUT_ACTIONS
