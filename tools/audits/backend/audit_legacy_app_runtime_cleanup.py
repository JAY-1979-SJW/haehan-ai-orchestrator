"""Audit legacy desktop app runtime cleanup.

This audit locks the removal of old desktop UI/runtime entrypoints that can
relaunch a stale Python app outside the current local-agent contract.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

FORBIDDEN_PATHS = [
    "desktop/tray_app.py",
    "desktop/webview_app.py",
    "desktop/webview_app_pywebview.py",
    "scripts/archive/desktop_local_ui/index.html",
    "scripts/archive/desktop_local_ui/app.js",
    "scripts/archive/desktop_local_ui/style.css",
    "scripts/archive/desktop_local_ui/DESIGN.md",
]

FORBIDDEN_SPEC_NEEDLES = [
    "desktop.tray_app",
    "desktop.webview_app",
    "desktop.webview_app_pywebview",
]

FORBIDDEN_SCHEDULER_NEEDLES = [
    "Register-ScheduledTask",
    "New-ScheduledTaskTrigger",
    "-AtLogOn",
]

FORBIDDEN_SOURCE_NEEDLES = [
    ("scripts/build_desktop_webview_app_windows.py", "desktop.webview_app_pywebview"),
    ("scripts/browser/cdp/install_cdp_chrome_task.ps1", "New-ScheduledTaskTrigger"),
    ("scripts/browser/cdp/install_cdp_chrome_task.ps1", "Register-ScheduledTask"),
    ("scripts/browser/cdp/install_cdp_chrome_task.ps1", "-AtLogOn"),
]


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _needle_found(needle, scheduler):
    if needle == "Register-ScheduledTask":
        found = re.search(r"(?<!Un)Register-ScheduledTask", scheduler)
    else:
        found = needle in scheduler
    return found


def audit() -> list[str]:
    failures: list[str] = []

    for rel in FORBIDDEN_PATHS:
        if (ROOT / rel).exists():
            failures.append(f"legacy runtime path still exists: {rel}")

    spec = _read("HaehanAI-Agent.spec")
    for needle in FORBIDDEN_SPEC_NEEDLES:
        if needle in spec:
            failures.append(f"legacy PyInstaller hidden import remains: {needle}")

    scheduler = _read("scripts/setup_task_scheduler.ps1")
    for needle in FORBIDDEN_SCHEDULER_NEEDLES:
        found = _needle_found(needle, scheduler)
        if found:
            failures.append(f"legacy autostart registration remains: {needle}")
    if "Unregister-ScheduledTask" not in scheduler:
        failures.append("scheduler cleanup script no longer removes legacy tasks")

    for rel, needle in FORBIDDEN_SOURCE_NEEDLES:
        text = _read(rel)
        found = _needle_found(needle, text)
        if found:
            failures.append(f"legacy runtime source reference remains: {rel}: {needle}")

    return failures


def main() -> int:
    failures = audit()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        print("RESULT=FAIL_LEGACY_APP_RUNTIME_CLEANUP")
        return 1

    print("[PASS] legacy desktop UI files are removed")
    print("[PASS] PyInstaller spec does not import removed UI entrypoints")
    print("[PASS] scheduler helper only removes legacy autostart tasks")
    print("RESULT=PASS_LEGACY_APP_RUNTIME_CLEANUP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
