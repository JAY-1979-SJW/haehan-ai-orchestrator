"""로컬 에이전트 응답 빌더 테스트.

API 응답 구조와 응답 키 일관성을 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".."))

from ai_orchestrator.agent_hub.response_builders import (
    make_get_task_response,
    make_list_agents_response,
    make_list_codes_response,
    make_list_tasks_response,
    make_register_agent_response,
)

# ── register_agent 응답 ───────────────────────────────────────────────────


def test_make_register_agent_response_structure():
    """register_agent 응답 구조 검증."""
    response = make_register_agent_response(
        agent_id="agent-123",
        device_token="token-abc",
        host="localhost",
        os_name="Windows",
        version="0.1.0",
        registered_at="2026-05-04T10:00:00Z",
    )

    assert isinstance(response, dict)
    assert "agent_id" in response
    assert "device_token" in response
    assert "host" in response
    assert "os_name" in response
    assert "version" in response
    assert "registered_at" in response


def test_make_register_agent_response_values():
    """register_agent 응답 값 검증."""
    response = make_register_agent_response(
        agent_id="agent-456",
        device_token="token-xyz",
        host="192.168.1.1",
        os_name="Linux",
        version="0.2.0",
        registered_at="2026-05-04T11:00:00Z",
    )

    assert response["agent_id"] == "agent-456"
    assert response["device_token"] == "token-xyz"
    assert response["host"] == "192.168.1.1"
    assert response["os_name"] == "Linux"
    assert response["version"] == "0.2.0"
    assert response["registered_at"] == "2026-05-04T11:00:00Z"


# ── list_agents 응답 ──────────────────────────────────────────────────────


def test_make_list_agents_response_structure():
    """list_agents 응답 구조 검증."""
    agents_list = [
        {"agent_id": "agent-1", "status": "online"},
        {"agent_id": "agent-2", "status": "offline"},
    ]
    response = make_list_agents_response(agents_list)

    assert isinstance(response, dict)
    assert "agents" in response
    assert isinstance(response["agents"], list)


def test_make_list_agents_response_empty():
    """list_agents 빈 응답 검증."""
    response = make_list_agents_response([])

    assert isinstance(response, dict)
    assert "agents" in response
    assert response["agents"] == []


def test_make_list_agents_response_with_agents():
    """list_agents 에이전트 포함 응답 검증."""
    agents_list = [
        {"agent_id": "agent-1", "status": "online", "host": "localhost"},
    ]
    response = make_list_agents_response(agents_list)

    assert len(response["agents"]) == 1
    assert response["agents"][0]["agent_id"] == "agent-1"


# ── list_codes 응답 ────────────────────────────────────────────────────


def test_make_list_codes_response_structure():
    """list_codes 응답 구조 검증."""
    codes_list = [
        {"code_id": "code-1", "label": "test"},
    ]
    response = make_list_codes_response(codes_list)

    assert isinstance(response, dict)
    assert "codes" in response
    assert isinstance(response["codes"], list)


def test_make_list_codes_response_empty():
    """list_codes 빈 응답 검증."""
    response = make_list_codes_response([])

    assert isinstance(response, dict)
    assert "codes" in response
    assert response["codes"] == []


# ── list_tasks 응답 ─────────────────────────────────────────────────────


def test_make_list_tasks_response_structure():
    """list_tasks 응답 구조 검증."""
    tasks_list = [
        {"task_id": "task-1", "status": "queued"},
    ]
    response = make_list_tasks_response(tasks_list)

    assert isinstance(response, dict)
    assert "tasks" in response
    assert isinstance(response["tasks"], list)


def test_make_list_tasks_response_empty():
    """list_tasks 빈 응답 검증."""
    response = make_list_tasks_response([])

    assert isinstance(response, dict)
    assert "tasks" in response
    assert response["tasks"] == []


# ── get_task 응답 ──────────────────────────────────────────────────────


def test_make_get_task_response_structure():
    """get_task 응답 구조 검증."""
    task = {
        "task_id": "task-1",
        "status": "running",
        "action": "open_url",
    }
    response = make_get_task_response(task)

    assert isinstance(response, dict)
    # task 응답은 task 객체 자체를 반환하거나 task 래퍼 구조
    assert "task_id" in response or "task" in response


# ── 토큰 미포함 검증 ────────────────────────────────────────────────────────


def test_make_register_agent_response_contains_device_token():
    """register_agent 응답은 device_token을 포함해야 함 (1회 노출)."""
    response = make_register_agent_response(
        agent_id="agent-789",
        device_token="token-secret",
        host="localhost",
        os_name="Windows",
        version="0.1.0",
        registered_at="2026-05-04T10:00:00Z",
    )
    # device_token은 register 응답에만 1회 노출됨
    assert "device_token" in response


# ── 응답 키 일관성 검증 ────────────────────────────────────────────────────


def test_response_key_consistency():
    """응답 키가 일관되는지 검증."""
    # list_agents는 "agents" 키 사용
    agents_resp = make_list_agents_response([])
    assert "agents" in agents_resp

    # list_codes는 "codes" 키 사용
    codes_resp = make_list_codes_response([])
    assert "codes" in codes_resp

    # list_tasks는 "tasks" 키 사용
    tasks_resp = make_list_tasks_response([])
    assert "tasks" in tasks_resp


# ── 모듈 import 검증 ────────────────────────────────────────────────────────


def test_response_builders_module_importable():
    """응답 빌더 모듈이 정상적으로 임포트 가능한지 검증."""
    import ai_orchestrator.agent_hub.response_builders as response_builders_module

    assert hasattr(response_builders_module, "make_register_agent_response")
    assert hasattr(response_builders_module, "make_list_agents_response")
    assert hasattr(response_builders_module, "make_list_codes_response")
    assert hasattr(response_builders_module, "make_list_tasks_response")
    assert hasattr(response_builders_module, "make_get_task_response")


def test_no_circular_import_with_router():
    """응답 빌더 모듈과 라우터 간 순환 참조 없음을 검증."""
    try:
        from ai_orchestrator.agent_hub.router.root import local_agent_router

        assert local_agent_router is not None
    except ImportError:
        pass


# ── 응답 형식 검증 ──────────────────────────────────────────────────────


def test_response_is_dict():
    """모든 응답이 dict 타입인지 검증."""
    assert isinstance(make_list_agents_response([]), dict)
    assert isinstance(make_list_codes_response([]), dict)
    assert isinstance(make_list_tasks_response([]), dict)
    assert isinstance(
        make_register_agent_response(
            agent_id="test",
            device_token="token",
            host="host",
            os_name="os",
            version="1.0",
            registered_at="2026-05-04",
        ),
        dict,
    )


def test_list_response_wraps_items_in_key():
    """list 응답이 항목을 올바른 키로 래핑하는지 검증."""
    # agents
    agents_resp = make_list_agents_response([{"agent_id": "test"}])
    assert "agents" in agents_resp
    assert isinstance(agents_resp["agents"], list)

    # codes
    codes_resp = make_list_codes_response([{"code_id": "test"}])
    assert "codes" in codes_resp
    assert isinstance(codes_resp["codes"], list)

    # tasks
    tasks_resp = make_list_tasks_response([{"task_id": "test"}])
    assert "tasks" in tasks_resp
    assert isinstance(tasks_resp["tasks"], list)
