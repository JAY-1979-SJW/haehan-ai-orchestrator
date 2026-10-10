"""tests/test_user_assisted_installer_20260508.py"""

from core.agent_runtime.runtime.security_program.user_assisted_installer import (
    STATUS_INSTALL_COMPLETED_DETECTED,
    STATUS_RETRY_ORIGINAL_TASK_READY,
    STATUS_USER_INSTALL_IN_PROGRESS,
    STATUS_WAITING_USER_INSTALL_CLICK,
    STATUS_WAITING_USER_UAC,
    confirm_user_completed,
    get_status_grade,
    prepare_user_install,
)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


def test_prepare_returns_waiting_user_click():
    r = prepare_user_install(
        installer_safe_name="delfino-g3.exe",
        source_host="download.kbstar.com",
        sha256="abc123",
        signature_status="Valid",
    )
    assert r["status"] == STATUS_WAITING_USER_INSTALL_CLICK


def test_auto_execute_always_false():
    r = prepare_user_install(
        installer_safe_name="setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="Valid",
    )
    assert r["auto_execute"] is False


def test_invalid_signature_rejected():
    r = prepare_user_install(
        installer_safe_name="setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="NotSigned",
    )
    assert r["status"] == "SIGNATURE_INVALID"


def test_safe_name_strips_path():
    r = prepare_user_install(
        installer_safe_name="C:\\Users\\user\\setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="Valid",
    )
    assert r["installer_safe_name"] == "setup.exe"


def test_no_local_path_in_result():
    r = prepare_user_install(
        installer_safe_name="setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="Valid",
    )
    for key in r:
        assert "local_path" not in key.lower()
        assert "full_path" not in key.lower()


def test_safe_fields_always_false():
    r = prepare_user_install(
        installer_safe_name="setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="Valid",
    )
    for f in _SAFE_FIELDS:
        assert r.get(f) is False


def test_user_guide_message_present():
    r = prepare_user_install(
        installer_safe_name="setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="Valid",
    )
    assert "더블클릭" in r["message"]
    assert "UAC" in r["message"]


def test_confirm_user_completed():
    r = confirm_user_completed("task-1", "setup.exe", target_domain="bank.example.com")
    assert r["status"] == STATUS_USER_INSTALL_IN_PROGRESS
    assert r["installer_safe_name"] == "setup.exe"


def test_get_status_grade_uac():
    assert get_status_grade(STATUS_WAITING_USER_UAC) == "USER_DIRECT_REQUIRED"


def test_get_status_grade_install_click():
    assert get_status_grade(STATUS_WAITING_USER_INSTALL_CLICK) == "USER_DIRECT_REQUIRED"


def test_get_status_grade_completed():
    assert get_status_grade(STATUS_INSTALL_COMPLETED_DETECTED) == "AUTO_ALLOWED"


def test_get_status_grade_retry_ready():
    assert get_status_grade(STATUS_RETRY_ORIGINAL_TASK_READY) == "AUTO_ALLOWED"


def test_signature_invalid_no_auto_execute():
    r = prepare_user_install(
        installer_safe_name="setup.exe",
        source_host="example.com",
        sha256="hash",
        signature_status="NotSigned",
    )
    # SIGNATURE_INVALID 결과에도 자동 실행 없음
    assert r.get("auto_execute") is not True
