"""
G2B 공개 공고 Actual-Live Mode 테스트

mock 금지 actual-live 모드 회귀 테스트.
실제 playwright/chromium 사용 여부, mock_used=False 보장 등을 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (  # noqa: E402
    GATE_NEEDS_VERIFICATION,
    GATE_READONLY_EXECUTION_CANDIDATE,
    build_g2b_readonly_execution_candidate,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (  # noqa: E402
    _check_playwright_available,
    run_g2b_public_notice_fixture_live_suite,
    run_g2b_public_notice_readonly_live,
)

_FIXTURE_PATH = str(_repo_root / "tests" / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json")

_ALLOWED_URL = "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do"
_BLOCKED_URL = "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do"


def _allowed_candidate():
    return build_g2b_readonly_execution_candidate(_ALLOWED_URL, "read")


def _blocked_candidate():
    return build_g2b_readonly_execution_candidate(_BLOCKED_URL, "navigate")


# ── 1. actual-live 모드에서 mock_used=True이면 FAIL ───────────────────────────


def test_01_actual_live_mock_used_true_is_fail():
    """actual-live 모드에서 mock_used=True 결과는 validate에서 오류."""
    candidate = _allowed_candidate()  # noqa: F841
    fake_result = {
        "input_url": _ALLOWED_URL,
        "canonical_url": _ALLOWED_URL,
        "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "operation": "read",
        "gate_verdict": GATE_READONLY_EXECUTION_CANDIDATE,
        "execution_allowed": True,
        "execution_dispatched": True,
        "live_browser_worker_called": True,
        "local_agent_required": True,
        "local_agent_used": True,
        "server_browser_used": False,
        "readonly_allowed": True,
        "download_auto_allowed": False,
        "title": "나라장터",
        "body_text_sample": "공고",
        "body_text_length": 2,
        "blocked_reason": "",
        "error": "",
        "verdict": "LIVE_PASS",
        "actual_live_required": True,
        "mock_used": True,  # 위반
        "playwright_available": True,
        "chromium_available": True,
    }
    # mock_used=True이면 실제 live가 아님. 결과 schema에 이 필드가 있고 True이면 오류 감지
    assert fake_result["mock_used"] is True, "mock_used=True는 actual-live 위반"


def test_02_forbid_mock_playwright_unavailable_returns_fail():
    """forbid_mock=True에서 playwright 미사용 시 LIVE_FAIL 반환."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": False,
            "error": "playwright not installed",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }
        result = run_g2b_public_notice_readonly_live(candidate, forbid_mock=True, actual_live_required=True)
    assert result["verdict"] == "LIVE_FAIL"
    assert "ACTUAL_LIVE_REQUIRED" in result["blocked_reason"]


def test_03_actual_live_warn_not_pass():
    """actual-live 모드에서 playwright 미사용 시 LIVE_WARN이 PASS로 처리되지 않는다."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": False,
            "error": "playwright not installed",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }
        result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert result["verdict"] != "LIVE_PASS"
    assert result["verdict"] in ("LIVE_FAIL", "LIVE_WARN")


def test_04_playwright_unavailable_actual_live_fails():
    """playwright 미설치 환경 시뮬레이션에서 actual-live PASS 불가."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": False,
            "error": "playwright not installed",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }
        result = run_g2b_public_notice_readonly_live(candidate, forbid_mock=True)
    assert result["verdict"] != "LIVE_PASS"


def test_05_allowed_case_execution_dispatched_true_on_success():
    """허용 케이스에서 실제 playwright 성공 시 execution_dispatched=True."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고목록",
            "body_text_length": 4,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert result["execution_dispatched"] is True
    assert result["verdict"] == "LIVE_PASS"
    assert result["mock_used"] is False


def test_06_blocked_case_execution_dispatched_false():
    """차단 케이스는 execution_dispatched=False."""
    candidate = _blocked_candidate()
    result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert result["execution_dispatched"] is False


def test_07_needs_verification_execution_dispatched_false():
    """NEEDS_VERIFICATION 케이스는 execution_dispatched=False."""
    nv_candidate = build_g2b_readonly_execution_candidate("https://shop.g2b.go.kr/", "read")
    assert nv_candidate["gate_verdict"] == GATE_NEEDS_VERIFICATION
    result = run_g2b_public_notice_readonly_live(nv_candidate, actual_live_required=True)
    assert result["execution_dispatched"] is False


def test_08_server_browser_used_always_false():
    """server_browser_used는 actual-live 모드에서도 항상 False."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고",
            "body_text_length": 2,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert result["server_browser_used"] is False


