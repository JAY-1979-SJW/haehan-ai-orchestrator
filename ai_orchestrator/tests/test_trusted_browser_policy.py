"""F-4C — local_agent.trusted_browser_policy 단위 테스트.

검증:
  A) is_allowed_trusted_site — hometax / 서브도메인 허용, 외부 차단
  B) action allowlist / blocklist
  C) validate_trusted_automation_request — 정상/raw 비밀/잘못된 host/
     blocked action / 다운로드 폴더 검증
  D) sanitize_trusted_result — raw 비밀 값 마스킹
  E) Google open-only 호스트는 trusted 진입에서 거절
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import trusted_browser_policy as tbp  # noqa: E402


# ─── A) is_allowed_trusted_site ──────────────────────────────────────────

@pytest.mark.parametrize("url_or_host", [
    "hometax.go.kr",
    "www.hometax.go.kr",
    "https://hometax.go.kr/",
    "https://www.hometax.go.kr/some/path",
    "https://teht.hometax.go.kr/",   # 서브도메인 허용
])
def test_is_allowed_trusted_site_accepts_hometax(url_or_host):
    assert tbp.is_allowed_trusted_site(url_or_host) is True


@pytest.mark.parametrize("url_or_host", [
    "",
    None,
    "naver.com",
    "https://google.com/",
    "https://accounts.google.com/",       # F-2 open-only — trusted 거절
    "https://www.youtube.com/",
    "https://hometax.go.kr.evil.com/",    # suffix injection
    "ftp://hometax.go.kr/",               # http(s) 외 스킴
    "javascript:alert(1)",
    "  ",
    "a b",
])
def test_is_allowed_trusted_site_rejects_others(url_or_host):
    assert tbp.is_allowed_trusted_site(url_or_host) is False


# ─── B) action allow / block ─────────────────────────────────────────────

@pytest.mark.parametrize("action", list(tbp.ALLOWED_TRUSTED_ACTIONS))
def test_allowed_actions_present(action):
    assert tbp.is_allowed_trusted_action(action) is True
    assert tbp.is_blocked_trusted_action(action) is False


@pytest.mark.parametrize("action", list(tbp.BLOCKED_TRUSTED_ACTIONS))
def test_blocked_actions_present(action):
    assert tbp.is_blocked_trusted_action(action) is True
    assert tbp.is_allowed_trusted_action(action) is False


@pytest.mark.parametrize("action", [
    "submit_tax_return", "pay_tax", "issue_tax_invoice",
    "export_cookie", "export_session", "export_storage",
    "captcha_bypass", "read_saved_password",
])
def test_known_dangerous_actions_blocked(action):
    assert tbp.is_blocked_trusted_action(action)


# ─── C) validate_trusted_automation_request ──────────────────────────────

def _good_secret_ref() -> dict:
    return {
        "site_key": "hometax",
        "login_method": "certificate",
        "user_id_secret_id": "hometax_user_id",
        "password_secret_id": "hometax_cert_password",
    }


def test_validate_request_accepts_observe_action():
    out = tbp.validate_trusted_automation_request({
        "action": "observe_authenticated_page",
        "target_url": "https://www.hometax.go.kr/",
        "site_key": "hometax",
    })
    assert out["ok"] is True
    assert out["error_code"] == ""


def test_validate_request_accepts_login_action_with_secret_ref():
    out = tbp.validate_trusted_automation_request({
        "action": "trusted_login",
        "target_url": "https://hometax.go.kr/",
        "site_key": "hometax",
        "secret_ref": _good_secret_ref(),
    })
    assert out["ok"] is True


def test_validate_request_rejects_raw_password():
    out = tbp.validate_trusted_automation_request({
        "action": "trusted_login",
        "target_url": "https://hometax.go.kr/",
        "password": "leak-this-must-not-pass",
    })
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"
    assert "leak-this-must-not-pass" not in repr(out)


def test_validate_request_rejects_cookie_param():
    out = tbp.validate_trusted_automation_request({
        "action": "observe_authenticated_page",
        "target_url": "https://hometax.go.kr/",
        "cookie": "session=AAA",
    })
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"


def test_validate_request_rejects_storage_state_param():
    out = tbp.validate_trusted_automation_request({
        "action": "observe_authenticated_page",
        "target_url": "https://hometax.go.kr/",
        "storage_state": "{}",
    })
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"


def test_validate_request_rejects_blocked_action_pay_tax():
    out = tbp.validate_trusted_automation_request({
        "action": "pay_tax",
        "target_url": "https://hometax.go.kr/",
    })
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_BLOCKED"
    assert any(w.startswith("blocked_action:") for w in out["warnings"])


def test_validate_request_rejects_blocked_action_submit_tax_return():
    out = tbp.validate_trusted_automation_request({
        "action": "submit_tax_return",
        "target_url": "https://hometax.go.kr/",
    })
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_BLOCKED"


def test_validate_request_rejects_blocked_action_issue_tax_invoice():
    out = tbp.validate_trusted_automation_request({
        "action": "issue_tax_invoice",
        "target_url": "https://hometax.go.kr/",
    })
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_BLOCKED"


def test_validate_request_rejects_unknown_host():
    out = tbp.validate_trusted_automation_request({
        "action": "observe_authenticated_page",
        "target_url": "https://example.com/",
    })
    assert out["ok"] is False
    assert out["error_code"] == "HOST_NOT_ALLOWED"


def test_validate_request_rejects_google_host_at_trusted_layer():
    out = tbp.validate_trusted_automation_request({
        "action": "observe_authenticated_page",
        "target_url": "https://accounts.google.com/",
    })
    assert out["ok"] is False
    assert out["error_code"] == "HOST_NOT_ALLOWED"


def test_validate_request_rejects_unknown_action():
    out = tbp.validate_trusted_automation_request({
        "action": "do_something_random",
        "target_url": "https://hometax.go.kr/",
    })
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_NOT_ALLOWED"


def test_validate_request_rejects_missing_target_url():
    out = tbp.validate_trusted_automation_request({
        "action": "observe_authenticated_page",
    })
    assert out["ok"] is False
    assert out["error_code"] == "MISSING_TARGET_URL"


def test_validate_request_rejects_invalid_secret_ref():
    bad_ref = _good_secret_ref()
    bad_ref["password_secret_id"] = "x"   # too short
    out = tbp.validate_trusted_automation_request({
        "action": "trusted_login",
        "target_url": "https://hometax.go.kr/",
        "secret_ref": bad_ref,
    })
    assert out["ok"] is False
    assert out["error_code"] == "INVALID_PASSWORD_SECRET_ID"


# ─── 다운로드 폴더 ──────────────────────────────────────────────────────

def test_validate_download_requires_path(tmp_path):
    out = tbp.validate_trusted_automation_request(
        {
            "action": "download_file",
            "target_url": "https://hometax.go.kr/",
        },
        allowed_download_roots=[str(tmp_path)],
    )
    assert out["ok"] is False
    assert out["error_code"] == "MISSING_DOWNLOAD_PATH"


def test_validate_download_path_in_allowed_root(tmp_path):
    target = os.path.join(str(tmp_path), "hometax", "2026-04")
    out = tbp.validate_trusted_automation_request(
        {
            "action": "download_file",
            "target_url": "https://hometax.go.kr/",
            "download_path": target,
        },
        allowed_download_roots=[str(tmp_path)],
    )
    assert out["ok"] is True


def test_validate_download_path_outside_allowed_root(tmp_path):
    out = tbp.validate_trusted_automation_request(
        {
            "action": "download_file",
            "target_url": "https://hometax.go.kr/",
            "download_path": str(tmp_path.parent / "elsewhere"),
        },
        allowed_download_roots=[str(tmp_path)],
    )
    assert out["ok"] is False
    assert out["error_code"] == "DOWNLOAD_PATH_NOT_IN_ALLOWED_ROOTS"


def test_validate_download_blocks_system_path(tmp_path):
    blocked = "C:\\Windows\\System32\\evil"
    out = tbp.validate_trusted_automation_request(
        {
            "action": "download_file",
            "target_url": "https://hometax.go.kr/",
            "download_path": blocked,
        },
        allowed_download_roots=[str(tmp_path)],
    )
    assert out["ok"] is False
    # 시스템 경로 prefix 매칭이 우선이어야 한다.
    assert out["error_code"] == "DOWNLOAD_PATH_BLOCKED"


def test_validate_download_requires_configured_roots():
    out = tbp.validate_trusted_automation_request({
        "action": "download_file",
        "target_url": "https://hometax.go.kr/",
        "download_path": "/tmp/safe",
    })
    assert out["ok"] is False
    assert out["error_code"] == "DOWNLOAD_ROOTS_NOT_CONFIGURED"


# ─── D) sanitize_trusted_result ──────────────────────────────────────────

def test_sanitize_result_masks_password_value():
    raw = {
        "site_key": "hometax",
        "password": "leak-XYZ",
        "user_id_secret_id": "hometax_user_id",
    }
    out = tbp.sanitize_trusted_result(raw)
    assert out["password"] == "***"
    assert "leak-XYZ" not in repr(out)
    assert out["user_id_secret_id"].startswith("home")
    assert out["user_id_secret_id"].endswith("***")


def test_sanitize_result_recurses():
    raw = {"nested": {"cookie": "leak-cookie"}}
    out = tbp.sanitize_trusted_result(raw)
    assert "leak-cookie" not in repr(out)
