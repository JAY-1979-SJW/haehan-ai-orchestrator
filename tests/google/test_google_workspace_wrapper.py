from __future__ import annotations

from importlib import import_module

from scripts.google.workspace import registry, router


WORKSPACE_APPROVAL_ACTIONS = [
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
]


def test_workspace_registry_preserves_locked_counts() -> None:
    summary = registry.workspace_summary()

    assert summary["surface_count"] == 12
    assert summary["action_count"] == 24
    assert summary["read_action_count"] == 12
    assert summary["approval_action_count"] == 12
    assert summary["live_input_supported_actions"] == WORKSPACE_APPROVAL_ACTIONS
    assert summary["prepare_or_open_only_approval_actions"] == []


def test_workspace_registry_surfaces_are_expected() -> None:
    assert [surface["key"] for surface in registry.list_surfaces()] == [
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
    ]


def test_workspace_registry_approval_actions_are_expected() -> None:
    approval_actions = [
        action["key"]
        for action in registry.list_actions()
        if action["requires_approval"]
    ]

    assert approval_actions == WORKSPACE_APPROVAL_ACTIONS


def test_workspace_router_summary_returns_registry() -> None:
    summary = router.run_workspace("summary")

    assert isinstance(summary, dict)
    assert summary["key"] == "workspace"
    assert summary["surface_count"] == 12


def test_workspace_router_rejects_unknown_service() -> None:
    result = router.run_workspace("unknown", "open", [])

    assert result == {
        "ok": False,
        "reason": "unknown_workspace_service",
        "service": "unknown",
    }


def test_workspace_catalog_only_wrappers_do_not_execute_live_actions() -> None:
    for service in ("slides", "forms", "meet", "chat", "contacts", "keep", "tasks"):
        module = import_module(f"scripts.google.workspace.{service}")
        result = module.run("create", ["private-value"])
        assert result["ok"] is False
        assert result["mode"] == "catalog_only"
        assert result["surface"]["key"] == service


def test_workspace_legacy_wrappers_delegate(monkeypatch) -> None:
    calls: list[tuple[str, str, list[str]]] = []
    wrapper_modules = {"calendar": "calendar_tasks"}  # 표준 calendar 가림 방지 이름(A005)
    wrappers = {
        "gmail": ("scripts.google.common.gmail", "list"),
        "drive": ("scripts.google.common.drive", "list"),
        "calendar": ("scripts.google.common.calendar_tasks", "today"),
        "docs": ("scripts.google.common.docs", "recent"),
        "sheets": ("scripts.google.common.sheets", "recent"),
    }

    for service, (legacy_module_name, expected_default) in wrappers.items():
        legacy_module = import_module(legacy_module_name)
        monkeypatch.setattr(
            legacy_module,
            "run",
            lambda task, args, service=service: calls.append((service, task, args)),
        )
        wrapper = import_module(f"scripts.google.workspace.{wrapper_modules.get(service, service)}")
        wrapper.run("", ["arg1"])
        assert calls[-1] == (service, expected_default, ["arg1"])
