"""SESSION-HEALTH-1 — check_developer_console_sessions 유닛 테스트.

보안 경계 검증:
- 비밀번호/OTP 저장 없음
- 쿠키/session export 없음
- password input value 읽기 없음
- pending task 파일 생성 검증 (NEEDS_REAUTH)
- READY_LOGGED_IN 분류 검증
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_developer_console_sessions import (
    _classify_session,
    _build_pending_task,
    check_all,
    _CONSOLES,
)


# ---------------------------------------------------------------------------
# _classify_session
# ---------------------------------------------------------------------------


def test_classify_logged_in_kakao():
    result = {"success": True, "text_excerpt": "내 애플리케이션 로그아웃", "title": "Kakao Developers"}
    assert _classify_session("kakao_developers", result) == "READY_LOGGED_IN"


def test_classify_needs_reauth_kakao():
    result = {"success": True, "text_excerpt": "카카오 계정으로 로그인", "title": "로그인"}
    assert _classify_session("kakao_developers", result) == "NEEDS_REAUTH"


def test_classify_needs_reauth_via_page_state():
    result = {"success": True, "page_state": "login_required", "text_excerpt": "", "title": ""}
    assert _classify_session("naver_developers", result) == "NEEDS_REAUTH"


def test_classify_unknown_when_no_signal():
    result = {"success": True, "text_excerpt": "서버 오류 500", "title": "Error"}
    assert _classify_session("kakao_developers", result) == "UNKNOWN"


def test_classify_blocked():
    result = {"success": False, "error_code": "BLOCKED", "text_excerpt": "", "title": ""}
    assert _classify_session("kakao_developers", result) == "BLOCKED"


def test_classify_logged_in_google():
    result = {
        "success": True,
        "text_excerpt": "dashboard project apis & services",
        "title": "Google Cloud Console",
    }
    assert _classify_session("google_cloud_console", result) == "READY_LOGGED_IN"


# ---------------------------------------------------------------------------
# _build_pending_task
# ---------------------------------------------------------------------------


def test_build_pending_task_creates_file(tmp_path):
    console = _CONSOLES[0]  # kakao_developers
    pending_dir = tmp_path / "pending_auth_tasks"
    path = _build_pending_task(console, "20260426_120000", pending_dir)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["console"] == "kakao_developers"
    assert data["status"] == "NEEDS_REAUTH"
    assert data["profile_name"] == "kakao_developer_console"
    assert "resume_command" in data
    assert "next_action_after_login" in data


def test_pending_task_no_password_field(tmp_path):
    console = _CONSOLES[0]
    pending_dir = tmp_path / "pending"
    path = _build_pending_task(console, "20260426_120001", pending_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "password" not in data
    assert "cookie" not in data
    assert "session" not in data
    assert "otp" not in data


# ---------------------------------------------------------------------------
# check_all — mock observe
# ---------------------------------------------------------------------------


def _mock_logged_in(url, **kwargs):
    return {
        "success": True,
        "status_code": 200,
        "text_excerpt": "내 애플리케이션 로그아웃 dashboard project apis & services",
        "title": "Console",
        "warnings": [],
    }


def _mock_needs_reauth(url, **kwargs):
    return {
        "success": True,
        "status_code": 200,
        "page_state": "login_required",
        "text_excerpt": "로그인",
        "title": "Login",
        "warnings": [],
    }


def test_check_all_all_logged_in(tmp_path):
    with patch(
        "scripts.check_developer_console_sessions.observe_public_browser_page",
        side_effect=_mock_logged_in,
    ):
        result = check_all(out_dir=str(tmp_path))

    assert result["summary"]["READY_LOGGED_IN"] == 3
    assert result["summary"]["NEEDS_REAUTH"] == 0
    assert Path(result["output_json"]).exists()
    assert Path(result["output_md"]).exists()


def test_check_all_needs_reauth_creates_pending(tmp_path):
    with patch(
        "scripts.check_developer_console_sessions.observe_public_browser_page",
        side_effect=_mock_needs_reauth,
    ):
        result = check_all(out_dir=str(tmp_path))

    assert result["summary"]["NEEDS_REAUTH"] == 3
    pending_dir = tmp_path / "pending_auth_tasks"
    assert pending_dir.exists()
    pending_files = list(pending_dir.glob("*.json"))
    assert len(pending_files) == 3


def test_check_all_security_fields(tmp_path):
    with patch(
        "scripts.check_developer_console_sessions.observe_public_browser_page",
        side_effect=_mock_logged_in,
    ):
        result = check_all(out_dir=str(tmp_path))

    sec = result["security"]
    assert sec["password_stored"] is False
    assert sec["cookie_exported"] is False
    assert sec["password_input_read"] is False
    assert sec["otp_stored"] is False
    assert sec["session_exported"] is False


def test_check_all_single_console(tmp_path):
    with patch(
        "scripts.check_developer_console_sessions.observe_public_browser_page",
        side_effect=_mock_logged_in,
    ):
        result = check_all(out_dir=str(tmp_path), consoles=[_CONSOLES[0]])

    assert len(result["consoles"]) == 1
    assert result["consoles"][0]["console"] == "kakao_developers"


def test_check_all_output_md_contains_security_section(tmp_path):
    with patch(
        "scripts.check_developer_console_sessions.observe_public_browser_page",
        side_effect=_mock_logged_in,
    ):
        result = check_all(out_dir=str(tmp_path))

    md = Path(result["output_md"]).read_text(encoding="utf-8")
    assert "보안 확인" in md
    assert "비밀번호 저장: 없음" in md
    assert "쿠키/session export: 없음" in md
