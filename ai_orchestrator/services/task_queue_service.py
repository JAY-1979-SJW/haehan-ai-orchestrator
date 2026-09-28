"""Task Queue Service — task 큐 조회/분류/count 서비스 계층.

책임:
- pending task 안전 조회 (금지 필드 차단)
- execution_location별 count 계산
- LOCAL_AGENT_REQUIRED / USER_DIRECT_REQUIRED / BLOCKED / SERVER_INTERNAL_ONLY 분류
- forbidden field stripping 통합 적용

금지:
- task 실행 금지
- DB write 금지
- 운영 데이터 write 금지
- 기존 API 응답 변경 금지

기존 원본:
- ai_orchestrator/server/task_queue_schema.py (원본 유지)
- desktop/task_receiver.py (원본 유지)

이 서비스는 얇은 조립 계층이다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 통합 금지 필드 — task_queue_schema + domain/models + desktop/task_receiver 교집합
_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "cookie",
        "cookies",
        "session",
        "authorization",
        "password",
        "otp",
        "certificate_password",
        "certificate_file_path",
        "localstorage",
        "sessionstorage",
        "token",
        "access_token",
        "refresh_token",
        "npki",
        "private_key",
        "auth_header",
        "approval_token",
        "final_approval_token",
        "token_hash",
        "typed_text",
        "device_token",
        "raw_screenshot",
        "base64",
    }
)

# execution location 상수 (execution_location_guard.py 값 호환)
_LOC_SERVER = "SERVER_INTERNAL_ONLY"
_LOC_AGENT = "LOCAL_AGENT_REQUIRED"
_LOC_USER = "USER_DIRECT_REQUIRED"
_LOC_BLOCKED = "BLOCKED"


def _strip_forbidden(d: dict[str, Any]) -> dict[str, Any]:
    """금지 필드를 재귀적으로 제거한다."""
    result = {}
    for k, v in d.items():
        if k.lower() in _FORBIDDEN_FIELDS:
            continue
        if isinstance(v, dict):
            result[k] = _strip_forbidden(v)
        else:
            result[k] = v
    return result


def _classify_location(task: dict[str, Any]) -> str:
    """task dict에서 execution_location을 추출하거나 추정한다."""
    # 명시적 필드 우선
    for key in ("execution_location", "exec_location", "location"):
        loc = task.get(key, "")
        if loc:
            return str(loc)
    # payload 안에서 찾기
    payload = task.get("payload", {})
    if isinstance(payload, dict):
        loc = payload.get("execution_location", "")
        if loc:
            return str(loc)
    # 기본값
    return _LOC_SERVER


@dataclass
class TaskQueueSummary:
    """Task 큐 분류 요약 — 읽기 전용."""

    total_pending: int = 0
    server_internal_count: int = 0
    local_agent_count: int = 0
    user_direct_count: int = 0
    blocked_count: int = 0
    safe_tasks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_pending": self.total_pending,
            "server_internal_count": self.server_internal_count,
            "local_agent_count": self.local_agent_count,
            "user_direct_count": self.user_direct_count,
            "blocked_count": self.blocked_count,
        }

    def tray_label(self) -> str:
        parts = []
        if self.local_agent_count:
            parts.append(f"에이전트 {self.local_agent_count}건")
        if self.user_direct_count:
            parts.append(f"직접 조작 {self.user_direct_count}건")
        if self.blocked_count:
            parts.append(f"차단 {self.blocked_count}건")
        if not parts:
            return "수신 작업: 대기 없음"
        return "수신 작업: " + ", ".join(parts)


class TaskQueueService:
    """Task 큐 조회/분류/count 서비스.

    기존 task_queue_schema.py의 get_pending_tasks()를 얇게 감싸서
    forbidden field stripping + location 분류를 추가한다.
    """

    def get_pending_tasks_safe(self, limit: int = 100) -> list[dict[str, Any]]:
        """pending task 목록을 금지 필드 제거 후 반환한다."""
        try:
            from ai_orchestrator.server.task_queue_schema import get_pending_tasks

            raw_tasks = get_pending_tasks(limit=limit)
        except Exception as exc:  # noqa: BLE001 - task_queue_schema 조회 실패 시 debug 로그 남기고 빈 목록 반환 - 읽기전용 조회 폴백, 실패해도 작업 누락(빈 결과)만 발생할 뿐 위험 조작 없음
            logger.debug("task_queue_schema 조회 실패: %s", exc)
            raw_tasks = []
        return [_strip_forbidden(t) for t in raw_tasks]

    def get_queue_summary(self, limit: int = 100) -> TaskQueueSummary:
        """pending task 분류 요약을 반환한다."""
        safe_tasks = self.get_pending_tasks_safe(limit=limit)
        summary = TaskQueueSummary(total_pending=len(safe_tasks))

        for task in safe_tasks:
            loc = _classify_location(task)
            if loc == _LOC_AGENT:
                summary.local_agent_count += 1
            elif loc == _LOC_USER:
                summary.user_direct_count += 1
            elif loc == _LOC_BLOCKED:
                summary.blocked_count += 1
            else:
                summary.server_internal_count += 1

        summary.safe_tasks = safe_tasks
        return summary

    def count_by_location(self) -> dict[str, int]:
        """execution_location별 pending count를 반환한다."""
        summary = self.get_queue_summary()
        return {
            _LOC_SERVER: summary.server_internal_count,
            _LOC_AGENT: summary.local_agent_count,
            _LOC_USER: summary.user_direct_count,
            _LOC_BLOCKED: summary.blocked_count,
        }

    def validate_no_forbidden_fields(self, task: dict[str, Any]) -> list[str]:
        """task dict에 금지 필드가 없는지 검증. 위반 key 목록 반환."""
        violations = []
        for key in task:
            if key.lower() in _FORBIDDEN_FIELDS:
                violations.append(key)
        payload = task.get("payload", {})
        if isinstance(payload, dict):
            for key in payload:
                if key.lower() in _FORBIDDEN_FIELDS:
                    violations.append(f"payload.{key}")
        return violations


# 싱글턴 인스턴스 (경량 — 상태 없음)
_service_instance: TaskQueueService | None = None


def get_task_queue_service() -> TaskQueueService:
    """TaskQueueService 싱글턴을 반환한다."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TaskQueueService()
    return _service_instance
