from tools.audits.backend import audit_legacy_app_runtime_cleanup as audit


def test_legacy_app_runtime_cleanup_passes_current_tree():
    assert audit.audit() == []


def test_removed_ui_paths_are_locked():
    assert "desktop/tray_app.py" in audit.FORBIDDEN_PATHS
    assert "scripts/archive/desktop_local_ui/index.html" in audit.FORBIDDEN_PATHS


def test_scheduler_is_cleanup_only():
    scheduler = audit._read("scripts/setup_task_scheduler.ps1")
    assert "Unregister-ScheduledTask" in scheduler
    assert audit.audit() == []
    assert "-AtLogOn" not in scheduler


def test_cdp_chrome_task_helper_is_cleanup_only():
    script = audit._read("scripts/browser/cdp/install_cdp_chrome_task.ps1")
    assert "Unregister-ScheduledTask" in script
    assert "New-ScheduledTaskTrigger" not in script
    assert "-AtLogOn" not in script
