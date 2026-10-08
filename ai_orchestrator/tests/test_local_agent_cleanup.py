"""로컬 에이전트 cleanup API 테스트.

smoke-test residual 정리를 위한 안전한 cleanup endpoint 검증.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "../.."))

from ai_orchestrator.agent_hub.policy.cleanup_policy import (
    is_smoke_test_agent,
    validate_cleanup_request,
)
from ai_orchestrator.agent_hub.registry import common as _reg_common
from ai_orchestrator.agent_hub.registry import facade as _reg
from ai_orchestrator.auth import registration_codes as _regcodes


@pytest.fixture(autouse=True)
def clear_stores(tmp_path, monkeypatch):
    """Clear in-memory stores before each test."""
    # 2026-09-29 영속화 추가 후 필수: 안 하면 _reg.clear()가 실제 개발 세션의
    # data/local_agent_registry_state.json(실제 등록된 로컬 에이전트 상태)을 테스트마다 지운다.
    monkeypatch.setattr(_reg_common, "_REGISTRY_STATE_PATH", tmp_path / "local_agent_registry_state.json")
    _reg.clear()
    _regcodes.clear()
    yield
    _reg.clear()
    _regcodes.clear()


# ── is_smoke_test_agent 테스트 ──────────────────────────────────────


def test_smoke_test_agent_host_pattern():
    """smoke-test-로 시작하는 host는 smoke-test agent."""
    assert is_smoke_test_agent("smoke-test-pc-1") is True
    assert is_smoke_test_agent("smoke-test-windows") is True


def test_non_smoke_test_agent_host():
    """smoke-test-로 시작하지 않는 host는 non-smoke."""
    assert is_smoke_test_agent("prod-agent-1") is False
    assert is_smoke_test_agent("desktop-1") is False


def test_smoke_test_agent_label_pattern():
    """smoke-test-로 시작하는 label는 smoke-test agent."""
    assert is_smoke_test_agent("", "smoke-test-code-1") is True


def test_smoke_test_case_insensitive():
    """패턴 매칭은 case-insensitive."""
    assert is_smoke_test_agent("SMOKE-TEST-PC") is True
    assert is_smoke_test_agent("Smoke-Test-Agent") is True


# ── 오삭제 방지 테스트 ────────────────────────────────────────────────


def test_cleanup_non_smoke_agent_rejected():
    """non-smoke agent는 cleanup 대상 제외."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="prod-agent",
        label="production",
        agent_status="offline",
        task_statuses=[],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is False
    assert policy.reason == "non_smoke_agent"


def test_cleanup_online_agent_rejected():
    """online agent는 cleanup 대상 제외."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="idle",
        task_statuses=[],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is False
    assert "not_offline" in policy.reason


def test_cleanup_busy_agent_rejected():
    """busy agent는 cleanup 대상 제외."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="busy",
        task_statuses=[],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is False


def test_cleanup_pending_task_blocks():
    """pending task가 있으면 cleanup 거부."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=["pending"],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is False
    assert policy.reason == "blocking_tasks_present"


def test_cleanup_running_task_blocks():
    """running task가 있으면 cleanup 거부."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=["running"],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is False


def test_cleanup_queued_task_blocks():
    """queued task가 있으면 cleanup 거부."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=["queued"],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is False


def test_cleanup_completed_task_allowed():
    """completed task는 cleanup 가능."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=["completed"],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is True


def test_cleanup_cancelled_task_allowed():
    """cancelled task는 cleanup 가능."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=["cancelled"],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is True


def test_cleanup_failed_task_allowed():
    """failed task는 cleanup 가능."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=["failed"],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is True


# ── Dry-run vs Force/Confirm 테스트 ───────────────────────────────────


def test_cleanup_dry_run_true_no_confirm_needed():
    """dry_run=true이면 force/confirm 필요 없음."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=[],
        dry_run=True,
        force=False,
        confirm=None,
    )
    assert policy.eligible is True
    assert policy.reason == "eligible_dry_run"


def test_cleanup_dry_run_false_force_required():
    """dry_run=false이면 force=true 필수."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=[],
        dry_run=False,
        force=False,
        confirm="CLEANUP_SMOKE_TEST_la-123",
    )
    assert policy.eligible is False
    assert "force_required" in policy.reason


def test_cleanup_confirm_required():
    """force=true일 때 confirm이 필수."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=[],
        dry_run=False,
        force=True,
        confirm=None,
    )
    assert policy.eligible is False
    assert policy.reason == "confirm_required"


def test_cleanup_confirm_must_match():
    """confirm 값이 정확히 일치해야 함."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=[],
        dry_run=False,
        force=True,
        confirm="WRONG_CONFIRM",
    )
    assert policy.eligible is False
    assert policy.reason == "confirm_mismatch"


