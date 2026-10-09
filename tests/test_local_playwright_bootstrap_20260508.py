"""Playwright bootstrap 모듈 테스트

playwright_bootstrap.py의 상태 진단, 정책 상수, 옵션 반환을 검증한다.
실제 Playwright 미설치 환경과 설치 환경 모두 고려한다.
"""
from __future__ import annotations

import types

import pytest

import core.agent_runtime.runtime.playwright.playwright_bootstrap as bootstrap
from core.agent_runtime.runtime.playwright.playwright_bootstrap import (
    _ALL_STATES,
    BROWSER_POLICY,
    NETWORK_BLOCKED,
    PERMISSION_DENIED,
    PLAYWRIGHT_BROWSER_MISSING,
    PLAYWRIGHT_INSTALL_FAILED,
    PLAYWRIGHT_INSTALL_REQUIRED,
    PLAYWRIGHT_LAUNCH_FAILED,
    PLAYWRIGHT_PACKAGE_MISSING,
    PLAYWRIGHT_READY,
    UNKNOWN_ERROR,
    _classify_launch_error,
    _get_playwright_version,
    _try_launch_chromium,
    check_playwright_status,
    ensure_playwright_ready,
    get_launch_options,
)

# ── 1. 상태 상수 완전성 ──────────────────────────────────────────────────────────

def test_all_states_defined():
    expected = {
        PLAYWRIGHT_READY, PLAYWRIGHT_PACKAGE_MISSING, PLAYWRIGHT_BROWSER_MISSING,
        PLAYWRIGHT_INSTALL_REQUIRED, PLAYWRIGHT_INSTALL_FAILED,
        PLAYWRIGHT_LAUNCH_FAILED, NETWORK_BLOCKED, PERMISSION_DENIED, UNKNOWN_ERROR,
    }
    assert expected == _ALL_STATES

def test_state_constants_are_strings():
    for s in _ALL_STATES:
        assert isinstance(s, str) and s

def test_all_states_unique():
    states_list = [
        PLAYWRIGHT_READY, PLAYWRIGHT_PACKAGE_MISSING, PLAYWRIGHT_BROWSER_MISSING,
        PLAYWRIGHT_INSTALL_REQUIRED, PLAYWRIGHT_INSTALL_FAILED,
        PLAYWRIGHT_LAUNCH_FAILED, NETWORK_BLOCKED, PERMISSION_DENIED, UNKNOWN_ERROR,
    ]
    assert len(states_list) == len(set(states_list))


# ── 2. BROWSER_POLICY 구조 ────────────────────────────────────────────────────

def test_browser_policy_keys():
    required_keys = {
        "headless_default", "headed_on_user_auth_required",
        "bring_to_front_on_auth_required", "close_browser_after_task",
        "keep_local_profile",
    }
    assert required_keys <= set(BROWSER_POLICY.keys())

def test_browser_policy_headless_default_true():
    assert BROWSER_POLICY["headless_default"] is True

def test_browser_policy_headed_on_auth_true():
    assert BROWSER_POLICY["headed_on_user_auth_required"] is True

def test_browser_policy_bring_to_front_true():
    assert BROWSER_POLICY["bring_to_front_on_auth_required"] is True

def test_browser_policy_close_after_task_false():
    assert BROWSER_POLICY["close_browser_after_task"] is False

def test_browser_policy_keep_local_profile_true():
    assert BROWSER_POLICY["keep_local_profile"] is True


# ── 3. get_launch_options ─────────────────────────────────────────────────────

def test_get_launch_options_default_headless():
    opts = get_launch_options(requires_user_auth=False)
    assert opts["headless"] is True
    assert opts["bring_to_front"] is False

def test_get_launch_options_auth_headed():
    opts = get_launch_options(requires_user_auth=True)
    assert opts["headless"] is False
    assert opts["bring_to_front"] is True

def test_get_launch_options_auth_has_reason():
    opts = get_launch_options(requires_user_auth=True)
    assert "reason" in opts and opts["reason"]

def test_get_launch_options_no_auth_has_reason():
    opts = get_launch_options(requires_user_auth=False)
    assert "reason" in opts and opts["reason"]

