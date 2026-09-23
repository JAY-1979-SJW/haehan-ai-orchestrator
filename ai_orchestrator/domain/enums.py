"""ai_orchestrator 도메인 단일 기준 enum 파일.

이 파일은 기존 코드와의 호환성을 유지하며, 분산된 enum/상수를 한 곳에 정의한다.
기존 파일(task_state 모듈, local_agent_status_policy 모듈, approval 모듈 등)은
삭제하거나 수정하지 않는다. 이 파일은 기준선 역할만 한다.

외부 JSON/API 호환: 값(value)은 기존 소문자 문자열 그대로 유지.
"""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):  # noqa: UP042
    """액션 위험 등급 (ai_orchestrator 도메인 기준).

    기존 models.py Literal["low","medium","high","critical"]과 값 호환.
    scripts/schemas.py의 RiskLevel(AUTO/NOTIFY/APPROVE/BLOCK)은 별개 도메인이므로 충돌 없음.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionLocation(str, Enum):  # noqa: UP042
    """실행 위치 분류 (ai_orchestrator 도메인 기준).

    기존 server/execution_location_guard 모듈 문자열 상수와 값 호환.
    scripts/site_engine/types.py의 ExecutionLocation(SERVER/LOCAL_AGENT/USER_DIRECT)과는
    별개 파일에 정의되어 있으며, 이 파일은 execution_location_guard 모듈 기준을 따른다.
    """

    SERVER_INTERNAL_ONLY = "SERVER_INTERNAL_ONLY"
    SERVER_BROWSER_ALLOWED = "SERVER_BROWSER_ALLOWED"
    LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
    USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
    BLOCKED = "BLOCKED"


class TaskStatus(str, Enum):  # noqa: UP042
    """태스크 상태 통합 enum.

    기존 task_state 모듈 TaskState Literal 4값 +
    local_agent_status_policy 모듈 KNOWN_TASK_STATUSES 9값 +
    timed_out 확장값 포함.
    """

    # task_state 모듈 계열
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    # local_agent_status_policy 모듈 계열
    QUEUED = "queued"
    DELIVERED = "delivered"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    # 확장값
    TIMED_OUT = "timed_out"


class ApprovalStatus(str, Enum):  # noqa: UP042
    """승인 토큰 상태 통합 enum.

    기존 approval 모듈 Literal["issued","approved","expired","revoked","rejected"] 5값 +
    확장 호환값(ESCALATED, CANCELLED) 포함.
    기존 로직의 상태 전이는 변경하지 않는다.
    """

    ISSUED = "issued"
    APPROVED = "approved"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REJECTED = "rejected"
    # 확장 호환값 (기존 코드 미사용, 향후 호환용)
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class Verdict(str, Enum):  # noqa: UP042
    """감사/게이트 판정 결과 통합 enum.

    BrowserAuditStatus(PASS/WARN/FAIL/SKIP/ERROR) 포함 +
    BLOCK 확장.
    """

    PASS = "PASS"  # noqa: S105
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCK = "BLOCK"
    SKIP = "SKIP"
    ERROR = "ERROR"