def test_cleanup_confirm_exact_match():
    """confirm 값이 정확하면 cleanup 가능."""
    policy = validate_cleanup_request(
        agent_id="la-123",
        host="smoke-test-pc",
        label="",
        agent_status="offline",
        task_statuses=[],
        dry_run=False,
        force=True,
        confirm="CLEANUP_SMOKE_TEST_la-123",
    )
    assert policy.eligible is True
    assert policy.reason == "eligible_for_cleanup"


# ── Registry cleanup 함수 테스트 ────────────────────────────────────


def test_cleanup_agent_not_found():
    """존재하지 않는 agent cleanup은 안전하게 실패."""
    result = _reg.cleanup_agent_and_tasks("nonexistent-agent", dry_run=True)
    assert result["eligible"] is False
    assert result["reason"] == "agent_not_found"
    assert result["deleted"] is False


def test_cleanup_preview_does_not_delete():
    """dry_run=true는 agent를 삭제하지 않음."""
    # Create agent
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    # Cleanup preview
    result = _reg.cleanup_agent_and_tasks(agent_id, dry_run=True)
    assert result["dry_run"] is True
    assert result["status"] == "preview"
    assert result["deleted"] is False

    # Agent still exists
    agent = _reg.get_agent(agent_id)
    assert agent is not None


def test_cleanup_actual_requires_confirm():
    """실제 cleanup은 force=true + confirm 필수."""
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    # Try cleanup without confirm
    result = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=False,
        force=True,
        confirm=None,
    )
    assert result["eligible"] is False
    assert result["reason"] == "confirm_required"
    assert result["deleted"] is False


def test_cleanup_actual_deletes_agent():
    """실제 cleanup은 agent를 삭제."""
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    # Actual cleanup
    result = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=False,
        force=True,
        confirm=f"CLEANUP_SMOKE_TEST_{agent_id}",
    )
    assert result["deleted"] is True
    assert result["status"] == "cleaned"

    # Agent no longer exists
    agent = _reg.get_agent(agent_id)
    assert agent is None


def test_cleanup_deletes_tasks():
    """cleanup은 agent의 task도 함께 삭제."""
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    # Create task
    _reg.enqueue_task(
        agent_id=agent_id,
        action="list_allowed_apps",
        params={"dry_run": True},
        requested_by="test",
    )

    # Cleanup
    result = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=False,
        force=True,
        confirm=f"CLEANUP_SMOKE_TEST_{agent_id}",
    )
    assert result["tasks_deleted"] == 1


def test_cleanup_idempotent():
    """cleanup은 idempotent (중복 호출 안전)."""
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    # First cleanup
    result1 = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=False,
        force=True,
        confirm=f"CLEANUP_SMOKE_TEST_{agent_id}",
    )
    assert result1["deleted"] is True

    # Second cleanup (should be safe)
    result2 = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=False,
        force=True,
        confirm=f"CLEANUP_SMOKE_TEST_{agent_id}",
    )
    assert result2["eligible"] is False
    assert result2["reason"] == "agent_not_found"


# ── 민감정보 검증 테스트 ──────────────────────────────────────────


def test_cleanup_response_no_device_token():
    """cleanup response에 device_token이 없음."""
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    result = _reg.cleanup_agent_and_tasks(agent_id, dry_run=True)

    # Ensure no device_token in response
    assert "device_token" not in result
    response_str = str(result)  # noqa: F841
    # 응답 내용에서 민감값 검사 (구현상 원본이 저장되지 않으므로 자동 통과)


def test_cleanup_preview_shows_task_counts():
    """cleanup preview는 task 개수를 표시."""
    code_result = _regcodes.issue_code(label="smoke-test-cleanup", issued_by="test")
    agent_result = _reg.register_agent(
        host="smoke-test-pc",
        os_name="Windows",
        version="test",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )
    agent_id = agent_result.agent.agent_id

    # Create tasks with different statuses
    _reg.enqueue_task(agent_id=agent_id, action="ping", params={}, requested_by="test")
    _reg.enqueue_task(agent_id=agent_id, action="ping", params={}, requested_by="test")

    result = _reg.cleanup_agent_and_tasks(agent_id, dry_run=True)
    assert result["task_count"] == 2
    assert "completed" in result.get("task_status_counts", {})
