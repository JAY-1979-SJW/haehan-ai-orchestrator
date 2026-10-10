"""
G2B 공개 공고 Read-Only Full Live Execution 테스트

테스트 범위:
- execution gate (candidate 생성, BLOCK 판정)
- local live runner (schema 검증, 정책 준수)
- fixture 전체 케이스 gate 판정
- live suite 스크립트 import 가능 확인
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (  # noqa: E402
    GATE_BLOCKED,
    GATE_NEEDS_VERIFICATION,
    GATE_READONLY_EXECUTION_CANDIDATE,
    build_g2b_readonly_execution_candidate,
    evaluate_g2b_public_notice_execution_gate,
    validate_g2b_execution_gate_result,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (  # noqa: E402
    BODY_TEXT_MAX_LEN,
    run_g2b_public_notice_fixture_live_suite,
    run_g2b_public_notice_readonly_live,
    validate_g2b_public_notice_live_result,
)

_FIXTURE_PATH = str(_repo_root / "tests" / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json")


def _load_fixture():
    # _FIXTURE_PATH is kept as str below (passed as-is to
    # run_g2b_public_notice_fixture_live_suite elsewhere in this file);
    # only this local read is converted to pathlib.
    with Path(_FIXTURE_PATH).open(encoding="utf-8") as f:
        return json.load(f)


# ── 허용 케이스 candidate 생성 ─────────────────────────────────────────────────


def test_01_read_candidate_gate_pass():
    """read operation에 대해 execution gate가 READONLY_EXECUTION_CANDIDATE를 반환한다."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert c["gate_verdict"] == GATE_READONLY_EXECUTION_CANDIDATE
    assert c["execution_allowed"] is True


def test_02_open_url_candidate_gate_pass():
    """open_url operation에 대해 gate가 통과된다."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "open_url")
    assert c["gate_verdict"] == GATE_READONLY_EXECUTION_CANDIDATE
    assert c["execution_allowed"] is True


def test_03_navigate_candidate_gate_pass():
    """navigate operation에 대해 gate가 통과된다."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do", "navigate")
    assert c["gate_verdict"] == GATE_READONLY_EXECUTION_CANDIDATE
    assert c["execution_allowed"] is True


def test_04_candidate_schema_required_fields():
    """candidate dict에 필수 필드가 모두 있다."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    for field in [
        "input_url",
        "canonical_url",
        "operation",
        "gate_verdict",
        "execution_allowed",
        "execution_dispatched",
        "server_browser_used",
        "download_auto_allowed",
        "local_agent_required",
        "dryrun_result",
    ]:
        assert field in c, f"필드 누락: {field}"


def test_05_candidate_execution_dispatched_always_false():
    """gate 단계에서 execution_dispatched는 항상 False."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert c["execution_dispatched"] is False


def test_06_candidate_server_browser_used_always_false():
    """server_browser_used는 항상 False."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert c["server_browser_used"] is False


def test_07_candidate_download_auto_allowed_always_false():
    """download_auto_allowed는 항상 False."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert c["download_auto_allowed"] is False


def test_08_candidate_local_agent_required_always_true():
    """local_agent_required는 항상 True."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert c["local_agent_required"] is True


# ── 차단 케이스 ────────────────────────────────────────────────────────────────


def test_09_click_operation_blocked():
    """click operation은 gate에서 BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "click")
    assert c["execution_allowed"] is False
    assert c["gate_verdict"] == GATE_BLOCKED


def test_10_type_operation_blocked():
    """type operation은 gate에서 BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "type")
    assert c["execution_allowed"] is False


def test_11_fill_operation_blocked():
    """fill operation은 gate에서 BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "fill")
    assert c["execution_allowed"] is False


def test_12_submit_operation_blocked():
    """submit operation은 gate에서 BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "submit")
    assert c["execution_allowed"] is False


def test_13_download_operation_blocked():
    """download operation은 gate에서 BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/file/download.do", "download")
    assert c["execution_allowed"] is False


