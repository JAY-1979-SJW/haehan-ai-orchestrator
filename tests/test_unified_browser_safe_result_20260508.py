"""통합 브라우저 안전 결과 스키마 테스트"""
from __future__ import annotations
import pytest
from ai_orchestrator.browser_tool.unified_browser_safe_result import (
    build_safe_result, validate_safe_result,
    STATUS_SUCCESS, STATUS_BLOCKED, STATUS_LOCAL_HANDOFF_CREATED,
    STATUS_USER_ACTION_REQUIRED, STATUS_FAILED,
    EXEC_SERVER_BROWSER, EXEC_LOCAL_AGENT, EXEC_USER_DIRECT, EXEC_BLOCKED,
)


# F-1: 기본 안전 결과 생성
def test_build_safe_result_basic():
    r = build_safe_result(
        task_id="t1",
        ok=True,
        execution_used=EXEC_SERVER_BROWSER,
        final_status=STATUS_SUCCESS,
        message_ko="서버 성공",
    )
    assert r["task_id"] == "t1"
    assert r["ok"] is True
    assert r["final_status"] == STATUS_SUCCESS

# F-2: cookie 값 없음 (고정 필드)
def test_cookie_exported_false():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    assert r["cookie_exported"] is False

# F-3: password 수집 없음
def test_password_collected_false():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    assert r["password_collected"] is False

# F-4: session 수출 없음
def test_session_exported_false():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    assert r["session_exported"] is False

# F-5: otp 수집 없음
def test_otp_collected_false():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    assert r["otp_collected"] is False

# F-6: 민감 데이터 수집 없음
def test_sensitive_data_collected_false():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    assert r["sensitive_data_collected"] is False

# F-7: extra에서 민감 필드 제거
def test_extra_sensitive_fields_removed():
    r = build_safe_result(
        "t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS,
        extra={"cookie": "sess=abc", "token": "xyz", "safe_field": "ok"},
    )
    assert "cookie" not in r or r.get("cookie") in (None, False, "", [], {})
    assert "token" not in r or r.get("token") in (None, False, "", [], {})
    assert r.get("safe_field") == "ok"

# F-8: validate_safe_result 정상 통과
def test_validate_safe_result_ok():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    violations = validate_safe_result(r)
    assert violations == []

# F-9: validate 실패 - cookie 값 있음
def test_validate_fails_cookie_present():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    r["cookie"] = "session=abc"
    violations = validate_safe_result(r)
    assert any("cookie" in v for v in violations)

# F-10: validate 실패 - 고정 필드 변조
def test_validate_fails_fixed_field_tampered():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    r["password_collected"] = True
    violations = validate_safe_result(r)
    assert any("password_collected" in v for v in violations)

# F-11: security_signals 포함
def test_security_signals_included():
    r = build_safe_result(
        "t1", False, EXEC_LOCAL_AGENT, STATUS_LOCAL_HANDOFF_CREATED,
        security_signals=["login_required"],
    )
    assert "login_required" in r["security_signals"]

# F-12: security_signals 없으면 빈 리스트
def test_security_signals_default_empty():
    r = build_safe_result("t1", True, EXEC_SERVER_BROWSER, STATUS_SUCCESS)
    assert r["security_signals"] == []

# F-13: BLOCKED status
def test_blocked_status():
    r = build_safe_result("t1", False, EXEC_BLOCKED, STATUS_BLOCKED, message_ko="차단됨")
    assert r["final_status"] == STATUS_BLOCKED
    assert r["ok"] is False

# F-14: LOCAL_HANDOFF status
def test_local_handoff_status():
    r = build_safe_result("t1", True, EXEC_LOCAL_AGENT, STATUS_LOCAL_HANDOFF_CREATED)
    assert r["execution_used"] == EXEC_LOCAL_AGENT
