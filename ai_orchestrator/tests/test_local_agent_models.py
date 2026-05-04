"""로컬 에이전트 모델 테스트.

LocalAgent, LocalAgentTask, RegisterResult 모델의 필드, 기본값, 응답 shape를 검증한다.
분리 전후 동등성을 고정한다.
"""

import pytest
from ai_orchestrator.local_agent_registry import (
    LocalAgent, LocalAgentTask, RegisterResult,
    register_agent, enqueue_task, clear
)


@pytest.fixture(autouse=True)
def cleanup():
    """테스트 전후 registry 정리."""
    clear()
    yield
    clear()


# LocalAgent 테스트

def test_local_agent_fields():
    """LocalAgent 필드가 기존과 동일하다."""
    result = register_agent(
        host="test-host",
        os_name="Windows 11",
        version="0.1.0",
        requested_by="test-user",
    )
    agent = result.agent

    # 필드 존재 확인
    assert hasattr(agent, "agent_id")
    assert hasattr(agent, "host")
    assert hasattr(agent, "os_name")
    assert hasattr(agent, "version")
    assert hasattr(agent, "registered_at")
    assert hasattr(agent, "requested_by")
    assert hasattr(agent, "token_hash")
    assert hasattr(agent, "connected_at")
    assert hasattr(agent, "last_seen_at")
    assert hasattr(agent, "disconnected_at")


def test_local_agent_to_safe_shape():
    """LocalAgent.to_safe() 응답 key가 기존과 동일하다."""
    result = register_agent(
        host="test-host",
        os_name="Windows 11",
        version="0.1.0",
        requested_by="test-user",
    )
    safe = result.agent.to_safe()

    expected_keys = {
        "agent_id", "host", "os_name", "version", "registered_at",
        "requested_by", "agent_status", "connected_at", "last_seen_at",
        "disconnected_at", "active_task_count", "current_task_id",
        "task_count", "completed_task_count", "failed_task_count",
    }
    assert set(safe.keys()) == expected_keys


def test_local_agent_to_safe_no_token_hash():
    """LocalAgent.to_safe()에 token_hash가 포함되지 않는다."""
    result = register_agent(
        host="test-host",
        os_name="Windows 11",
        version="0.1.0",
        requested_by="test-user",
    )
    safe = result.agent.to_safe()

    assert "token_hash" not in safe
    assert "device_token" not in safe


def test_register_result_fields():
    """RegisterResult 필드가 기존과 동일하다."""
    result = register_agent(
        host="test-host",
        os_name="Windows 11",
        version="0.1.0",
        requested_by="test-user",
    )

    assert hasattr(result, "agent")
    assert hasattr(result, "device_token")
    assert isinstance(result.agent, LocalAgent)
    assert isinstance(result.device_token, str)


# LocalAgentTask 테스트

def test_local_agent_task_fields():
    """LocalAgentTask 필드가 기존과 동일하다."""
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )

    # 필수 필드
    assert hasattr(task, "task_id")
    assert hasattr(task, "agent_id")
    assert hasattr(task, "action")
    assert hasattr(task, "params")
    assert hasattr(task, "risk_level")
    assert hasattr(task, "status")
    assert hasattr(task, "requested_by")
    assert hasattr(task, "created_at")
    assert hasattr(task, "updated_at")

    # 선택 필드
    assert hasattr(task, "token_id")
    assert hasattr(task, "approval_public_id")
    assert hasattr(task, "result_summary")
    assert hasattr(task, "delivered_at")
    assert hasattr(task, "started_at")
    assert hasattr(task, "completed_at")
    assert hasattr(task, "error_summary")
    assert hasattr(task, "approved_at")
    assert hasattr(task, "approved_by")
    assert hasattr(task, "cancelled_at")
    assert hasattr(task, "observe_summary")
    assert hasattr(task, "audit_summary")
    assert hasattr(task, "result_data")


def test_local_agent_task_to_safe_shape():
    """LocalAgentTask.to_safe() 응답 key가 기존과 동일하다."""
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )
    safe = task.to_safe()

    expected_keys = {
        "task_id", "agent_id", "action", "params", "risk_level",
        "status", "requested_by", "created_at", "updated_at",
        "token_id", "approval_id", "approval_public_id", "result_summary",
        "delivered_at", "started_at", "completed_at", "error_summary",
        "approved_at", "approved_by", "rejected_at", "reject_reason",
        "failure_reason", "timed_out_at", "cancel_reason",
        "cancel_requested_at", "cancel_requested_by", "cancelled_at",
        "observe_summary", "audit_summary", "result_data",
    }
    assert set(safe.keys()) == expected_keys


def test_local_agent_task_to_list_safe_shape():
    """LocalAgentTask.to_list_safe() 응답 key가 기존과 동일하다."""
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )
    list_safe = task.to_list_safe()

    expected_keys = {
        "task_id", "agent_id", "action", "risk_level", "status",
        "requested_by", "created_at", "updated_at", "delivered_at",
        "started_at", "completed_at", "failure_reason", "timed_out_at",
        "error_summary", "result_summary", "cancel_reason",
        "cancel_requested_at", "cancel_requested_by", "cancelled_at",
    }
    assert set(list_safe.keys()) == expected_keys


def test_local_agent_task_to_dispatch_shape():
    """LocalAgentTask.to_dispatch() 응답 key가 기존과 동일하다."""
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )
    dispatch = task.to_dispatch()

    # low risk non-auto-complete는 approved=false
    assert "task_id" in dispatch
    assert "agent_id" in dispatch
    assert "action" in dispatch
    assert "params" in dispatch
    assert "risk_level" in dispatch
    assert "approved" in dispatch
    assert dispatch["approved"] is False


def test_local_agent_task_to_safe_no_token_id_in_list():
    """LocalAgentTask.to_list_safe()에 token_id가 없다."""
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )
    list_safe = task.to_list_safe()

    assert "token_id" not in list_safe
    assert "approval_id" not in list_safe


def test_local_agent_task_to_safe_includes_params():
    """LocalAgentTask.to_safe()에 params가 포함된다 (이미 민감값 제거됨)."""
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={"key": "value"},
        requested_by="test-user",
    )
    safe = task.to_safe()

    assert "params" in safe
    assert isinstance(safe["params"], dict)