def test_get_launch_options_auth_reason_mentions_auth():
    opts = get_launch_options(requires_user_auth=True)
    assert "인증" in opts["reason"] or "auth" in opts["reason"].lower()


# ── 4. check_playwright_status 반환 구조 ─────────────────────────────────────

def test_check_playwright_status_returns_dict():
    result = check_playwright_status()
    assert isinstance(result, dict)

def test_check_playwright_status_has_required_keys():
    result = check_playwright_status()
    for key in ("status", "package_version", "browser_available", "message_ko", "browser_policy"):
        assert key in result

def test_check_playwright_status_status_is_known():
    result = check_playwright_status()
    assert result["status"] in _ALL_STATES

def test_check_playwright_status_browser_available_is_bool():
    result = check_playwright_status()
    assert isinstance(result["browser_available"], bool)

def test_check_playwright_status_message_ko_is_str():
    result = check_playwright_status()
    assert isinstance(result["message_ko"], str)

def test_check_playwright_status_policy_returned():
    result = check_playwright_status()
    assert result["browser_policy"] == dict(BROWSER_POLICY)


# ── 5. Playwright 설치 환경에서 READY 확인 ────────────────────────────────────

def test_playwright_ready_when_installed():
    """playwright 1.x가 설치된 환경에서 READY를 반환해야 한다."""
    pytest.importorskip("playwright")
    result = check_playwright_status()
    assert result["status"] == PLAYWRIGHT_READY, f"expected READY, got {result['status']}: {result['message_ko']}"

def test_playwright_ready_browser_available():
    pytest.importorskip("playwright")
    result = check_playwright_status()
    assert result["browser_available"] is True

def test_playwright_version_not_none_when_installed():
    pytest.importorskip("playwright")
    result = check_playwright_status()
    assert result["package_version"] is not None


# ── 6. ensure_playwright_ready ────────────────────────────────────────────────

def test_ensure_playwright_ready_no_install_returns_status():
    result = ensure_playwright_ready(auto_install=False)
    assert result["status"] in _ALL_STATES

def test_ensure_playwright_ready_installed_is_ready():
    pytest.importorskip("playwright")
    result = ensure_playwright_ready(auto_install=False)
    assert result["status"] == PLAYWRIGHT_READY


# ── 7. _classify_launch_error ─────────────────────────────────────────────────

def test_classify_executable_not_found():
    r = _classify_launch_error("Executable not found", None)
    assert r["status"] == PLAYWRIGHT_BROWSER_MISSING

def test_classify_permission_denied():
    r = _classify_launch_error("permission denied", None)
    assert r["status"] == PERMISSION_DENIED

def test_classify_unknown_error():
    r = _classify_launch_error("some random error message", None)
    assert r["status"] == PLAYWRIGHT_LAUNCH_FAILED

def test_classify_browser_missing_has_install_command():
    r = _classify_launch_error("Executable not found", None)
    assert r["install_command"] is not None

def test_try_launch_chromium_parses_subprocess_success(monkeypatch):
    def fake_run(*args, **kwargs):
        return types.SimpleNamespace(stdout="PLAYWRIGHT_LAUNCH_OK\n", stderr="", returncode=0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    ok, error = _try_launch_chromium()

    assert ok is True
    assert error == ""

def test_try_launch_chromium_parses_subprocess_error_marker(monkeypatch):
    def fake_run(*args, **kwargs):
        return types.SimpleNamespace(
            stdout="PLAYWRIGHT_LAUNCH_ERROR:PermissionError:access denied\n",
            stderr="Future exception was never retrieved",
            returncode=0,
        )

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    ok, error = _try_launch_chromium()

    assert ok is False
    assert error == "PermissionError:access denied"
    assert "Future exception" not in error


# ── 8. _get_playwright_version ────────────────────────────────────────────────

def test_get_playwright_version_returns_str_or_none():
    v = _get_playwright_version()
    assert v is None or isinstance(v, str)

def test_get_playwright_version_not_empty_when_installed():
    pytest.importorskip("playwright")
    v = _get_playwright_version()
    assert v and len(v) > 0
