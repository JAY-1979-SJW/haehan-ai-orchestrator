"""tests/test_security_installer_policy_20260508.py"""

from core.agent_runtime.runtime.security_program.security_installer_policy import (
    POLICY_ALLOWED,
    POLICY_BLOCKED,
    POLICY_NEEDS_PERMISSION,
    POLICY_NEEDS_USER_DIRECT,
    check_silent_flags,
    evaluate_installer,
    record_installer_hash,
)


def test_official_exe_without_permission_needs_permission():
    r = evaluate_installer("setup.exe", "bank.example.com", is_official_source=True)
    assert r["policy"] == POLICY_NEEDS_PERMISSION
    assert r["executable"] is False
    assert r["grade"] == "USER_DELEGATED_PERMISSION_REQUIRED"


def test_official_exe_with_permission_allowed():
    r = evaluate_installer("setup.exe", "bank.example.com", is_official_source=True, has_user_permission=True)
    assert r["policy"] == POLICY_ALLOWED
    assert r["executable"] is True


def test_unofficial_source_needs_user_direct():
    r = evaluate_installer("setup.exe", "bank.example.com", is_official_source=False, has_user_permission=True)
    assert r["policy"] == POLICY_NEEDS_USER_DIRECT


def test_bat_extension_blocked():
    r = evaluate_installer("install.bat", "bank.example.com", is_official_source=True, has_user_permission=True)
    assert r["policy"] == POLICY_BLOCKED


def test_ps1_extension_blocked():
    r = evaluate_installer("install.ps1", "bank.example.com", is_official_source=True, has_user_permission=True)
    assert r["policy"] == POLICY_BLOCKED


def test_silent_flag_blocked():
    r = evaluate_installer(
        "setup.exe", "bank.example.com", is_official_source=True, has_user_permission=True, install_args=["/silent"]
    )
    assert r["policy"] == POLICY_BLOCKED
    assert any("무인 설치" in v for v in r["violations"])


def test_quiet_flag_blocked():
    r = evaluate_installer(
        "setup.exe", "bank.example.com", is_official_source=True, has_user_permission=True, install_args=["/quiet"]
    )
    assert r["policy"] == POLICY_BLOCKED


def test_qn_flag_blocked():
    r = evaluate_installer(
        "setup.msi", "bank.example.com", is_official_source=True, has_user_permission=True, install_args=["/qn"]
    )
    assert r["policy"] == POLICY_BLOCKED


def test_normal_args_allowed():
    r = evaluate_installer(
        "setup.exe", "bank.example.com", is_official_source=True, has_user_permission=True, install_args=["/lang=ko"]
    )
    assert r["policy"] == POLICY_ALLOWED


def test_exe_requires_uac():
    r = evaluate_installer("setup.exe", "bank.example.com", is_official_source=True, has_user_permission=True)
    assert r["requires_uac"] is True


def test_check_silent_flags():
    flags = check_silent_flags(["/silent", "/lang=ko", "--quiet"])
    assert "/silent" in flags
    assert "--quiet" in flags
    assert "/lang=ko" not in flags


def test_record_installer_hash():
    h = record_installer_hash(b"test data")
    assert isinstance(h, str)
    assert len(h) == 64


def test_file_size_limit():
    large = 600 * 1024 * 1024
    r = evaluate_installer(
        "setup.exe", "bank.example.com", is_official_source=True, has_user_permission=True, file_size_bytes=large
    )
    assert r["policy"] != POLICY_ALLOWED
