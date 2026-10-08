"""validate_site_policy_config 검증 테스트."""

from __future__ import annotations

from scripts.archive.one_off.validate_site_policy_config import validate_config


def _base() -> dict:
    return {
        "site_id": "test",
        "label": "테스트 사이트",
        "allowed_hosts": ["www.test.go.kr"],
        "allowed_paths": ["/notice"],
        "blocked_paths": ["/admin", "/login"],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "login_mode": "PUBLIC_READONLY",
        "credential_policy": "NO_CREDENTIAL_CAPTURE",
        "capture_policy": "NO_SCREENSHOT_NO_HAR",
        "risk_level": "MEDIUM",
    }


def test_valid_config_passes():
    assert validate_config(_base())["ok"] is True


def test_missing_required_field_fails():
    cfg = _base()
    del cfg["execution_location"]
    assert validate_config(cfg)["ok"] is False


def test_invalid_execution_location_fails():
    cfg = _base()
    cfg["execution_location"] = "SERVER_REMOTE"
    assert validate_config(cfg)["ok"] is False


def test_invalid_credential_policy_fails():
    cfg = _base()
    cfg["credential_policy"] = "ALLOWED"
    assert validate_config(cfg)["ok"] is False


def test_invalid_capture_policy_fails():
    cfg = _base()
    cfg["capture_policy"] = "SCREENSHOT_OK"
    assert validate_config(cfg)["ok"] is False


def test_invalid_risk_level_fails():
    cfg = _base()
    cfg["risk_level"] = "EXTREME"
    assert validate_config(cfg)["ok"] is False


def test_empty_allowed_hosts_fails():
    cfg = _base()
    cfg["allowed_hosts"] = []
    assert validate_config(cfg)["ok"] is False


def test_dangerous_path_in_allowed_paths_warns():
    cfg = _base()
    cfg["allowed_paths"] = ["/login/path"]
    result = validate_config(cfg)
    assert result["ok"] is True
    assert any("login" in w for w in result.get("warnings", []))


def test_no_blocked_login_admin_warns():
    cfg = _base()
    cfg["blocked_paths"] = ["/other"]
    result = validate_config(cfg)
    assert result["ok"] is True
    assert len(result.get("warnings", [])) > 0
