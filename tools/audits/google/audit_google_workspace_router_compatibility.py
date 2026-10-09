"""Audit Google Workspace router compatibility without live browser execution."""

from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKSPACE_ROUTER_COMMANDS = (
    ("google", "mail", "list", ["inbox"], ("gmail", "list", ["inbox"]), ("goto", "auto")),
    (
        "google",
        "mail",
        "compose",
        ["to@example.com", "subject", "body"],
        ("gmail", "compose", ["to@example.com", "subject", "body"]),
        ("gmail_send", "approve"),
    ),
    ("google", "drive", "list", [], ("drive", "list", []), ("goto", "auto")),
    ("google", "calendar", "today", [], ("calendar", "today", []), ("goto", "auto")),
    ("google", "docs", "recent", [], ("docs", "recent", []), ("goto", "auto")),
    ("google", "sheets", "recent", [], ("sheets", "recent", []), ("goto", "auto")),
)

LEGACY_WRAPPERS = {
    "gmail": ("scripts.google.common.gmail", "list"),
    "drive": ("scripts.google.common.drive", "list"),
    "calendar": ("scripts.google.common.calendar_tasks", "today"),
    "docs": ("scripts.google.common.docs", "recent"),
    "sheets": ("scripts.google.common.sheets", "recent"),
}

# 서비스 키와 wrapper 모듈 이름이 다른 경우(표준 calendar 가림 방지로 calendar → calendar_tasks, A005)
WRAPPER_MODULES = {"calendar": "calendar_tasks"}

CATALOG_ONLY_SERVICES = ("slides", "forms", "meet", "chat", "contacts", "keep", "tasks")
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


def _patch(obj: object, name: str, replacement: object) -> Callable[[], None]:
    original = getattr(obj, name)
    setattr(obj, name, replacement)

    def restore() -> None:
        setattr(obj, name, original)

    return restore


def _audit_google_router_delegation() -> list[str]:
    from scripts.google import router as google_router

    failures: list[str] = []
    calls: list[tuple[str, str, list[str]]] = []
    gate_calls: list[tuple[str, str]] = []

    restores = [
        _patch(google_router, "gate_check", lambda action, risk="auto": gate_calls.append((action, risk))),
        _patch(
            google_router.workspace_router,
            "run_workspace",
            lambda service, task, args: calls.append((service, task, list(args))),
        ),
    ]
    try:
        for site, task, sub, args, _expected_call, _expected_gate in WORKSPACE_ROUTER_COMMANDS:
            google_router.run_google(site, task, sub, list(args))
    finally:
        for restore in reversed(restores):
            restore()

    expected_calls = [item[4] for item in WORKSPACE_ROUTER_COMMANDS]
    expected_gates = [item[5] for item in WORKSPACE_ROUTER_COMMANDS]
    if calls != expected_calls:
        failures.append(f"router delegation mismatch: expected {expected_calls}, got {calls}")
    if gate_calls != expected_gates:
        failures.append(f"router gate mismatch: expected {expected_gates}, got {gate_calls}")
    return failures


def _audit_legacy_wrapper_delegation() -> list[str]:
    failures: list[str] = []
    calls: list[tuple[str, str, list[str]]] = []
    restores: list[Callable[[], None]] = []
    try:
        for service, (legacy_module_name, expected_default) in LEGACY_WRAPPERS.items():
            legacy_module = import_module(legacy_module_name)
            restores.append(
                _patch(
                    legacy_module,
                    "run",
                    lambda task, args, service=service: calls.append((service, task, list(args))),
                )
            )
            wrapper = import_module(f"scripts.google.workspace.{WRAPPER_MODULES.get(service, service)}")
            wrapper.run("", ["arg1"])
            if calls[-1] != (service, expected_default, ["arg1"]):
                failures.append(f"{service} wrapper delegation mismatch: got {calls[-1]}")
    finally:
        for restore in reversed(restores):
            restore()
    return failures


def _audit_catalog_only_wrappers() -> list[str]:
    failures: list[str] = []
    for service in CATALOG_ONLY_SERVICES:
        module = import_module(f"scripts.google.workspace.{service}")
        result = module.run("create", ["private-value"])
        if result.get("ok") is not False:
            failures.append(f"{service} catalog wrapper returned ok={result.get('ok')!r}")
        if result.get("mode") != "catalog_only":
            failures.append(f"{service} catalog wrapper mode mismatch: {result.get('mode')!r}")
        if result.get("surface", {}).get("key") != service:
            failures.append(f"{service} catalog wrapper surface mismatch: {result.get('surface')!r}")
    return failures


def _audit_workspace_counts() -> list[str]:
    from scripts.google.workspace.registry import workspace_summary

    failures: list[str] = []
    summary = workspace_summary()
    expected = {
        "surface_count": 12,
        "action_count": 24,
        "read_action_count": 12,
        "approval_action_count": 12,
        "live_input_supported_actions": WORKSPACE_APPROVAL_ACTIONS,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            failures.append(f"workspace {key} mismatch: expected {value!r}, got {summary.get(key)!r}")
    if summary.get("prepare_or_open_only_approval_actions", []) != []:
        failures.append("workspace prepare/open-only approval action count must be 0")
    return failures


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    failures.extend(_audit_google_router_delegation())
    failures.extend(_audit_legacy_wrapper_delegation())
    failures.extend(_audit_catalog_only_wrappers())
    failures.extend(_audit_workspace_counts())
    return not failures, failures or [
        "Google router delegates Workspace commands through workspace router",
        "Workspace legacy wrappers preserve top-level implementation compatibility",
        "Workspace catalog-only services do not execute live actions",
        "Workspace counts and live-input boundaries are preserved",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_WORKSPACE_ROUTER_COMPATIBILITY")


if __name__ == "__main__":
    raise SystemExit(main())