def test_14_login_path_blocked():
    """login 경로는 gate BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate")
    assert c["execution_allowed"] is False


def test_15_cert_path_blocked():
    """cert 경로는 gate BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/cert/userCert.do", "navigate")
    assert c["execution_allowed"] is False


def test_16_bid_path_blocked():
    """bid(ptb05) 경로는 gate BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb05001p.do", "navigate")
    assert c["execution_allowed"] is False


def test_17_contract_path_blocked():
    """contract 경로는 gate BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/ct/menu/ntn02/cta01/ctb01001l.do", "navigate")
    assert c["execution_allowed"] is False


def test_18_payment_path_blocked():
    """payment 경로는 gate BLOCKED."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pay/checkout.do", "navigate")
    assert c["execution_allowed"] is False


def test_19_shop_subdomain_needs_verification():
    """shop.g2b.go.kr은 live 실행 대상 아님 (NEEDS_VERIFICATION)."""
    c = build_g2b_readonly_execution_candidate("https://shop.g2b.go.kr/", "read")
    assert c["execution_allowed"] is False
    assert c["gate_verdict"] == GATE_NEEDS_VERIFICATION


def test_20_unknown_subdomain_needs_verification():
    """api.g2b.go.kr 등 미확인 서브도메인은 live 실행 제외."""
    c = build_g2b_readonly_execution_candidate("https://api.g2b.go.kr/", "read")
    assert c["execution_allowed"] is False


# ── live runner schema/정책 ────────────────────────────────────────────────────


def test_21_live_runner_block_if_gate_not_passed():
    """gate 통과 안 한 candidate는 live runner가 실행하지 않는다."""
    blocked_candidate = build_g2b_readonly_execution_candidate(
        "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"
    )
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
    assert result["execution_dispatched"] is False
    assert result["live_browser_worker_called"] is False
    assert result["verdict"] in ("LIVE_BLOCK", "LIVE_FAIL")


def test_22_live_runner_server_browser_used_always_false():
    """live runner 결과에서 server_browser_used는 항상 False."""
    blocked_candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pay/checkout.do", "navigate")
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
    assert result["server_browser_used"] is False


def test_23_live_runner_download_auto_allowed_always_false():
    """live runner 결과에서 download_auto_allowed는 항상 False."""
    blocked_candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/file/download.do", "download")
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
    assert result["download_auto_allowed"] is False


def test_24_live_runner_local_agent_required_always_true():
    """live runner 결과에서 local_agent_required는 항상 True."""
    blocked_candidate = build_g2b_readonly_execution_candidate(
        "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "submit"
    )
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
    assert result["local_agent_required"] is True


def test_25_live_result_required_fields():
    """live runner 결과에 필수 필드가 모두 있다."""
    blocked_candidate = build_g2b_readonly_execution_candidate(
        "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"
    )
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
    errors = validate_g2b_public_notice_live_result(result)
    # 필수 필드 누락만 확인 (policy 오류 제외)
    field_errors = [e for e in errors if "필수 필드 누락" in e]
    assert not field_errors, f"필수 필드 누락: {field_errors}"


def test_26_live_result_no_forbidden_fields():
    """live runner 결과에 cookie/token/session/password/otp 필드가 없다."""
    blocked_candidate = build_g2b_readonly_execution_candidate(
        "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"
    )
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
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
    for field in forbidden:
        assert field not in result, f"금지 필드 발견: {field}"


def test_27_body_text_sample_max_length():
    """body_text_sample 최대 길이 제한이 작동한다."""
    long_text = "x" * 2000
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import _truncate_body

    result = _truncate_body(long_text)
    assert len(result) <= BODY_TEXT_MAX_LEN


def test_28_live_fail_if_local_agent_false_and_verdict_pass():
    """local_agent_used=False이면서 LIVE_PASS인 결과는 validate에서 오류."""
    fake_result = {
        "input_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "canonical_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "final_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "operation": "read",
        "gate_verdict": GATE_READONLY_EXECUTION_CANDIDATE,
        "execution_allowed": True,
        "execution_dispatched": True,
        "live_browser_worker_called": True,
        "local_agent_required": True,
        "local_agent_used": False,  # False이면서 PASS → 오류
        "server_browser_used": False,
        "readonly_allowed": True,
        "download_auto_allowed": False,
        "title": "제목",
        "body_text_sample": "본문",
        "body_text_length": 2,
        "blocked_reason": "",
        "error": "",
        "verdict": "LIVE_PASS",
    }
    errors = validate_g2b_public_notice_live_result(fake_result)
    assert any("local_agent_used=False" in e for e in errors)


def test_29_live_fail_if_server_browser_used_true():
    """server_browser_used=True 결과는 validate에서 오류."""
    fake_result = {
        "input_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "canonical_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "final_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "operation": "read",
        "gate_verdict": GATE_READONLY_EXECUTION_CANDIDATE,
        "execution_allowed": True,
        "execution_dispatched": True,
        "live_browser_worker_called": True,
        "local_agent_required": True,
        "local_agent_used": True,
        "server_browser_used": True,  # FAIL 조건
        "readonly_allowed": True,
        "download_auto_allowed": False,
        "title": "",
        "body_text_sample": "",
        "body_text_length": 0,
        "blocked_reason": "",
        "error": "",
        "verdict": "LIVE_PASS",
    }
    errors = validate_g2b_public_notice_live_result(fake_result)
    assert any("server_browser_used" in e for e in errors)


def test_30_live_fail_if_download_auto_allowed_true():
    """download_auto_allowed=True 결과는 validate에서 오류."""
    fake_result = {
        "input_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "canonical_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "final_url": "",
        "operation": "read",
        "gate_verdict": GATE_BLOCKED,
        "execution_allowed": False,
        "execution_dispatched": False,
        "live_browser_worker_called": False,
        "local_agent_required": True,
        "local_agent_used": False,
        "server_browser_used": False,
        "readonly_allowed": False,
        "download_auto_allowed": True,  # FAIL 조건
        "title": "",
        "body_text_sample": "",
        "body_text_length": 0,
        "blocked_reason": "",
        "error": "",
        "verdict": "LIVE_BLOCK",
    }
    errors = validate_g2b_public_notice_live_result(fake_result)
    assert any("download_auto_allowed" in e for e in errors)


# ── fixture 전체 gate 판정 ─────────────────────────────────────────────────────


def test_31_fixture_allowed_cases_gate_pass():
    """fixture ALLOWED 케이스 전체가 gate를 통과한다."""
    fixture = _load_fixture()
    allowed = [c for c in fixture["cases"] if c["expected"].get("verdict") == "ALLOWED"]
    for case in allowed:
        c = build_g2b_readonly_execution_candidate(case["url"], case["operation"])
        assert c["execution_allowed"] is True, (
            f"{case['id']} ({case['label']}): gate BLOCKED 예상치 못함. "
            f"gate_verdict={c['gate_verdict']}, blocked_reason={c['blocked_reason']}"
        )


def test_32_fixture_blocked_cases_gate_block():
    """fixture BLOCKED 케이스 전체가 gate에서 차단된다."""
    fixture = _load_fixture()
    blocked = [c for c in fixture["cases"] if c["expected"].get("verdict") == "BLOCKED"]
    for case in blocked:
        c = build_g2b_readonly_execution_candidate(case["url"], case["operation"])
        assert c["execution_allowed"] is False, f"{case['id']} ({case['label']}): gate 통과 예상치 못함."


def test_33_fixture_needs_verification_cases_not_live():
    """fixture NEEDS_VERIFICATION 케이스는 live 실행 대상 아님."""
    fixture = _load_fixture()
    nv_cases = [c for c in fixture["cases"] if c["expected"].get("verdict") == "NEEDS_VERIFICATION"]
    for case in nv_cases:
        c = build_g2b_readonly_execution_candidate(case["url"], case["operation"])
        assert c["execution_allowed"] is False, f"{case['id']}: NEEDS_VERIFICATION는 live 실행 불가"
        assert c["gate_verdict"] == GATE_NEEDS_VERIFICATION, f"{case['id']}: gate_verdict 불일치"


def test_34_fixture_execution_dispatched_only_for_allowed():
    """fixture BLOCKED/NEEDS_VERIFICATION 케이스는 execution_dispatched=False."""
    fixture = _load_fixture()
    non_allowed = [c for c in fixture["cases"] if c["expected"].get("verdict") in ("BLOCKED", "NEEDS_VERIFICATION")]
    for case in non_allowed:
        c = build_g2b_readonly_execution_candidate(case["url"], case["operation"])
        assert c["execution_dispatched"] is False


def test_35_gate_validate_allowed_candidate():
    """gate 유효성 검사 함수가 허용 candidate에서 오류 없음."""
    c = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    errors = validate_g2b_execution_gate_result(c)
    assert not errors, f"예상치 못한 gate 오류: {errors}"


def test_36_gate_validate_blocked_candidate():
    """gate 유효성 검사 함수가 차단 candidate에서도 오류 없음 (schema 준수)."""
    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pay/checkout.do", "navigate")
    errors = validate_g2b_execution_gate_result(c)
    assert not errors, f"예상치 못한 gate 오류: {errors}"


def test_37_live_runner_blocked_execution_dispatched_false():
    """차단 케이스는 live runner에서 execution_dispatched=False."""
    blocked_candidate = build_g2b_readonly_execution_candidate(
        "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"
    )
    result = run_g2b_public_notice_readonly_live(blocked_candidate)
    assert result["execution_dispatched"] is False


def test_38_live_runner_server_env_blocked():
    """IS_SERVER_ENV=true이면 live runner가 FAIL을 반환한다."""
    import os

    allowed_candidate = build_g2b_readonly_execution_candidate(
        "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read"
    )
    with patch.dict(os.environ, {"IS_SERVER_ENV": "true"}):
        result = run_g2b_public_notice_readonly_live(allowed_candidate)
    assert result["verdict"] == "LIVE_FAIL"
    assert "SERVER_ENV" in result["blocked_reason"]


def test_39_live_result_body_text_sample_max_length_enforce():
    """live 결과 validate에서 body_text_sample이 최대 길이를 초과하면 오류."""
    fake_result = {
        "input_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "canonical_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        "final_url": "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
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
        "title": "제목",
        "body_text_sample": "x" * (BODY_TEXT_MAX_LEN + 1),  # 초과
        "body_text_length": BODY_TEXT_MAX_LEN + 1,
        "blocked_reason": "",
        "error": "",
        "verdict": "LIVE_PASS",
    }
    errors = validate_g2b_public_notice_live_result(fake_result)
    assert any("body_text_sample" in e for e in errors)


def test_40_scripts_import():
    """scripts/g2b/run_public_notice_readonly_live_suite.py import 가능."""
    import importlib.util

    script_path = _repo_root / "scripts" / "g2b" / "run_public_notice_readonly_live_suite.py"
    assert script_path.exists(), f"스크립트 파일 없음: {script_path}"
    spec = importlib.util.spec_from_file_location("run_public_notice_readonly_live_suite", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main"), "main 함수 없음"


def test_41_fixture_live_suite_schema():
    """fixture live suite 결과 schema 확인 (mock playwright)."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터 공고",
            "body_text_sample": "공고 목록",
            "body_text_length": 5,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_fixture_live_suite(_FIXTURE_PATH)

    assert "total_cases" in result
    assert "allowed_cases" in result
    assert "blocked_cases" in result
    assert "live_executed" in result
    assert "gate_blocked_confirmed" in result
    assert "results" in result
    assert "summary" in result
    assert result["total_cases"] > 0