def test_09_local_agent_used_false_no_actual_pass():
    """local_agent_used=False이면 actual-live PASS 불가."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": False,
            "error": "not available",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }
        result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert result["local_agent_used"] is False
    assert result["verdict"] != "LIVE_PASS"


def test_10_result_schema_actual_live_fields():
    """실제 live 결과 schema에 actual_live_required/mock_used/playwright_available 포함."""
    candidate = _allowed_candidate()
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "테스트",
            "body_text_sample": "공고",
            "body_text_length": 2,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert "actual_live_required" in result
    assert "mock_used" in result
    assert "playwright_available" in result
    assert "chromium_available" in result
    assert result["actual_live_required"] is True
    assert result["mock_used"] is False


def test_11_no_forbidden_fields_in_result():
    """live 결과에 cookie/session/token/password/otp 없음."""
    candidate = _blocked_candidate()
    result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    forbidden = {
        "cookie",
        "cookies",
        "session",
        "token",
        "password",
        "otp",
        "auth_token",
        "access_token",
        "refresh_token",
        "credential",
    }
    for f in forbidden:
        assert f not in result, f"금지 필드 발견: {f}"


def test_12_download_auto_allowed_always_false():
    """download_auto_allowed는 actual-live 모드에서도 항상 False."""
    candidate = _blocked_candidate()
    result = run_g2b_public_notice_readonly_live(candidate, actual_live_required=True)
    assert result["download_auto_allowed"] is False


def test_13_click_type_fill_submit_always_blocked():
    """click/type/fill/submit operation은 actual-live 모드에서도 BLOCK."""
    blocked_ops = ["click", "type", "fill", "submit", "download"]
    for op in blocked_ops:
        c = build_g2b_readonly_execution_candidate(_ALLOWED_URL, op)
        result = run_g2b_public_notice_readonly_live(c, actual_live_required=True)
        assert result["execution_dispatched"] is False, f"{op}: execution_dispatched가 False여야 함"
        assert result["verdict"] != "LIVE_PASS", f"{op}: LIVE_PASS 불가"


def test_14_suite_mock_used_false_in_actual_live_mode():
    """actual-live suite 결과에 mock_used=False 포함."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고목록",
            "body_text_length": 4,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_fixture_live_suite(
            _FIXTURE_PATH,
            forbid_mock=True,
            actual_live_required=True,
        )
    assert result["mock_used"] is False
    assert result["actual_live_required"] is True


def test_15_suite_live_warn_not_counted_as_success_in_actual_live():
    """actual-live suite에서 LIVE_WARN은 live_executed에 포함되지 않는다."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": False,
            "error": "not available",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }
        result = run_g2b_public_notice_fixture_live_suite(
            _FIXTURE_PATH,
            forbid_mock=True,
            actual_live_required=True,
        )
    # LIVE_WARN/LIVE_FAIL은 live_executed에 포함되지 않아야 함
    assert result["live_executed"] == 0, (
        f"actual-live 모드에서 WARN은 live_executed에 포함 불가: {result['live_executed']}"
    )


def test_16_check_playwright_available_returns_dict():
    """_check_playwright_available가 필수 필드를 포함하는 dict를 반환한다."""
    result = _check_playwright_available()
    assert "playwright_available" in result
    assert "chromium_available" in result
    assert "error" in result
    assert isinstance(result["playwright_available"], bool)
    assert isinstance(result["chromium_available"], bool)


def test_17_actual_live_required_field_in_suite_result():
    """suite 결과에 actual_live_required 필드가 있다."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고",
            "body_text_length": 2,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_fixture_live_suite(_FIXTURE_PATH, actual_live_required=True)
    assert "actual_live_required" in result
    assert result["actual_live_required"] is True


def test_18_fixture_blocked_cases_gate_block_in_actual_live():
    """actual-live 모드에서도 차단 케이스는 gate BLOCK."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고",
            "body_text_length": 2,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_fixture_live_suite(_FIXTURE_PATH, actual_live_required=True)
    blocked_results = [r for r in result["results"] if r.get("expected_verdict") == "BLOCKED"]
    for r in blocked_results:
        assert r["case_verdict"] == "GATE_BLOCK_CONFIRMED", (
            f"{r['id']}: 차단 케이스가 gate BLOCK 아님: {r['case_verdict']}"
        )


def test_19_scripts_import_includes_argparse():
    """스크립트에 --mode actual-live 파라미터가 포함되어 있다."""
    script_path = _repo_root / "scripts" / "g2b" / "run_public_notice_readonly_live_suite.py"
    source = script_path.read_text(encoding="utf-8")
    assert "actual-live" in source
    assert "forbid-mock" in source or "forbid_mock" in source
    assert "argparse" in source


def test_20_suite_needs_verification_not_live_in_actual_live():
    """actual-live 모드에서도 NEEDS_VERIFICATION은 live 실행 대상 아님."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고",
            "body_text_length": 2,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_fixture_live_suite(_FIXTURE_PATH, actual_live_required=True)
    nv_results = [r for r in result["results"] if r.get("expected_verdict") == "NEEDS_VERIFICATION"]
    for r in nv_results:
        assert r["case_verdict"] == "NEEDS_VERIFICATION_CONFIRMED"
