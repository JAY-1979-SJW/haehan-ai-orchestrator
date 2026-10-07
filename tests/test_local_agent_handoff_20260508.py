"""Local Agent Handoff 테스트"""

from __future__ import annotations

from ai_orchestrator.browser_tool.routing.local_agent_handoff import (
    HANDOFF_LOCAL_BROWSER_CONTINUE,
    HANDOFF_LOCAL_LOGIN_WAIT,
    build_local_agent_handoff,
    validate_handoff_payload,
)


def _task(**kw):
    return {"task_id": "t1", "action": "open", "target_url": "https://www.g2b.go.kr/notice", **kw}


# E-1: 기본 handoff 생성
def test_build_handoff_basic():
    h = build_local_agent_handoff(task=_task())
    assert h["task_id"] == "t1"
    assert h["readonly"] is True


# E-2: forbidden 목록 항상 포함
def test_forbidden_list_always_present():
    h = build_local_agent_handoff(task=_task())
    assert isinstance(h["forbidden"], list)
    assert len(h["forbidden"]) > 0
    assert "cookie_export" in h["forbidden"]


# E-3: cookie_included=False
def test_cookie_not_included():
    h = build_local_agent_handoff(task=_task())
    assert h["cookie_included"] is False


# E-4: session_included=False
def test_session_not_included():
    h = build_local_agent_handoff(task=_task())
    assert h["session_included"] is False


# E-5: password_included=False
def test_password_not_included():
    h = build_local_agent_handoff(task=_task())
    assert h["password_included"] is False


# E-6: otp_included=False
def test_otp_not_included():
    h = build_local_agent_handoff(task=_task())
    assert h["otp_included"] is False


# E-7: cert_info_included=False
def test_cert_info_not_included():
    h = build_local_agent_handoff(task=_task())
    assert h["cert_info_included"] is False


# E-8: sensitive_data_included=False
def test_sensitive_data_not_included():
    h = build_local_agent_handoff(task=_task())
    assert h["sensitive_data_included"] is False


# E-9: 허용 안 된 action → read로 downgrade
def test_disallowed_action_downgrade():
    h = build_local_agent_handoff(task=_task(action="login"))
    # login은 _ALLOWED_HANDOFF_ACTIONS에 없으므로 read로 downgrade
    assert h["action"] == "read"


def test_cookie_export_action_downgrade():
    h = build_local_agent_handoff(task=_task(action="cookie_export"))
    assert h["action"] == "read"


# E-10: URL 민감 파라미터 제거
def test_url_sensitive_param_removed():
    h = build_local_agent_handoff(task=_task(target_url="https://www.g2b.go.kr/notice?token=abc123&page=1"))
    assert "token=abc123" not in h["target_url"]
    assert "page=1" in h["target_url"]


# E-11: validate_handoff_payload 정상 통과
def test_validate_handoff_ok():
    h = build_local_agent_handoff(task=_task())
    violations = validate_handoff_payload(h)
    assert violations == []


# E-12: validate fails if cookie_included=True
def test_validate_fails_cookie_included():
    h = build_local_agent_handoff(task=_task())
    h["cookie_included"] = True
    violations = validate_handoff_payload(h)
    assert any("cookie_included" in v for v in violations)


# E-13: validate fails if forbidden empty
def test_validate_fails_no_forbidden():
    h = build_local_agent_handoff(task=_task())
    h["forbidden"] = []
    violations = validate_handoff_payload(h)
    assert any("forbidden" in v for v in violations)


# E-14: validate fails if readonly=False
def test_validate_fails_readonly_false():
    h = build_local_agent_handoff(task=_task())
    h["readonly"] = False
    violations = validate_handoff_payload(h)
    assert any("readonly" in v for v in violations)


# E-15: handoff_type 기본값
def test_default_handoff_type():
    h = build_local_agent_handoff(task=_task())
    assert h["handoff_type"] == HANDOFF_LOCAL_BROWSER_CONTINUE


# E-16: handoff_type 지정
def test_custom_handoff_type():
    h = build_local_agent_handoff(task=_task(), handoff_type=HANDOFF_LOCAL_LOGIN_WAIT)
    assert h["handoff_type"] == HANDOFF_LOCAL_LOGIN_WAIT
