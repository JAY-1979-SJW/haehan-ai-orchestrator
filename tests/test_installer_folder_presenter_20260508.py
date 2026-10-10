"""tests/test_installer_folder_presenter_20260508.py"""

import sys

import pytest

from core.agent_runtime.runtime.security_program.installer_folder_presenter import (
    PRESENT_FAILED,
    PRESENT_NOT_SUPPORTED,
    build_explorer_command,
    present_installer_in_explorer,
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


def test_build_explorer_command_format():
    cmd = build_explorer_command("C:\\path\\file.exe")
    assert cmd[0] == "explorer.exe"
    assert "/select" in cmd[1]
    assert "file.exe" in cmd[1]


def test_build_explorer_command_empty_raises():
    with pytest.raises(ValueError):
        build_explorer_command("")


def test_build_explorer_command_no_runas():
    # runas/ShellExecuteW 자동 권한 상승 사용 안 함
    cmd = build_explorer_command("C:\\path\\file.exe")
    cmd_str = " ".join(cmd).lower()
    assert "runas" not in cmd_str
    assert "shellexecutew" not in cmd_str


def test_build_explorer_command_no_silent():
    cmd = build_explorer_command("C:\\path\\file.exe")
    cmd_str = " ".join(cmd).lower()
    for flag in ("/silent", "/quiet", "/qn", "/s "):
        assert flag not in cmd_str


def test_present_nonexistent_file_returns_failed():
    r = present_installer_in_explorer(
        local_path="C:\\NotExist\\nofile.exe",
        installer_safe_name="nofile.exe",
        target_domain="example.com",
        task_id="t1",
    )
    if sys.platform.startswith("win"):
        assert r["status"] == PRESENT_FAILED
        assert r["opened"] is False


def test_present_non_windows_not_supported():
    if sys.platform.startswith("win"):
        pytest.skip("Windows 전용 테스트 스킵")
    r = present_installer_in_explorer(
        local_path="/tmp/setup.exe",
        installer_safe_name="setup.exe",
    )
    assert r["status"] == PRESENT_NOT_SUPPORTED


def test_result_has_no_local_path():
    r = present_installer_in_explorer(
        local_path="C:\\Users\\test\\setup.exe",
        installer_safe_name="setup.exe",
        task_id="t1",
    )
    for key in r:
        assert "local_path" not in key.lower()
        assert "full_path" not in key.lower()


def test_result_safe_name_only():
    r = present_installer_in_explorer(
        local_path="C:\\Users\\test\\Downloads\\setup.exe",
        installer_safe_name="C:\\path\\to\\setup.exe",
        task_id="t1",
    )
    assert r["installer_safe_name"] == "setup.exe"


def test_safe_fields_always_false():
    r = present_installer_in_explorer(
        local_path="C:\\NotExist\\nofile.exe",
        installer_safe_name="nofile.exe",
        task_id="t1",
    )
    for f in _SAFE_FIELDS:
        assert r.get(f) is False


def test_no_silent_flag_in_command():
    cmd = build_explorer_command("C:\\setup.exe")
    for arg in cmd:
        assert "/silent" not in arg.lower()
        assert "/qn" not in arg.lower()
