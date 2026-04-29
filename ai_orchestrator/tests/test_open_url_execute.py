"""Stage 13G-5: open_url_execute 승인형 actual 실행 테스트.

검증 범위:
  1. open_url dry_run 기존 경로 회귀
  2. dry_run=false 직접 open_url 거부 (ACTUAL_EXECUTION_NOT_ENABLED)
  3. ACTION_RISK["open_url_execute"] == "high"
  4. open_url_execute 가 _SERVER_AUTO_COMPLETE 에 미포함
  5. open_url_execute 가 _APPROVAL_REQUIRED_ACTIONS 에 포함 (ws_client)
  6. open_url_execute 승인 없이 action handler 호출 시 OPEN_URL_NOT_APPROVED
  7. payload approved=true 조작만으로는 실행 불가 (_approved 키만 신뢰)
  8. _approved=True 주입 시 webbrowser.open 호출
  9. _approved=False/미포함 시 webbrowser.open 미호출
  10. 민감정보 payload 거부
  11. URL query string result_data 저장 시 제거
  12. waiting_approval 상태 task 는 list_pending_for_agent() 에 미포함
  13. mark_approved 후 queued 전환 및 list_pending_for_agent() 에 포함
  14. approval token attach/validate
  15. result_data 에 approval_id/execution_task_id/would_open_browser 저장
  16. router endpoint — waiting_approval 생성 + token attach
  17. open_url_execute ACTION_RISK 테스트 독립 확인
"""
from __future__ import annotations

import json
import uuid
from unittest import mock

import pytest

# ── 공통 픽스처 ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_registry():
    import ai_orchestrator.local_agent_registry as reg
    reg.clear()
    yield
    reg.clear()


def _make_admin_user():
    return {"sub": "admin-test", "actor": "admin-test", "role": "admin"}