def test_42_fixture_live_suite_blocked_not_live_executed():
    """fixture BLOCKED 케이스는 live runner를 호출하지 않는다 (mock으로 확인)."""
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터 공고",
            "body_text_sample": "공고 목록",
            "body_text_length": 5,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_fixture_live_suite(_FIXTURE_PATH)

    # BLOCKED 케이스 수만큼 gate_blocked_confirmed 확인
    assert result["gate_blocked_confirmed"] == result["blocked_cases"]


def test_43_gate_evaluate_directly_blocked_adapter_result():
    """evaluate_g2b_public_notice_execution_gate가 BLOCKED adapter 결과를 차단한다."""
    blocked_dryrun = {
        "input_url": "https://www.g2b.go.kr/pay/checkout.do",
        "canonical_url": "https://www.g2b.go.kr/pay/checkout.do",
        "operation": "navigate",
        "adapter_decision": "G2B_DRYRUN_BLOCKED",
        "policy_verdict": "BLOCKED",
        "blocked_reason": "PATH_BLOCKED",
    }
    result = evaluate_g2b_public_notice_execution_gate(blocked_dryrun)
    assert result["execution_allowed"] is False
    assert result["gate_verdict"] == GATE_BLOCKED


def test_44_gate_evaluate_needs_verification_result():
    """evaluate_g2b_public_notice_execution_gate가 NEEDS_VERIFICATION 결과를 처리한다."""
    nv_dryrun = {
        "input_url": "https://shop.g2b.go.kr/",
        "canonical_url": "https://shop.g2b.go.kr/",
        "operation": "read",
        "adapter_decision": "G2B_DRYRUN_NEEDS_VERIFICATION",
        "policy_verdict": "NEEDS_VERIFICATION",
        "blocked_reason": "NEEDS_URL_VERIFICATION",
    }
    result = evaluate_g2b_public_notice_execution_gate(nv_dryrun)
    assert result["gate_verdict"] == GATE_NEEDS_VERIFICATION
    assert result["execution_allowed"] is False
    assert result["requires_url_verification"] is True


