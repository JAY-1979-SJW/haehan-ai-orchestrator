"""cad-mcp 상류 호출 헬퍼.

read 와 write 를 코드 레벨에서 명시적으로 분리한다.

    call_cad_read(path, ...)
        → cad-backend 직통 (GET 전용, MCP_ALLOW_DIRECT_READ=true 기본)

    call_cad_write_via_orchestrator(path, method, ...)
        → orchestrator /api/v1/cad/* 경유 필수
        → cad-backend URL 은 이 함수에서 참조되지 않는다

금지 사항 (이 모듈 내):
    - write 경로에서 CAD_BACKEND_URL 참조
    - tool 마다 직접 httpx 호출 (항상 이 헬퍼 사용)
    - if 분기 없이 임의 URL 조합하는 함수 추가
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from . import config
from .write_guard import (
    McpWriteError,
    WriteContext,
    check_write_prerequisites,
)

logger = logging.getLogger(__name__)


# ── Read ──────────────────────────────────────────────────────────────

async def call_cad_read(
    path: str,
    *,
    query: Optional[dict[str, Any]] = None,
) -> dict:
    """cad-backend 직통 조회 (GET 전용, read-only).

    MCP_ALLOW_DIRECT_READ=false 이면 RuntimeError 발생.
    path: /api/v1/ 이후 상대경로 (예: "projects", "drawings/abc123")
    """
    if not config.MCP_ALLOW_DIRECT_READ:
        raise RuntimeError(
            "MCP_ALLOW_DIRECT_READ is false; direct cad-backend reads are disabled."
        )

    clean_query = {k: v for k, v in (query or {}).items() if v is not None}
    url = f"{config.CAD_BACKEND_URL}/api/v1/{path.lstrip('/')}"
    logger.debug("[MCP-READ] GET %s params=%s", url, clean_query)

    async with httpx.AsyncClient(timeout=config.READ_TIMEOUT_SEC) as client:
        resp = await client.get(url, params=clean_query)

    logger.info("[MCP-READ] GET %s status=%d", url, resp.status_code)
    resp.raise_for_status()
    return resp.json()


# ── Write ─────────────────────────────────────────────────────────────

async def call_cad_write_via_orchestrator(
    path: str,
    method: str,
    *,
    actor: str,
    task_id: str,
    approval_token: str,
    body: Optional[dict] = None,
    files: Optional[dict] = None,
) -> dict:
    """orchestrator /api/v1/cad/* 경유 write 호출.

    cad-backend 주소는 이 함수 내에서 절대 참조하지 않는다.
    1차 MCP 게이트(write_guard) → 통과 후 orchestrator 로 전달.
    orchestrator 에서 2차 auth/approval/audit 게이트 수행.

    Args:
        path: cad 경로 (예: "projects", "projects/{id}")
        method: HTTP method ("POST", "PATCH", "DELETE")
        actor: 실사용자 식별자 (audit trail)
        task_id: 사전 제출 task id
        approval_token: 사전 승인 approval token id
        body: JSON 바디 (선택)
        files: multipart 파일 (upload 전용)

    Raises:
        McpWriteError: MCP 레벨 1차 게이트 실패
        httpx.HTTPStatusError: orchestrator 응답 오류
    """
    # ── 1차 게이트: MCP 레벨 (실행 전 완전 차단) ────────────────────────
    ctx: WriteContext = check_write_prerequisites(
        orchestrator_url=config.ORCHESTRATOR_URL,
        actor=actor,
        task_id=task_id,
        approval_token=approval_token,
        allow_direct_write=config.MCP_ALLOW_DIRECT_WRITE,  # 항상 False
    )

    # ── 상류 URL: orchestrator 고정 (cad-backend URL 미참조) ────────────
    upstream_url = f"{ctx.orchestrator_url}/api/v1/cad/{path.lstrip('/')}"

    # approval 컨텍스트 헤더 (orchestrator cad_router 가 소비)
    headers: dict[str, str] = {
        "X-Task-Id": ctx.task_id,
        "X-Approval-Token-Id": ctx.approval_token,
        config.MCP_ACTOR_HEADER: ctx.actor,
    }

    # orchestrator 서비스 계정 Basic Auth
    auth = None
    if config.MCP_ORCHESTRATOR_USER and config.MCP_ORCHESTRATOR_PASS:
        auth = (config.MCP_ORCHESTRATOR_USER, config.MCP_ORCHESTRATOR_PASS)

    logger.info(
        "[MCP-WRITE] %s %s actor=%s task_id=%s",
        method.upper(), upstream_url, ctx.actor, ctx.task_id,
    )

    # ── 상류 호출 ─────────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=config.WRITE_TIMEOUT_SEC, auth=auth) as client:
        resp = await client.request(
            method=method.upper(),
            url=upstream_url,
            headers=headers,
            json=body if body is not None and files is None else None,
            files=files,
        )

    if not resp.is_success:
        logger.warning(
            "[MCP-WRITE-FAILED] %s %s status=%d actor=%s task_id=%s",
            method.upper(), upstream_url, resp.status_code,
            ctx.actor, ctx.task_id,
        )
        resp.raise_for_status()

    logger.info(
        "[MCP-WRITE-OK] %s %s status=%d actor=%s",
        method.upper(), upstream_url, resp.status_code, ctx.actor,
    )
    return resp.json() if resp.content else {}
