"""tests/test_security_program_install_result_sanitizer_20260508.py"""

from core.agent_runtime.runtime.security_program.security_program_install_result_sanitizer import (
    build_safe_report,
    check_result_has_no_sensitive_data,
    sanitize_install_result,
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


def test_sanitize_removes_local_path():
    raw = {
        "task_id": "t1",
        "domain": "bank.example.com",
        "installer_safe_name": "setup.exe",
        "source_host": "bank.example.com",
        "status": "INSTALL_COMPLETED",
        "local_path": "C:\\Users\\user\\Downloads\\setup.exe",
    }
    r = sanitize_install_result(raw)
    assert "local_path" not in r
    assert r["task_id"] == "t1"


def test_sanitize_removes_password():
    raw = {
        "task_id": "t1",
        "domain": "bank.example.com",
        "installer_safe_name": "setup.exe",
        "source_host": "bank.example.com",
        "status": "COMPLETED",
        "password_collected": True,
    }
    r = sanitize_install_result(raw)
    assert r.get("password_collected") is False


def test_sanitize_removes_cookie():
    raw = {
        "task_id": "t1",
        "domain": "bank.example.com",
        "installer_safe_name": "setup.exe",
        "source_host": "bank.example.com",
        "status": "COMPLETED",
        "cookie_value": "secret_cookie",
    }
    r = sanitize_install_result(raw)
    assert "cookie_value" not in r


def test_safe_fields_always_false():
    raw = {"task_id": "t1", "domain": "d", "installer_safe_name": "s", "source_host": "s", "status": "OK"}
    r = sanitize_install_result(raw)
    for f in _SAFE_FIELDS:
        assert r.get(f) is False, f"{f} != False"


def test_check_no_sensitive_data_clean():
    report = build_safe_report(
        task_id="t1",
        domain="bank.example.com",
        installer_safe_name="setup.exe",
        source_host="bank.example.com",
        status="COMPLETED",
    )
    violations = check_result_has_no_sensitive_data(report)
    assert violations == []


def test_check_detects_cookie_exported_true():
    report = build_safe_report(
        task_id="t1",
        domain="bank.example.com",
        installer_safe_name="setup.exe",
        source_host="bank.example.com",
        status="COMPLETED",
    )
    report["cookie_exported"] = True
    violations = check_result_has_no_sensitive_data(report)
    assert len(violations) > 0


def test_check_detects_password_collected_true():
    report = build_safe_report(
        task_id="t1",
        domain="bank.example.com",
        installer_safe_name="setup.exe",
        source_host="bank.example.com",
        status="COMPLETED",
    )
    report["password_collected"] = True
    violations = check_result_has_no_sensitive_data(report)
    assert len(violations) > 0


def test_build_safe_report_structure():
    r = build_safe_report(
        task_id="t1",
        domain="bank.example.com",
        installer_safe_name="setup.exe",
        source_host="bank.example.com",
        status="INSTALL_COMPLETED",
        install_detected=True,
        restart_required=False,
        retry_ready=True,
    )
    assert r["task_id"] == "t1"
    assert r["install_detected"] is True
    assert r["retry_ready"] is True
    assert r["server_browser_used"] is False


def test_sanitize_removes_npki():
    raw = {
        "task_id": "t1",
        "domain": "d",
        "installer_safe_name": "s",
        "source_host": "s",
        "status": "OK",
        "npki_path": "/usr/NPKI/CrossCert",
    }
    r = sanitize_install_result(raw)
    assert "npki_path" not in r


def test_sanitize_removes_otp():
    raw = {
        "task_id": "t1",
        "domain": "d",
        "installer_safe_name": "s",
        "source_host": "s",
        "status": "OK",
        "otp_value": "123456",
    }
    r = sanitize_install_result(raw)
    assert "otp_value" not in r
