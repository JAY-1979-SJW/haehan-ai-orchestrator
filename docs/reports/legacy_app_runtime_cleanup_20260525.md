# Legacy App Runtime Cleanup - 2026-05-25

## Finding

Some Python processes seen during inspection were not from the current Haehan
local-agent app. They belonged to other workspaces or unrelated verification
work, including:

- `scripts.hwpx.web_office.editor_api_route:app` on `127.0.0.1:8767`
- `scripts/ops/verify_web_office_server_monitor.py`
- interrupted pytest/pre-commit verification processes

Those external processes are not part of this cleanup scope. The cleanup scope
is limited to this repository's legacy Haehan desktop UI/runtime entrypoints.
Per `docs/baseline/STANDARD_WORKFLOW.md`, external apps are report-only unless
the user separately approves action on that app.

Current Haehan Task Scheduler autostart jobs were not registered when checked.
Current legacy UI entrypoint files are absent:

- `desktop/tray_app.py`
- `desktop/webview_app.py`
- `desktop/webview_app_pywebview.py`
- `scripts/archive/desktop_local_ui/index.html`

Python processes may still be visible on the machine, but current command-line
inspection was denied by Windows process permissions. Per target-app scope, no
external Python process was stopped or modified by this cleanup.

## Cleanup

- Removed archived legacy desktop UI files under `scripts/archive/desktop_local_ui/`.
- Removed deleted UI entrypoints from `HaehanAI-Agent.spec`.
- Changed `scripts/setup_task_scheduler.ps1` to cleanup-only behavior so it
  removes legacy Haehan scheduled tasks instead of registering logon autostart.
- Added `scripts/ops/audit_legacy_app_runtime_cleanup.py` and regression tests.

## Verification

```text
python scripts/ops/audit_legacy_app_runtime_cleanup.py
python scripts/ops/audit_standard_workflow_contract.py
python -m py_compile scripts/cdp_daemon.py scripts/ops/audit_legacy_app_runtime_cleanup.py scripts/build_desktop_webview_app_windows.py scripts/ops/audit_desktop_app_design.py scripts/ops/audit_desktop_webview_pyinstaller_package.py scripts/ops/audit_desktop_webview_local_e2e_smoke.py desktop/main_launcher.py
python -m pytest tests/test_legacy_app_runtime_cleanup.py -q
python -m pytest tests/test_legacy_app_runtime_cleanup.py tests/test_app_scope_web_desktop_boundary_20260516.py tests/test_desktop_status_provider.py tests/test_haehan_legacy_entrypoint_guard.py tests/test_standard_workflow_contract.py -q
git diff --check
```
