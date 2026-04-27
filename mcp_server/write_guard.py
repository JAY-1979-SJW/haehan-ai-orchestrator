"""MCP 레벨 1차 write 게이트.

write 성격 도구는 반드시 이 모듈의 ``check_write_prerequisites`` 를 거쳐야 한다.
조건 미충족 시 McpWriteError 를 발생시키고 표준 에러 코드를 반환한다.

이중 게이트 구조:
    1차 — mcp 레벨 (이 모듈): 실행 전 사전 차단
    2차 — orchestrator 레벨: /api/v1/cad/* approval 재검증

에러 코드:
    mcp_write_direct_forbidden       — MCP_ALLOW_DIRECT_WRITE 가 true 시 (항상 false 여야 함)
    mcp_write_requires_orchestrator  — ORCHESTRATOR_URL 미설정
    mcp_write_missing_actor          — actor 미제공
    mcp_write_requires_task_id       — task_id 미제공
    mcp_write_requires_approval      — approval_token 미제공
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteContext:
    """write 게이트 통과 시 반환되는 검증된 컨텍스트."""
    actor: str
    task_id: str
    approval_token: str
    orchestrator_url: str


class McpWriteError(ValueError):
    """MCP write 게이트 차단 — 표준 에러 코드 포함."""

    def __init__(self, error_code: str, detail: str) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(f"{error_code}: {detail}")


def check_write_prerequisites(
    *,
    orchestrator_url: str,
    actor: str | None,
    task_id: str | None,
    approval_token: str | None,
    allow_direct_write: bool,
) -> WriteContext:
    """MCP write 1차 게이트.

    통과하면 WriteContext 반환. 조건 미충족 시 McpWriteError 발생.
    모든 실패는 logger.warning 으로 기록된다.

    Args:
        orchestrator_url: ORCHESTRATOR_URL 설정값
        actor: 실사용자 식별자 (audit trail 용)
        task_id: 사전 제출된 task id
        approval_token: 사전 승인된 approval token id
        allow_direct_write: 항상 False 여야 정상 (config.MCP_ALLOW_DIRECT_WRITE)
    """
    # 0. 코드 레벨 하드락 — allow_direct_write 가 True 라면 설정 오류
    if allow_direct_write:
        _deny("mcp_write_direct_forbidden", actor, task_id,
              "MCP_ALLOW_DIRECT_WRITE must be False; direct cad-backend write is permanently blocked.")
        raise McpWriteError(
            "mcp_write_direct_forbidden",
            "direct write to cad-backend is hard-blocked at code level. "
            "This indicates a configuration error — MCP_ALLOW_DIRECT_WRITE cannot be set to true.",
        )

    # 1. orchestrator_url 존재 확인
    if not (orchestrator_url or "").strip():
        _deny("mcp_write_requires_orchestrator", actor, task_id,
              "ORCHESTRATOR_URL is not configured.")
        raise McpWriteError(
            "mcp_write_requires_orchestrator",
            "ORCHESTRATOR_URL env is not set. Write operations require orchestrator routing.",
        )

    # 2. actor 확인
    if not (actor or "").strip():
        _deny("mcp_write_missing_actor", actor, task_id,
              "actor parameter is missing.")
        raise McpWriteError(
            "mcp_write_missing_actor",
            "actor is required for audit trail. Provide the caller's username or identity.",
        )

    # 3. task_id 확인
    if not (task_id or "").strip():
        _deny("mcp_write_requires_task_id", actor, task_id,
              "task_id parameter is missing.")
        raise McpWriteError(
            "mcp_write_requires_task_id",
            "task_id is required. Submit task first via POST /api/v1/tasks to obtain task_id.",
        )

    # 4. approval_token 확인
    if not (approval_token or "").strip():
        _deny("mcp_write_requires_approval", actor, task_id,
              "approval_token is missing.")
        raise McpWriteError(
            "mcp_write_requires_approval",
            "approval_token is required. "
            "Get approval via POST /api/v1/tasks/{task_id}/approve (admin/owner only).",
        )

    return WriteContext(
        actor=actor.strip(),
        task_id=task_id.strip(),
        approval_token=approval_token.strip(),
        orchestrator_url=orchestrator_url.rstrip("/"),
    )


def _deny(code: str, actor: str | None, task_id: str | None, reason: str) -> None:
    logger.warning(
        "[MCP-WRITE-DENIED] code=%s actor=%s task_id=%s reason=%s",
        code, actor or "-", task_id or "-", reason,
    )