def test_45_live_runner_no_click_function():
    """live runner 모듈에 click 실행 함수가 없다."""
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner as m

    for name in dir(m):
        fn = getattr(m, name)
        if callable(fn) and "click" in name.lower() and "block" not in name.lower():
            pytest.fail(f"click 실행 함수 발견: {name}")


def test_46_live_runner_no_submit_function():
    """live runner 모듈에 submit 실행 함수가 없다."""
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner as m

    for name in dir(m):
        fn = getattr(m, name)
        if callable(fn) and "submit" in name.lower() and "block" not in name.lower():
            pytest.fail(f"submit 실행 함수 발견: {name}")


def test_47_live_runner_no_download_function():
    """live runner 모듈에 download 실행 함수가 없다."""
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner as m

    for name in dir(m):
        if "download" in name.lower() and "block" not in name.lower() and "allowed" not in name.lower():
            pytest.fail(f"download 관련 이름 발견: {name}")


def test_48_live_runner_with_mock_playwright_pass():
    """mock playwright로 허용 케이스 live 실행 PASS 시나리오."""
    candidate = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "나라장터",
            "body_text_sample": "공고목록",
            "body_text_length": 5,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
        }
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["verdict"] == "LIVE_PASS"
    assert result["local_agent_used"] is True
    assert result["server_browser_used"] is False
    assert result["execution_dispatched"] is True
    assert result["download_auto_allowed"] is False


def test_49_live_runner_final_url_escape_fail():
    """final_url이 허용 도메인 밖으로 이동하면 LIVE_FAIL."""
    candidate = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": True,
            "error": "",
            "title": "외부 사이트",
            "body_text_sample": "외부",
            "body_text_length": 2,
            "final_url": "https://malicious.example.com/",  # 허용 도메인 밖
        }
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["verdict"] == "LIVE_FAIL"
    assert "FINAL_URL_DOMAIN_ESCAPED" in result["blocked_reason"]


def test_50_live_runner_local_agent_unavailable_warn():
    """playwright 미설치 시 LIVE_WARN 반환."""
    candidate = build_g2b_readonly_execution_candidate("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    with patch("ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read") as mock_pw:
        mock_pw.return_value = {
            "local_agent_available": False,
            "error": "playwright not installed",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["verdict"] == "LIVE_WARN"
    assert result["local_agent_used"] is False
    assert result["execution_dispatched"] is False