def _make_test_client(user: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ai_orchestrator.local_agent_router import local_agent_router
    from ai_orchestrator.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def _register_agent(client) -> dict:
    resp = client.post("/api/v1/local-agents/register", json={
        "host": "test-pc", "os_name": "Windows 11", "version": "0.1.0",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# ════════════════════════════════════════════════════════════════════════════
# 1. open_url dry_run 기존 경로 회귀
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_dry_run_regression():
    """기존 dry_run=true 경로는 변경 없이 동작해야 한다."""
    from local_agent.actions import action_open_url
    r = action_open_url({"url": "https://example.com", "dry_run": True})
    assert r.success
    assert r.summary == "open_url_dry_run_ok"
    assert r.data["dry_run"] is True
    assert r.data["would_open_browser"] is False


# ════════════════════════════════════════════════════════════════════════════
# 2. dry_run=false 직접 open_url 거부
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_dry_run_false_still_rejected():
    from local_agent.actions import action_open_url
    r = action_open_url({"url": "https://example.com", "dry_run": False})
    assert not r.success
    assert r.error_code == "ACTUAL_EXECUTION_NOT_ENABLED"


# ════════════════════════════════════════════════════════════════════════════
# 3. ACTION_RISK["open_url_execute"] == "high"
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_action_risk_high():
    from ai_orchestrator.local_agent_registry import ACTION_RISK
    assert ACTION_RISK["open_url_execute"] == "high"


# ════════════════════════════════════════════════════════════════════════════
# 4. open_url_execute 가 _SERVER_AUTO_COMPLETE 에 미포함
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_not_in_server_auto_complete():
    from ai_orchestrator.local_agent_registry import _SERVER_AUTO_COMPLETE
    assert "open_url_execute" not in _SERVER_AUTO_COMPLETE


# ════════════════════════════════════════════════════════════════════════════
# 5. _APPROVAL_REQUIRED_ACTIONS (ws_client) 에 포함
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_in_approval_required_actions():
    from local_agent.websocket_client import _APPROVAL_REQUIRED_ACTIONS
    assert "open_url_execute" in _APPROVAL_REQUIRED_ACTIONS


# ════════════════════════════════════════════════════════════════════════════
# 6. 승인 없이 action handler 호출 시 OPEN_URL_NOT_APPROVED
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_no_approved_flag_rejected():
    from local_agent.actions import action_open_url_execute
    r = action_open_url_execute({"url": "https://example.com"})
    assert not r.success
    assert r.error_code == "OPEN_URL_NOT_APPROVED"


def test_open_url_execute_approved_false_rejected():
    from local_agent.actions import action_open_url_execute
    r = action_open_url_execute({"url": "https://example.com", "_approved": False})
    assert not r.success
    assert r.error_code == "OPEN_URL_NOT_APPROVED"


# ════════════════════════════════════════════════════════════════════════════
# 7. payload approved=true 조작만으로는 실행 불가
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_user_approved_true_not_trusted():
    """사용자가 params 에 approved=true 를 넣어도 _approved 키만 신뢰한다."""
    from local_agent.actions import action_open_url_execute
    # approved (without underscore) 는 내부 인증 키가 아님
    with mock.patch("local_agent.actions.webbrowser.open") as mock_open:
        r = action_open_url_execute({"url": "https://example.com", "approved": True})
    assert not r.success
    assert r.error_code == "OPEN_URL_NOT_APPROVED"
    mock_open.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# 8. _approved=True 주입 시 webbrowser.open 호출
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_approved_calls_webbrowser_open():
    from local_agent.actions import action_open_url_execute
    with mock.patch("local_agent.actions.webbrowser.open") as mock_open:
        r = action_open_url_execute({
            "url": "https://example.com",
            "_approved": True,
        })
    assert r.success
    assert r.summary == "open_url_execute_ok"
    mock_open.assert_called_once_with("https://example.com")


# ════════════════════════════════════════════════════════════════════════════
# 9. _approved=False/미포함 시 webbrowser.open 미호출
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_no_approved_no_webbrowser_call():
    from local_agent.actions import action_open_url_execute
    with mock.patch("local_agent.actions.webbrowser.open") as mock_open:
        r = action_open_url_execute({"url": "https://example.com"})
    assert not r.success
    mock_open.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# 10. 민감정보 payload 거부
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sensitive_key", [
    "password", "token", "cookie", "authorization", "session", "api_key",
])
def test_open_url_execute_sensitive_key_rejected(sensitive_key):
    from local_agent.actions import action_open_url_execute
    with mock.patch("local_agent.actions.webbrowser.open") as mock_open:
        r = action_open_url_execute({
            "url": "https://example.com",
            "_approved": True,
            sensitive_key: "secret_value",
        })
    assert not r.success
    assert r.error_code == "SENSITIVE_DATA_DETECTED"
    mock_open.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# 11. URL query string result_data 저장 시 제거
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_query_string_stripped_from_result():
    from local_agent.actions import action_open_url_execute
    with mock.patch("local_agent.actions.webbrowser.open"):
        r = action_open_url_execute({
            "url": "https://example.com/path?token=abc&foo=bar",
            "_approved": True,
        })
    assert r.success
    assert "token=abc" not in r.data.get("normalized_url", "")
    assert "?" not in r.data.get("normalized_url", "")
    assert r.data["normalized_url"] == "https://example.com/path"


# ════════════════════════════════════════════════════════════════════════════
# 12. waiting_approval 상태 task 는 list_pending_for_agent() 에 미포함
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_waiting_approval_not_delivered():
    import ai_orchestrator.local_agent_registry as reg

    result = reg.register_agent(
        host="pc-test", os_name="Windows 11", version="0.1.0", requested_by="admin",
    )
    agent_id = result.agent.agent_id

    task = reg.enqueue_task(
        agent_id=agent_id,
        action="open_url_execute",
        params={"url": "https://example.com"},
        requested_by="admin",
    )
    assert task.status == "waiting_approval"

    pending = reg.list_pending_for_agent(agent_id)
    task_ids = [t.task_id for t in pending]
    assert task.task_id not in task_ids, "waiting_approval task 가 pending 에 포함됨"


# ════════════════════════════════════════════════════════════════════════════
# 13. mark_approved 후 queued 전환 및 list_pending_for_agent() 에 포함
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_mark_approved_queued_and_pending():
    import ai_orchestrator.local_agent_registry as reg

    result = reg.register_agent(
        host="pc-test2", os_name="Windows 11", version="0.1.0", requested_by="admin",
    )
    agent_id = result.agent.agent_id

    task = reg.enqueue_task(
        agent_id=agent_id,
        action="open_url_execute",
        params={"url": "https://example.com"},
        requested_by="admin",
    )
    assert task.status == "waiting_approval"

    updated = reg.mark_approved(task.task_id, actor="admin")
    assert updated is not None
    assert updated.status == "queued"

    pending = reg.list_pending_for_agent(agent_id)
    task_ids = [t.task_id for t in pending]
    assert task.task_id in task_ids, "mark_approved 후 task 가 pending 에 없음"


# ════════════════════════════════════════════════════════════════════════════
# 14. approval token attach/validate
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_attach_and_validate_token():
    import ai_orchestrator.local_agent_registry as reg
    from ai_orchestrator.approval import issue_token_for_dev_reg, validate_token, approve_token

    result = reg.register_agent(
        host="pc-test3", os_name="Windows 11", version="0.1.0", requested_by="admin",
    )
    agent_id = result.agent.agent_id

    task = reg.enqueue_task(
        agent_id=agent_id,
        action="open_url_execute",
        params={"url": "https://example.com"},
        requested_by="admin",
    )

    token = issue_token_for_dev_reg(
        task_id=task.task_id,
        requested_by="admin",
        risk_level=task.risk_level,
    )
    reg.attach_token(task.task_id, token.token_id)

    # 승인 전 validate_token → False (issued 상태)
    assert not validate_token(token.token_id, task.task_id)

    # 승인
    approved_token, status = approve_token(
        token_id=token.token_id,
        task_id=task.task_id,
        approved_by="admin",
        role="admin",
    )
    assert status == "approved"

    # 승인 후 validate_token → True
    assert validate_token(token.token_id, task.task_id)


# ════════════════════════════════════════════════════════════════════════════
# 15. result_data 에 approval_id/execution_task_id/would_open_browser 저장
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_result_data_fields():
    from local_agent.actions import action_open_url_execute
    with mock.patch("local_agent.actions.webbrowser.open"):
        r = action_open_url_execute({
            "url": "https://example.com/page",
            "_approved": True,
            "_task_id": "lat-test123",
            "_approval_id": "tok-approval456",
        })
    assert r.success
    d = r.data
    assert d["would_open_browser"] is True
    assert d["dry_run"] is False
    assert d["external_network_call"] == "browser_possible"
    assert d["policy_decision"] == "approved_execution"
    assert d["approval_id"] == "tok-approval456"
    assert d["execution_task_id"] == "lat-test123"
    assert d["url_scheme"] == "https"
    assert d["url_host"] == "example.com"
    assert "normalized_url" in d


# ════════════════════════════════════════════════════════════════════════════
# 15b. _RESULT_DATA_ALLOWED_KEYS 에 신규 키 포함 확인
# ════════════════════════════════════════════════════════════════════════════

def test_result_data_allowed_keys_include_approval_fields():
    from ai_orchestrator.local_agent_registry import _RESULT_DATA_ALLOWED_KEYS
    for key in ("approval_id", "approved_by", "execution_task_id"):
        assert key in _RESULT_DATA_ALLOWED_KEYS, f"{key} 가 허용 목록에 없음"


# ════════════════════════════════════════════════════════════════════════════
# 16. router endpoint — waiting_approval 생성 + token attach
# ════════════════════════════════════════════════════════════════════════════

def test_router_open_url_execution_request_creates_waiting_approval():
    import ai_orchestrator.local_agent_registry as reg
    user = _make_admin_user()
    client = _make_test_client(user)

    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]

    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/open-url-execution-request",
        json={"url": "https://example.com/path?query=removed", "reason": "test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "waiting_approval"
    assert body["action"] == "open_url_execute"
    assert body["approval_required"] is True
    assert body["url_host"] == "example.com"
    assert "task_id" in body

    task_id = body["task_id"]
    task = reg.get_task(agent_id, task_id)
    assert task is not None
    assert task.status == "waiting_approval"
    # query string 은 params url 에 포함되지 않아야 함
    stored_url = task.params.get("url", "")
    assert "query=removed" not in stored_url
    assert "?" not in stored_url


def test_router_open_url_execution_request_bad_scheme():
    import ai_orchestrator.local_agent_registry as reg
    user = _make_admin_user()
    client = _make_test_client(user)

    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]

    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/open-url-execution-request",
        json={"url": "ftp://example.com"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "URL_SCHEME_NOT_ALLOWED"


def test_router_open_url_execution_request_missing_url():
    user = _make_admin_user()
    client = _make_test_client(user)

    resp = client.post("/api/v1/local-agents/nonexist/open-url-execution-request",
                       json={"url": ""})
    assert resp.status_code in (400, 404)


# ════════════════════════════════════════════════════════════════════════════
# 17. process_task (ws_client) — open_url_execute + approval 흐름
# ════════════════════════════════════════════════════════════════════════════

def test_process_task_open_url_execute_no_approved_refused():
    """process_task: approved=False → NOT_IMPLEMENTED_STAGE2."""
    from local_agent.websocket_client import process_task
    task = {
        "task_id": "lat-ws-001",
        "action": "open_url_execute",
        "params": {"url": "https://example.com"},
        "risk_level": "high",
        "approved": False,
    }
    result = process_task(task)
    assert not result["success"]
    assert result["error_code"] == "NOT_IMPLEMENTED_STAGE2"


def test_process_task_open_url_execute_approved_calls_action():
    """process_task: approved=True → execute_action 호출, webbrowser.open."""
    from local_agent.websocket_client import process_task
    task = {
        "task_id": "lat-ws-002",
        "action": "open_url_execute",
        "params": {"url": "https://example.com"},
        "risk_level": "high",
        "approved": True,
        "token_id": "tok-abc",
    }
    with mock.patch("local_agent.actions.webbrowser.open") as mock_open:
        result = process_task(task)
    assert result["success"], result
    mock_open.assert_called_once_with("https://example.com")


# ════════════════════════════════════════════════════════════════════════════
# 18. WS integration — open_url_execute full delivery path
#     (delivered → running → completed 상태 전이 검증)
# ════════════════════════════════════════════════════════════════════════════

def test_open_url_execute_ws_running_then_result_ack_completed(tmp_path):
    """open_url_execute WS full path: running → running_ack → result → result_ack(completed).

    서버 상태 기계: waiting_approval → queued → delivered → running → completed.
    running 없이 result 전송 시 InvalidTaskTransitionError 발생 확인도 포함한다.
    """
    import ai_orchestrator.local_agent_registry as reg
    from ai_orchestrator.approval import issue_token_for_dev_reg, approve_token

    user = _make_admin_user()
    client = _make_test_client(user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]

    # open_url_execute task 생성 (waiting_approval)
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/open-url-execution-request",
        json={"url": "https://example.com/ws-test", "reason": "ws integration test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    task_id = body["task_id"]
    assert body["status"] == "waiting_approval"

    # approval token 조회 후 승인
    task_obj = reg.get_task(agent_id, task_id)
    token_id = task_obj.token_id
    assert token_id, "approval token_id 가 task 에 없음"

    approve_resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert approve_resp.status_code == 200

    # WS: running → running_ack → result → result_ack(completed)
    with mock.patch("local_agent.actions.webbrowser.open"):
        with client.websocket_connect("/api/v1/local-agents/ws") as ws:
            device_token = reg_resp["device_token"]
            ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": device_token})
            assert ws.receive_json()["type"] == "auth_ok"

            msg = ws.receive_json()
            assert msg["type"] == "task"
            assert msg["task"]["task_id"] == task_id
            assert msg["task"]["action"] == "open_url_execute"
            assert msg["task"]["approved"] is True

            # delivered → running (필수)
            ws.send_json({"type": "running", "task_id": task_id})
            ack = ws.receive_json()
            assert ack["type"] == "running_ack"
            assert ack["status"] == "running"

            # result 전송 (running → completed)
            ws.send_json({
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": "open_url_execute_ok",
            })
            result_ack = ws.receive_json()
            assert result_ack["type"] == "result_ack"
            assert result_ack["status"] == "completed"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "completed"


def test_open_url_execute_ws_result_without_running_fails(tmp_path):
    """open_url_execute: running 없이 result 전송 시 WS 가 1011 로 종료되어야 한다.

    서버가 delivered → completed 전환을 허용하지 않음을 검증한다.
    """
    import ai_orchestrator.local_agent_registry as reg
    from starlette.websockets import WebSocketDisconnect

    user = _make_admin_user()
    client = _make_test_client(user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]

    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/open-url-execution-request",
        json={"url": "https://example.com/no-running"},
    )
    task_id = resp.json()["task_id"]
    task_obj = reg.get_task(agent_id, task_id)
    token_id = task_obj.token_id

    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json({"type": "auth", "agent_id": agent_id,
                          "device_token": reg_resp["device_token"]})
            assert ws.receive_json()["type"] == "auth_ok"
            assert ws.receive_json()["type"] == "task"

            # running 없이 바로 result(success=True) 전송 → delivered → completed 시도
            ws.send_json({
                "type": "result", "task_id": task_id,
                "success": True, "summary": "open_url_execute_ok",
            })
            ws.receive_json()  # 여기서 WebSocketDisconnect(1011) 발생해야 함


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
