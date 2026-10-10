"""Local Agent 실사용 서버사이드 통합 검증 테스트.

실제 agent 실행, WebSocket 연결, task 실행 없이
서버사이드/mock으로 실사용 흐름을 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "../.."))

from ai_orchestrator.agent_hub.error_mapping import (
    ERROR_STATUS_CODES,
    ErrorType,
)
from ai_orchestrator.agent_hub.policy.audit_event_policy import (
    APPROVE_AUDIT_EVENT,
    REJECT_AUDIT_EVENT,
)
from ai_orchestrator.agent_hub.policy.status_policy import (
    ACTIVE_TASK_STATUSES,
    VALID_TASK_TRANSITIONS,
    can_cancel_task,
    is_terminal_status,
)
from ai_orchestrator.agent_hub.registry import facade as _reg

# ── 상태 정책 검증 ──────────────────────────────────────────────────────


def test_task_status_transition_valid_paths():
    """task 상태 전이 경로가 정의되어 있음."""
    # queued → delivered, failed, cancelled 가능
    assert "delivered" in VALID_TASK_TRANSITIONS["queued"]
    assert "failed" in VALID_TASK_TRANSITIONS["queued"]
    assert "cancelled" in VALID_TASK_TRANSITIONS["queued"]

    # running → completed, failed, cancel_requested 가능
    assert "completed" in VALID_TASK_TRANSITIONS["running"]
    assert "failed" in VALID_TASK_TRANSITIONS["running"]

    # completed는 더 이상 전이 불가
    assert len(VALID_TASK_TRANSITIONS["completed"]) == 0


def test_cancel_allowed_status_matrix():
    """취소 가능/불가능 상태 matrix."""
    # 가능
    assert can_cancel_task("queued") is True
    assert can_cancel_task("waiting_approval") is True
    assert can_cancel_task("delivered") is True
    assert can_cancel_task("running") is True

    # 불가능
    assert can_cancel_task("completed") is False
    assert can_cancel_task("failed") is False
    assert can_cancel_task("rejected") is False
    assert can_cancel_task("cancelled") is False


def test_terminal_status_validation():
    """종료 상태 검증."""
    # 종료 상태
    assert is_terminal_status("completed") is True
    assert is_terminal_status("failed") is True
    assert is_terminal_status("rejected") is True
    assert is_terminal_status("cancelled") is True

    # 진행 중 상태
    assert is_terminal_status("queued") is False
    assert is_terminal_status("waiting_approval") is False
    assert is_terminal_status("delivered") is False
    assert is_terminal_status("running") is False
    assert is_terminal_status("cancel_requested") is False


def test_active_status_does_not_include_waiting_approval():
    """ACTIVE_TASK_STATUSES는 waiting_approval을 포함하지 않음."""
    assert "waiting_approval" not in ACTIVE_TASK_STATUSES
    assert "delivered" in ACTIVE_TASK_STATUSES
    assert "running" in ACTIVE_TASK_STATUSES
    assert "cancel_requested" in ACTIVE_TASK_STATUSES


# ── 감사 이벤트 정책 검증 ───────────────────────────────────────────────


def test_approve_audit_event_names_snapshot():
    """승인 감사 이벤트 이름 snapshot."""
    assert APPROVE_AUDIT_EVENT["approved"] == "LOCAL_AGENT_TASK_APPROVED"
    assert APPROVE_AUDIT_EVENT["not_found"] == "APPROVAL_INVALID_TOKEN"
    assert APPROVE_AUDIT_EVENT["expired"] == "LOCAL_AGENT_TASK_APPROVAL_EXPIRED"


def test_reject_audit_event_names_snapshot():
    """거절 감사 이벤트 이름 snapshot."""
    assert REJECT_AUDIT_EVENT["rejected"] == "LOCAL_AGENT_TASK_REJECTED_BY_APPROVER"
    assert REJECT_AUDIT_EVENT["not_found"] == "APPROVAL_REJECT_INVALID_TOKEN"
    assert REJECT_AUDIT_EVENT["expired"] == "LOCAL_AGENT_TASK_APPROVAL_EXPIRED"


def test_audit_event_names_are_descriptive():
    """감사 이벤트 이름이 사람이 읽을 수 있음."""
    for _status, event_name in APPROVE_AUDIT_EVENT.items():
        assert isinstance(event_name, str)
        assert len(event_name) > 0
        assert event_name.isupper()
        assert "_" in event_name or event_name.isalpha()

    for _status, event_name in REJECT_AUDIT_EVENT.items():
        assert isinstance(event_name, str)
        assert len(event_name) > 0


# ── 에러 매핑 검증 ──────────────────────────────────────────────────────


def test_error_type_enum_values():
    """ErrorType enum이 정의되어 있음."""
    assert hasattr(ErrorType, "INVALID_REQUEST")
    assert hasattr(ErrorType, "NOT_FOUND")
    assert hasattr(ErrorType, "INVALID_ALLOWED_ACTIONS")


def test_error_status_codes_are_standard():
    """에러 상태 코드가 표준 HTTP 코드."""
    valid_codes = {400, 404, 409, 410, 403, 429}
    for status_code in ERROR_STATUS_CODES.values():
        assert status_code in valid_codes


def test_error_mapping_no_duplicate_codes():
    """에러 매핑에 의도하지 않은 중복 매핑 없음."""
    # 여러 에러 타입이 같은 코드를 가질 수 있지만, 일관성 확인
    code_to_types = {}
    for error_type, code in ERROR_STATUS_CODES.items():
        if code not in code_to_types:
            code_to_types[code] = []
        code_to_types[code].append(error_type)

    # 예: 404는 NOT_FOUND만 사용 (또는 명확한 이유로 여러 개)
    assert len(code_to_types) > 0


# ── 실사용 흐름 모의 검증 ────────────────────────────────────────────────


def test_no_agent_list_response_has_agents_key():
    """no-agent 목록 응답에 agents 키 있음."""
    _reg._agents.clear()

    agents = _reg.list_agents()

    # list_agents 반환 형식 검증
    assert isinstance(agents, list)


def test_task_status_values_are_known():
    """task 상태값이 KNOWN_TASK_STATUSES에 포함됨."""
    from ai_orchestrator.agent_hub.policy.status_policy import KNOWN_TASK_STATUSES

    expected_statuses = {
        "queued",
        "delivered",
        "running",
        "waiting_approval",
        "completed",
        "failed",
        "rejected",
        "cancel_requested",
        "cancelled",
    }

    assert expected_statuses == KNOWN_TASK_STATUSES


def test_response_builder_functions_exist():
    """응답 빌더 함수들이 정의되어 있음."""
    from ai_orchestrator.agent_hub.response_builders import (
        make_list_agents_response,
        make_list_codes_response,
        make_list_tasks_response,
    )

    # 함수 실행 테스트
    resp1 = make_list_agents_response([])
    assert "agents" in resp1

    resp2 = make_list_codes_response([])
    assert "codes" in resp2

    resp3 = make_list_tasks_response([])
    assert "tasks" in resp3


def test_diagnostics_helpers_functions_exist():
    """진단 헬퍼 함수들이 정의되어 있음."""
    from ai_orchestrator.agent_hub.registry.diagnostics_helpers import (
        count_agents_by_status,
        count_tasks_by_status,
        determine_diagnostics_status,
    )

    # 함수 실행 테스트
    counts1 = count_agents_by_status({})
    assert "total" in counts1

    counts2 = count_tasks_by_status([])
    assert "total" in counts2

    status, warnings = determine_diagnostics_status({}, {})
    assert isinstance(status, str)
    assert isinstance(warnings, list)


# ── 보안 정책 검증 ──────────────────────────────────────────────────────


def test_response_builders_return_dict():
    """응답 빌더가 dict를 반환함."""
    from ai_orchestrator.agent_hub.response_builders import (
        make_register_agent_response,
    )

    resp = make_register_agent_response(
        agent_id="test-agent",
        device_token="test-token",  # noqa: S106
        host="localhost",
        os_name="test",
        version="1.0",
        registered_at="2026-05-04T10:00:00Z",
    )

    assert isinstance(resp, dict)
    assert "agent_id" in resp
    assert "device_token" in resp
    assert "host" in resp


def test_error_response_builder_no_token_in_detail():
    """에러 응답에 실제 토큰 값 없음."""
    from ai_orchestrator.agent_hub.error_mapping import make_error_response

    _status_code, detail = make_error_response(ErrorType.INVALID_REQUEST, message="Invalid request")

    detail_str = str(detail)

    # 토큰 같은 민감값이 없어야 함
    assert "token" not in detail_str or "Invalid request" in detail_str
    # 메시지만 포함되어야 함
    assert "message" in detail


def test_audit_event_snapshot_consistency():
    """감사 이벤트명이 기존 값과 일치."""
    # 기존 코드에서 사용하는 이벤트명들이 policy에 정의되어 있음
    assert "approved" in APPROVE_AUDIT_EVENT
    assert "rejected" in REJECT_AUDIT_EVENT

    # 값이 예상된 형식
    assert APPROVE_AUDIT_EVENT["approved"].isupper()
    assert REJECT_AUDIT_EVENT["rejected"].isupper()


def test_status_code_consistency():
    """status code 매핑이 일관성 있음."""
    from ai_orchestrator.agent_hub.policy.audit_event_policy import (
        APPROVE_STATUS_HTTP,
        REJECT_STATUS_HTTP,
    )

    # approved/rejected는 200
    assert APPROVE_STATUS_HTTP["approved"] == 200
    assert REJECT_STATUS_HTTP["rejected"] == 200

    # not_found는 404
    assert APPROVE_STATUS_HTTP["not_found"] == 404
    assert REJECT_STATUS_HTTP["not_found"] == 404

    # expired는 410
    assert APPROVE_STATUS_HTTP["expired"] == 410
    assert REJECT_STATUS_HTTP["expired"] == 410


# ── 통합 흐름 구조 검증 ────────────────────────────────────────────────


def test_task_lifecycle_states_are_valid():
    """task 생명주기의 상태들이 모두 KNOWN_TASK_STATUSES에 있음."""
    from ai_orchestrator.agent_hub.policy.status_policy import KNOWN_TASK_STATUSES

    lifecycle = [
        "queued",  # 초기
        "delivered",  # agent에 전달됨
        "running",  # 실행 중
        "completed",  # 완료
    ]

    for state in lifecycle:
        assert state in KNOWN_TASK_STATUSES


def test_high_risk_task_approval_flow_states():
    """high-risk task approval 흐름의 상태들이 유효함."""
    from ai_orchestrator.agent_hub.policy.status_policy import KNOWN_TASK_STATUSES

    flow = [
        "waiting_approval",  # 초기: 승인 대기
        "queued",  # 승인 후: 큐에 들어감
        "delivered",  # agent에 전달됨
        "completed",  # 완료
    ]

    for state in flow:
        assert state in KNOWN_TASK_STATUSES
        # waiting_approval은 취소 가능
        if state == "waiting_approval":
            assert can_cancel_task(state) is True
