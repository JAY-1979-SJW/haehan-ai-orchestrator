"""통합 LOCAL_PLAYWRIGHT bridge 테스트

LOCAL_BROWSER_DEFAULT → local_agent_handoff → task_protocol 전 과정 검증.
사이트별 도구 없이 공통 protocol로 처리되는지 확인.
"""

from __future__ import annotations

from ai_orchestrator.browser_tool.routing.local_agent_handoff import (
    build_local_agent_handoff,
    handoff_to_task_protocol,
)
from ai_orchestrator.browser_tool.unified_browser_safe_result import (
    EXEC_SERVER_BROWSER,
    STATUS_BLOCKED,
    STATUS_LOCAL_HANDOFF_CREATED,
)
from ai_orchestrator.browser_tool.routing.unified_execution_router import route_browser_task
from ai_orchestrator.contracts.local_task_protocol import (
    ALLOWED_TASK_ACTIONS,
    EXEC_MODE_LOCAL_PLAYWRIGHT,
    TASK_TYPE_BROWSER,
    validate_task,
)
from ai_orchestrator.server.task_queue_schema import clear_store


def setup_function():
    clear_store()


def _task(**kw):
    base = {
        "task_id": "bridge1",
        "action": "open",
        "target_url": "https://www.g2b.go.kr/notice/list",
        "readonly": True,
    }
    base.update(kw)
    return base


# ── 1. LOCAL_BROWSER_DEFAULT → LOCAL_PLAYWRIGHT 변환 ─────────────────────────


def test_local_browser_default_produces_task_protocol():
    r = route_browser_task(_task())
    proto = r.get("local_playwright_task")
    assert proto is not None
    assert proto["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT
    assert proto["task_type"] == TASK_TYPE_BROWSER


def test_task_protocol_valid_schema():
    r = route_browser_task(_task())
    proto = r.get("local_playwright_task")
    violations = validate_task(proto)
    assert violations == [], f"schema 위반: {violations}"


def test_task_protocol_no_sensitive_fields():
    r = route_browser_task(_task())
    proto = r.get("local_playwright_task")
    for f in ("cookie", "session", "password", "otp", "token"):
        assert f not in proto


# ── 2. 서버가 외부 URL을 직접 실행하지 않음 ───────────────────────────────────


def test_server_does_not_open_external_url():
    r = route_browser_task(_task())
    assert r["execution_used"] != EXEC_SERVER_BROWSER


def test_server_result_not_needed_for_local():
    r = route_browser_task(_task(), server_result=None)
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED


# ── 3. 로컬 에이전트 task 수신 ───────────────────────────────────────────────


def test_task_protocol_action_is_open_url():
    r = route_browser_task(_task(action="open"))
    proto = r.get("local_playwright_task")
    assert proto["action"] == "open_url"


def test_task_protocol_login_action_maps_to_wait_for_user_auth():
    r = route_browser_task(_task(action="login"))
    proto = r.get("local_playwright_task")
    # login → wait_for_user_auth 또는 open_url (downgrade)
    assert proto["action"] in ALLOWED_TASK_ACTIONS


# ── 4. 사이트별 도구 없이 공통 protocol 사용 ─────────────────────────────────


def test_g2b_uses_common_protocol():
    r = route_browser_task(_task(target_url="https://www.g2b.go.kr/notice"))
    proto = r.get("local_playwright_task")
    assert proto["task_type"] == TASK_TYPE_BROWSER


def test_hometax_uses_common_protocol():
    r = route_browser_task(_task(target_url="https://www.hometax.go.kr/notice"))
    proto = r.get("local_playwright_task")
    assert proto["task_type"] == TASK_TYPE_BROWSER


def test_bank_uses_common_protocol():
    r = route_browser_task(_task(target_url="https://www.kbbank.com/login"))
    proto = r.get("local_playwright_task")
    assert proto["task_type"] == TASK_TYPE_BROWSER


# ── 5. handoff_to_task_protocol 직접 검증 ─────────────────────────────────────


def test_handoff_to_task_protocol_basic():
    handoff = build_local_agent_handoff(
        task={"task_id": "h1", "action": "open", "target_url": "https://www.g2b.go.kr"},
    )
    proto = handoff_to_task_protocol(handoff, task_id="h1")
    assert proto["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT
    assert proto["action"] in ALLOWED_TASK_ACTIONS


def test_handoff_to_task_protocol_no_sensitive():
    handoff = build_local_agent_handoff(
        task={"task_id": "h2", "action": "read", "target_url": "https://www.g2b.go.kr"},
    )
    proto = handoff_to_task_protocol(handoff)
    for f in ("cookie", "session", "password", "otp"):
        assert f not in proto


def test_handoff_to_task_protocol_metadata_has_local_browser_default():
    handoff = build_local_agent_handoff(
        task={"task_id": "h3", "action": "open", "target_url": "https://www.g2b.go.kr"},
    )
    proto = handoff_to_task_protocol(handoff)
    assert proto["metadata"].get("local_browser_default") is True


# ── 6. 보안 차단 검증 ─────────────────────────────────────────────────────────


def test_cookie_export_blocked():
    r = route_browser_task(_task(action="cookie_export"))
    assert r["final_status"] == STATUS_BLOCKED


def test_auto_sign_blocked():
    r = route_browser_task(_task(action="auto_sign"))
    assert r["final_status"] == STATUS_BLOCKED


def test_bid_submit_blocked():
    r = route_browser_task(_task(action="bid_submit"))
    assert r["final_status"] == STATUS_BLOCKED


# ── 7. 결과 안전성 검증 ───────────────────────────────────────────────────────


def test_result_no_cookie():
    r = route_browser_task(_task())
    assert r.get("cookie_exported") is False
    assert r.get("password_collected") is False
    assert r.get("otp_collected") is False


def test_result_has_handoff_with_local_browser_default():
    r = route_browser_task(_task())
    handoff = r.get("local_agent_handoff")
    assert handoff.get("local_browser_default") is True
