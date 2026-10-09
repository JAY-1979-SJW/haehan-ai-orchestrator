"""ASSISTANT_BACKEND_ENUMS_SAFE_RESULT_ALIGNMENT_01 — characterization 테스트.

현재 동작을 기준선으로 고정한다.
DB, 서버, 외부 URL, 브라우저 실행 없음.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. RiskLevel 값이 기존 소문자 low/medium/high/critical과 일치한다.
# ---------------------------------------------------------------------------


def test_risk_level_values():
    from ai_orchestrator.domain.enums import RiskLevel

    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"
    assert RiskLevel.CRITICAL.value == "critical"
    # 문자열 비교 호환
    assert RiskLevel.LOW == "low"
    assert RiskLevel.HIGH == "high"


# ---------------------------------------------------------------------------
# 2. ExecutionLocation 5값이 모두 존재한다.
# ---------------------------------------------------------------------------


def test_execution_location_values():
    from ai_orchestrator.domain.enums import ExecutionLocation

    assert ExecutionLocation.SERVER_INTERNAL_ONLY.value == "SERVER_INTERNAL_ONLY"
    assert ExecutionLocation.SERVER_BROWSER_ALLOWED.value == "SERVER_BROWSER_ALLOWED"
    assert ExecutionLocation.LOCAL_AGENT_REQUIRED.value == "LOCAL_AGENT_REQUIRED"
    assert ExecutionLocation.USER_DIRECT_REQUIRED.value == "USER_DIRECT_REQUIRED"
    assert ExecutionLocation.BLOCKED.value == "BLOCKED"
    # 기존 execution_location_guard 상수와 값 일치
    from ai_orchestrator.server.execution_location_guard import (
        BLOCKED,
        LOCAL_AGENT_REQUIRED,
        SERVER_INTERNAL_ONLY,
        USER_DIRECT_REQUIRED,
    )

    assert ExecutionLocation.SERVER_INTERNAL_ONLY == SERVER_INTERNAL_ONLY
    assert ExecutionLocation.LOCAL_AGENT_REQUIRED == LOCAL_AGENT_REQUIRED
    assert ExecutionLocation.USER_DIRECT_REQUIRED == USER_DIRECT_REQUIRED
    assert ExecutionLocation.BLOCKED == BLOCKED


# ---------------------------------------------------------------------------
# 3. TaskStatus가 기존 task_state 값과 local_agent_status_policy 값을 모두 포함한다.
# ---------------------------------------------------------------------------


def test_task_status_covers_task_state():
    from ai_orchestrator.domain.enums import TaskStatus

    # task_state.py TaskState = Literal["pending","approved","rejected","executed"]
    for v in ("pending", "approved", "rejected", "executed"):
        assert TaskStatus(v).value == v


def test_task_status_covers_local_agent_status_policy():
    from ai_orchestrator.agent_hub.policy.status_policy import KNOWN_TASK_STATUSES
    from ai_orchestrator.domain.enums import TaskStatus

    for v in KNOWN_TASK_STATUSES:
        assert TaskStatus(v).value == v


def test_task_status_timed_out():
    from ai_orchestrator.domain.enums import TaskStatus

    assert TaskStatus.TIMED_OUT.value == "timed_out"


# ---------------------------------------------------------------------------
# 4. ApprovalStatus가 기존 5값 + escalated/cancelled를 포함한다.
# ---------------------------------------------------------------------------


def test_approval_status_values():
    from ai_orchestrator.domain.enums import ApprovalStatus

    for v in ("issued", "approved", "expired", "revoked", "rejected"):
        assert ApprovalStatus(v).value == v
    assert ApprovalStatus.ESCALATED.value == "escalated"
    assert ApprovalStatus.CANCELLED.value == "cancelled"


# ---------------------------------------------------------------------------
# 5. Verdict가 PASS/WARN/FAIL/BLOCK/SKIP/ERROR를 포함한다.
# ---------------------------------------------------------------------------


def test_verdict_values():
    from ai_orchestrator.domain.enums import Verdict

    for v in ("PASS", "WARN", "FAIL", "BLOCK", "SKIP", "ERROR"):
        assert Verdict(v).value == v
    # BrowserAuditStatus 기존 값(PASS/WARN/FAIL/SKIP/ERROR)이 Verdict에 포함됨
    from core.agent_runtime.browser.approval.browser_audit_contract import BrowserAuditStatus

    for bs in BrowserAuditStatus:
        assert Verdict(bs.value).value == bs.value


# ---------------------------------------------------------------------------
# 6. ApiResponse/api_success/api_error가 {success, data, error, meta} 구조를 만든다.
# ---------------------------------------------------------------------------


def test_api_success_structure():
    from ai_orchestrator.domain.response_envelope import ApiResponse, api_success

    resp = api_success(data={"key": "value"})
    assert isinstance(resp, ApiResponse)
    assert resp.success is True
    assert resp.data == {"key": "value"}
    assert resp.error is None


def test_api_error_structure():
    from ai_orchestrator.domain.response_envelope import ApiError, ApiResponse, api_error

    resp = api_error(code="NOT_FOUND", message="리소스 없음")
    assert isinstance(resp, ApiResponse)
    assert resp.success is False
    assert isinstance(resp.error, ApiError)
    assert resp.error.code == "NOT_FOUND"
    assert resp.error.message == "리소스 없음"
    assert resp.data is None


def test_api_response_fields():
    from ai_orchestrator.domain.response_envelope import ApiMeta, ApiResponse

    resp = ApiResponse(
        success=True,
        data=[1, 2, 3],
        meta=ApiMeta(total=3, page=1, page_size=10),
    )
    assert resp.meta.total == 3
    assert resp.meta.page == 1


# ---------------------------------------------------------------------------
# 7. 기존 execution_location_guard의 주요 분류 함수가 import error 없이 동작한다.
# ---------------------------------------------------------------------------


def test_execution_location_guard_import():
    from ai_orchestrator.server.execution_location_guard import (
        classify_execution_location_for_server,
        validate_task_execution_location,
    )

    assert callable(classify_execution_location_for_server)
    assert callable(validate_task_execution_location)
    result = classify_execution_location_for_server({"action": "ping", "task_id": "t1"})
    assert isinstance(result, dict)
    assert "execution_location" in result


# ---------------------------------------------------------------------------
# 8. 기존 approval.py가 import error 없이 동작한다.
# ---------------------------------------------------------------------------


def test_approval_import():
    from tools.gates.approval import issue_token

    assert callable(issue_token)


# ---------------------------------------------------------------------------
# 9. 기존 local_agent_status_policy.py가 import error 없이 동작한다.
# ---------------------------------------------------------------------------


def test_local_agent_status_policy_import():
    from ai_orchestrator.agent_hub.policy.status_policy import (
        ACTIVE_TASK_STATUSES,
        CANCELLABLE_TASK_STATUSES,
        TERMINAL_TASK_STATUSES,
        can_cancel_task,
    )

    assert "running" in ACTIVE_TASK_STATUSES
    assert "queued" in CANCELLABLE_TASK_STATUSES
    assert "completed" in TERMINAL_TASK_STATUSES
    assert callable(can_cancel_task)
