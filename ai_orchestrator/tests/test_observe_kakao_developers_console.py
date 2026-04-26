"""KAKAO-DEV-2 — scripts/observe_kakao_developers_console.py 단위 검증.

검증 항목:
- 결과 디렉터리/JSON/MD/next_actions 생성
- login_state 분류 (logged_in / login_required / unknown)
- 메뉴 신호 감지 (kakao_login, consent, biz_app 등)
- secret-like 값 마스킹 / secret_like_values_captured 플래그
- 쿠키/session/storage_state 추출 코드 없음 (AST)
- 비밀번호/OTP 저장 코드 없음 (AST)
- 앱 삭제 / secret 재발급 / 실제 신청 제출 코드 없음 (AST)
- 외부 write action 코드 없음 (AST)
- 다음 자동화 후보 산출
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import scripts.observe_kakao_developers_console as _obs


# ─── mock helpers ────────────────────────────────────────────────────────────

def _make_observer_result(
    *,
    success: bool = True,
    page_state: str = "login_required",
    title: str = "Kakao Developers",
    text_excerpt: str = "로그인 카카오 계정으로 로그인하세요.",
    status_code: int = 200,
    links: list | None = None,
    buttons: list | None = None,
    warnings: list | None = None,
) -> dict:
    return {
        "success": success,
        "error_code": "",
        "warnings": warnings or [],
        "page_state": page_state,
        "title": title,
        "status_code": status_code,
        "text_excerpt": text_excerpt,
        "text_length": len(text_excerpt),
        "links_count": len(links or []),
        "buttons_count": len(buttons or []),
        "forms_count": 0,
        "inputs_count": 0,
        "links": links or [],
        "buttons": buttons or [],
        "screenshot_path": None,
    }


# ─── 분류 로직 ────────────────────────────────────────────────────────────────

def test_classify_login_required_by_tokens():
    result = _make_observer_result(text_excerpt="카카오 계정으로 로그인하세요.")
    assert _obs._classify_login_state(result) == "login_required"


def test_classify_logged_in_by_tokens():
    result = _make_observer_result(
        text_excerpt="내 애플리케이션 로그아웃 대시보드",
        page_state="authenticated",
    )
    assert _obs._classify_login_state(result) == "logged_in"


def test_classify_unknown_when_no_signals():
    result = _make_observer_result(text_excerpt="환영합니다 개발자센터", page_state="unknown")
    assert _obs._classify_login_state(result) == "unknown"


def test_classify_login_required_by_page_state():
    result = _make_observer_result(page_state="login_required", text_excerpt="")
    assert _obs._classify_login_state(result) == "login_required"


# ─── 메뉴 신호 ────────────────────────────────────────────────────────────────

def test_menu_signals_kakao_login_found():
    result = _make_observer_result(
        text_excerpt="카카오 로그인 활성화 설정",
        links=[{"text": "카카오 로그인"}, {"text": "동의항목"}],
    )
    sigs = _obs._extract_menu_signals(result)
    assert sigs["kakao_login_menu_found"] is True
    assert sigs["consent_items_menu_found"] is True


def test_menu_signals_biz_app():
    result = _make_observer_result(
        text_excerpt="비즈앱 전환 비즈니스 앱 신청",
    )
    sigs = _obs._extract_menu_signals(result)
    assert sigs["business_app_menu_found"] is True


def test_menu_signals_all_false_when_empty():
    result = _make_observer_result(text_excerpt="", links=[], buttons=[])
    sigs = _obs._extract_menu_signals(result)
    assert not any(sigs.values())


# ─── secret 마스킹 ────────────────────────────────────────────────────────────

def test_secret_masking_detects_long_hex():
    text = "REST API Key: abcdef1234567890abcdef1234567890"
    safe = _obs._sanitize_result_for_output({"text_excerpt": text, "links": [], "buttons": []})
    assert "[MASKED]" in safe["text_excerpt"]
    assert safe["secret_like_detected_in_text"] is True


def test_secret_masking_safe_text_unchanged():
    text = "내 애플리케이션 목록을 확인하세요."
    safe = _obs._sanitize_result_for_output({"text_excerpt": text, "links": [], "buttons": []})
    assert "[MASKED]" not in safe["text_excerpt"]
    assert safe["secret_like_detected_in_text"] is False


def test_sanitize_drops_raw_links_href():
    result = _make_observer_result(
        links=[{"text": "링크1", "href": "https://example.com/secret?token=abc"}]
    )
    safe = _obs._sanitize_result_for_output(result)
    assert "href" not in safe["links"][0]
    assert safe["links"][0]["text"] == "링크1"


# ─── observe() 통합 (mock browser) ──────────────────────────────────────────

def test_observe_creates_result_files(tmp_path):
    mock_result = _make_observer_result(text_excerpt="로그인 카카오 계정으로 로그인")
    with patch(
        "scripts.observe_kakao_developers_console.observe_public_browser_page",
        return_value=mock_result,
    ):
        output = _obs.observe(
            url="https://developers.kakao.com/",
            out_dir=str(tmp_path),
            capture_screenshot=False,
        )

    run_dirs = list(tmp_path.glob("kakao_observe_*"))
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    assert (run_dir / "observe.json").exists()
    assert (run_dir / "observe.md").exists()
    assert (run_dir / "next_actions.md").exists()
    assert (run_dir / "menu_map.json").exists()


def test_observe_json_structure(tmp_path):
    mock_result = _make_observer_result(text_excerpt="로그인하세요.")
    with patch(
        "scripts.observe_kakao_developers_console.observe_public_browser_page",
        return_value=mock_result,
    ):
        output = _obs.observe(
            url="https://developers.kakao.com/",
            out_dir=str(tmp_path),
            capture_screenshot=False,
        )

    assert output["console_name"] == "kakao_developers"
    assert output["login_state"] == "login_required"
    assert output["auth_principal_required"] is True
    assert output["auth_principal_type"] == "developer_console_operator"
    assert output["secret_like_values_captured"] is False
    assert isinstance(output["recommended_next_actions"], list)
    assert len(output["recommended_next_actions"]) > 0


def test_observe_login_required_sets_auth_principal(tmp_path):
    mock_result = _make_observer_result(page_state="login_required", text_excerpt="")
    with patch(
        "scripts.observe_kakao_developers_console.observe_public_browser_page",
        return_value=mock_result,
    ):
        output = _obs.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert output["auth_principal_required"] is True
    assert output["auth_principal_type"] == "developer_console_operator"


def test_observe_logged_in_clears_auth_principal(tmp_path):
    mock_result = _make_observer_result(
        text_excerpt="내 애플리케이션 로그아웃 대시보드",
        page_state="authenticated",
    )
    with patch(
        "scripts.observe_kakao_developers_console.observe_public_browser_page",
        return_value=mock_result,
    ):
        output = _obs.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert output["login_state"] == "logged_in"
    assert output["auth_principal_required"] is False
    assert output["auth_principal_type"] is None


def test_observe_secret_masking_in_output(tmp_path):
    mock_result = _make_observer_result(
        text_excerpt="REST API Key: abcdef1234567890abcdef1234567890"
    )
    with patch(
        "scripts.observe_kakao_developers_console.observe_public_browser_page",
        return_value=mock_result,
    ):
        output = _obs.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert output["secret_like_values_captured"] is True
    page_obs = output.get("page_observation", {})
    assert "[MASKED]" in page_obs.get("text_excerpt", "")


# ─── 다음 후보 산출 ────────────────────────────────────────────────────────────

def test_next_actions_login_required_includes_auth_task():
    actions = _obs._build_next_actions("login_required", {})
    keys = [a["task_key"] for a in actions]
    assert "KAKAO-DEV-2-AUTH" in keys


def test_next_actions_logged_in_includes_kakao_dev_3():
    actions = _obs._build_next_actions("logged_in", {"apps_visible": True})
    keys = [a["task_key"] for a in actions]
    assert "KAKAO-DEV-3" in keys


def test_next_actions_always_includes_secret_ops():
    actions = _obs._build_next_actions("unknown", {})
    keys = [a["task_key"] for a in actions]
    assert "SECRET-OPS-1" in keys


def test_next_actions_kakao_dev_5_approval_required():
    actions = _obs._build_next_actions("logged_in", {})
    dev5 = next((a for a in actions if a["task_key"] == "KAKAO-DEV-5"), None)
    assert dev5 is not None
    assert dev5["approval_required"] is True


# ─── AST 보안 검증 ────────────────────────────────────────────────────────────

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "observe_kakao_developers_console.py"


def _get_ast_source() -> str:
    return _SCRIPT_PATH.read_text(encoding="utf-8")


_FORBIDDEN_AST_PATTERNS = [
    "context.storage_state",
    ".storage_state(",
    "cookies()",
    "add_cookies",
    "localStorage",
    "sessionStorage",
    "page.fill",
    "page.type",
    "page.click",
    "page.press",
    "page.keyboard",
    "page.mouse",
    "delete_app",
    "regenerate_secret",
    "os.system",
    "shell=True",
]


@pytest.mark.parametrize("pattern", _FORBIDDEN_AST_PATTERNS)
def test_no_forbidden_pattern_in_source(pattern):
    src = _get_ast_source()
    assert pattern not in src, f"forbidden pattern found in script: {pattern!r}"


def test_script_has_no_submit_action():
    src = _get_ast_source()
    assert "auto_submit" not in src or "auto_submit_allowed" not in src


def test_secret_like_value_never_written_to_json(tmp_path):
    mock_result = _make_observer_result(
        text_excerpt="Admin Key: 9f1234567890abcdef1234567890abcdef12"
    )
    with patch(
        "scripts.observe_kakao_developers_console.observe_public_browser_page",
        return_value=mock_result,
    ):
        _obs.observe(out_dir=str(tmp_path), capture_screenshot=False)

    run_dir = next(tmp_path.glob("kakao_observe_*"))
    json_content = (run_dir / "observe.json").read_text(encoding="utf-8")
    assert "9f1234567890abcdef1234567890abcdef12" not in json_content
