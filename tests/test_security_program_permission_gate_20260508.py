"""tests/test_security_program_permission_gate_20260508.py"""
import pytest

from core.agent_runtime.runtime.security_program.security_program_permission_gate import (
    consume_permission,
    create_install_permission,
    revoke_permission,
    validate_permission,
)


def _make_perm(**kwargs):
    defaults = {
        "domain": "bank.example.com",
        "installer_name": "setup.exe",
        "source_host": "bank.example.com",
    }
    defaults.update(kwargs)
    return create_install_permission(**defaults)


def test_create_permission_structure():
    p = _make_perm()
    assert p["action"] == "install_security_program"
    assert p["max_executions"] == 1
    assert p["execution_count"] == 0
    assert p["requires_user_uac"] is True
    assert p["audit_log_required"] is True
    assert p["status"] == "ACTIVE"


def test_permission_id_unique():
    p1 = _make_perm()
    p2 = _make_perm()
    assert p1["permission_id"] != p2["permission_id"]


def test_validate_permission_valid():
    p = _make_perm()
    r = validate_permission(p, "install_security_program",
                            "bank.example.com", "setup.exe", "bank.example.com")
    assert r["valid"] is True
    assert r["can_execute"] is True


def test_validate_wrong_action():
    p = _make_perm()
    r = validate_permission(p, "download_file",
                            "bank.example.com", "setup.exe", "bank.example.com")
    assert r["valid"] is False


def test_validate_wrong_domain():
    p = _make_perm()
    r = validate_permission(p, "install_security_program",
                            "evil.com", "setup.exe", "bank.example.com")
    assert r["valid"] is False


def test_validate_wrong_source_host():
    p = _make_perm()
    r = validate_permission(p, "install_security_program",
                            "bank.example.com", "setup.exe", "evil.com")
    assert r["valid"] is False


def test_validate_revoked_permission():
    p = _make_perm()
    p = revoke_permission(p)
    r = validate_permission(p, "install_security_program",
                            "bank.example.com", "setup.exe", "bank.example.com")
    assert r["valid"] is False


def test_consume_permission_exhausts():
    p = _make_perm()
    p = consume_permission(p)
    assert p["execution_count"] == 1
    assert p["status"] == "EXHAUSTED"


def test_validate_exhausted_permission():
    p = _make_perm()
    p = consume_permission(p)
    r = validate_permission(p, "install_security_program",
                            "bank.example.com", "setup.exe", "bank.example.com")
    assert r["valid"] is False


def test_invalid_installer_extension_raises():
    with pytest.raises(ValueError):
        create_install_permission(
            domain="bank.example.com",
            installer_name="install.bat",
            source_host="bank.example.com",
        )


def test_invalid_domain_raises():
    with pytest.raises(ValueError):
        create_install_permission(
            domain="invalid",
            installer_name="setup.exe",
            source_host="bank.example.com",
        )


def test_installer_name_strips_path():
    p = create_install_permission(
        domain="bank.example.com",
        installer_name="C:\\Users\\user\\Downloads\\setup.exe",
        source_host="bank.example.com",
    )
    assert p["installer_name"] == "setup.exe"
    assert "\\" not in p["installer_name"]


def test_hash_stored_in_permission():
    p = create_install_permission(
        domain="bank.example.com",
        installer_name="setup.exe",
        source_host="bank.example.com",
        installer_hash="abc123def456",
    )
    assert p["installer_hash"] == "abc123def456"


def test_hash_mismatch_invalid():
    p = create_install_permission(
        domain="bank.example.com",
        installer_name="setup.exe",
        source_host="bank.example.com",
        installer_hash="original_hash",
    )
    r = validate_permission(p, "install_security_program",
                            "bank.example.com", "setup.exe", "bank.example.com",
                            installer_hash="different_hash")
    assert r["valid"] is False
