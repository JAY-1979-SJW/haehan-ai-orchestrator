"""cad-mcp MCP 서버 진입점.

read / write 도구 분리 원칙:
    - read 도구: call_cad_read() 경유 → cad-backend 직통 (GET 전용)
    - write 도구: call_cad_write_via_orchestrator() 경유 → orchestrator 필수
    - 도구 내부에서 직접 httpx/requests 호출 금지

write 도구 공통 필수 파라미터:
    actor          — 실사용자 식별자 (audit trail 용)
    task_id        — POST /api/v1/tasks 로 사전 제출 후 획득
    approval_token — POST /api/v1/tasks/{id}/approve 로 사전 승인 후 획득

실행 모드:
    로컬 Claude Desktop : MCP_TRANSPORT=stdio (기본)
    컨테이너 SSE        : MCP_TRANSPORT=sse

환경변수 상세: mcp_server/config.py 참고
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# FastMCP 임포트 — mcp 패키지(pip install mcp) 에서 제공
try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:  # 테스트/CI 환경에서 mcp 미설치 시
    _MCP_AVAILABLE = False
    FastMCP = None  # type: ignore[assignment,misc]

from .upstream import call_cad_read, call_cad_write_via_orchestrator
from .write_guard import McpWriteError
from .local_cad_adapter_tools import (
    cad_agent_active_document_json,
    cad_agent_connect_json,
    cad_agent_health_json,
    cad_agent_status_json,
    cad_local_adapter_execute_json,
    cad_local_adapter_ping_json,
    cad_local_adapter_status_json,
    cad_local_autocad_ping_json,
    cad_local_bridge_health_json,
)

mcp = FastMCP("cad-mcp") if _MCP_AVAILABLE else None


# ── 공용 직렬화 헬퍼 ──────────────────────────────────────────────────

def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _write_error(e: McpWriteError) -> str:
    return json.dumps(
        {"error": e.error_code, "detail": e.detail}, ensure_ascii=False
    )


# ═════════════════════════════════════════════════════════════════════
# READ 도구 (22개) — cad-backend 직통, approval 불필요
# ═════════════════════════════════════════════════════════════════════

if _MCP_AVAILABLE:
    @mcp.tool()
    async def cad_agent_health() -> str:
        """Check localhost CAD agent health without touching AutoCAD COM."""
        return cad_agent_health_json()

    @mcp.tool()
    async def cad_agent_connect(timeout_seconds: int = 20) -> str:
        """Start/connect localhost CAD agent to AutoCAD COM and keep it alive."""
        return cad_agent_connect_json(timeout_seconds)

    @mcp.tool()
    async def cad_agent_status() -> str:
        """Return persistent localhost CAD agent connection status."""
        return cad_agent_status_json()

    @mcp.tool()
    async def cad_agent_active_document(timeout_seconds: int = 10) -> str:
        """Return active document info through the persistent localhost CAD agent."""
        return cad_agent_active_document_json(timeout_seconds)

    @mcp.tool()
    async def cad_local_adapter_ping() -> str:
        """로컬 CAD 어댑터 ping. AutoCAD 명령/도면 수정 없음."""
        return cad_local_adapter_ping_json()

    @mcp.tool()
    async def cad_local_adapter_status() -> str:
        """로컬 CAD 어댑터와 모듈 바인딩 상태 조회. AutoCAD 명령/도면 수정 없음."""
        return cad_local_adapter_status_json()

    @mcp.tool()
    async def cad_local_autocad_ping(timeout_seconds: int = 10) -> str:
        """Local AutoCAD backend ping with timeout isolation."""
        return cad_local_autocad_ping_json(timeout_seconds)

    @mcp.tool()
    async def cad_local_bridge_health(timeout_seconds: int = 5) -> str:
        """End-to-end CAD bridge health: MCP -> local agent -> adapter -> AutoCAD ping."""
        return cad_local_bridge_health_json(timeout_seconds)

    @mcp.tool()
    async def cad_local_adapter_execute(tool_id: str, args: Optional[dict] = None) -> str:
        """로컬 CAD 어댑터 read-only tool 실행. 수정/삭제 tool은 로컬에서 차단."""
        return cad_local_adapter_execute_json(tool_id, args or {})

    @mcp.tool()
    async def cad_list_projects(
        status: Optional[str] = None,
        trade_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """프로젝트 목록 조회 (read-only)."""
        return _json(await call_cad_read(
            "projects",
            query={"status": status, "trade_type": trade_type,
                   "limit": limit, "offset": offset},
        ))

    @mcp.tool()
    async def cad_get_project(project_id: str) -> str:
        """프로젝트 단건 조회 (read-only)."""
        return _json(await call_cad_read(f"projects/{project_id}"))

    @mcp.tool()
    async def cad_list_drawings(
        project_id: str,
        discipline: Optional[str] = None,
        parse_status: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """프로젝트 도면 목록 (read-only)."""
        return _json(await call_cad_read(
            f"projects/{project_id}/drawings",
            query={"discipline": discipline, "parse_status": parse_status, "limit": limit},
        ))

    @mcp.tool()
    async def cad_get_drawing(drawing_id: str) -> str:
        """도면 단건 조회 (read-only)."""
        return _json(await call_cad_read(f"drawings/{drawing_id}"))

    @mcp.tool()
    async def cad_list_drawing_parse_jobs(drawing_id: str, limit: int = 20) -> str:
        """도면의 파싱 작업 이력 (read-only)."""
        return _json(await call_cad_read(
            f"drawings/{drawing_id}/parse-jobs", query={"limit": limit}
        ))

    @mcp.tool()
    async def cad_get_drawing_parse_status(drawing_id: str) -> str:
        """도면 파싱 상태 조회 (read-only)."""
        return _json(await call_cad_read(f"drawings/{drawing_id}/parse/status"))

    @mcp.tool()
    async def cad_get_parse_job(job_id: str) -> str:
        """파싱 작업 단건 조회 (read-only)."""
        return _json(await call_cad_read(f"parse/jobs/{job_id}"))

    @mcp.tool()
    async def cad_get_parse_logs(job_id: str) -> str:
        """파싱 작업 로그 조회 (read-only)."""
        return _json(await call_cad_read(f"parse/jobs/{job_id}/logs"))

    @mcp.tool()
    async def cad_get_project_parse_status(project_id: str) -> str:
        """프로젝트 전체 파싱 상태 (read-only)."""
        return _json(await call_cad_read(f"projects/{project_id}/parse/status"))

    @mcp.tool()
    async def cad_list_parsed_entities(
        project_id: str,
        drawing_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """파싱된 엔터티 목록 (read-only)."""
        return _json(await call_cad_read(
            f"projects/{project_id}/parsed-entities",
            query={"drawing_id": drawing_id, "entity_type": entity_type,
                   "limit": limit, "offset": offset},
        ))

    @mcp.tool()
    async def cad_list_mappings(project_id: str, limit: int = 20) -> str:
        """매핑 목록 (read-only)."""
        return _json(await call_cad_read(
            f"projects/{project_id}/mappings", query={"limit": limit}
        ))

    @mcp.tool()
    async def cad_list_quantity_rows(
        project_id: str,
        discipline: Optional[str] = None,
        item_group: Optional[str] = None,
        review_required: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """물량 행 목록 (read-only)."""
        return _json(await call_cad_read(
            f"projects/{project_id}/quantity/rows",
            query={"discipline": discipline, "item_group": item_group,
                   "review_required": review_required, "limit": limit, "offset": offset},
        ))

    @mcp.tool()
    async def cad_get_quantity_summary(project_id: str) -> str:
        """물량 요약 (read-only)."""
        return _json(await call_cad_read(f"projects/{project_id}/quantity/summary"))

    @mcp.tool()
    async def cad_list_exports(project_id: str, limit: int = 20) -> str:
        """익스포트 목록 (read-only)."""
        return _json(await call_cad_read(
            f"projects/{project_id}/exports", query={"limit": limit}
        ))

    @mcp.tool()
    async def cad_get_export(export_job_id: str) -> str:
        """익스포트 단건 조회 (read-only)."""
        return _json(await call_cad_read(f"exports/{export_job_id}"))

    @mcp.tool()
    async def cad_list_issues(
        project_id: str,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """이슈 목록 (read-only)."""
        return _json(await call_cad_read(
            f"projects/{project_id}/issues",
            query={"severity": severity, "status": status, "issue_type": issue_type,
                   "limit": limit, "offset": offset},
        ))

    @mcp.tool()
    async def cad_get_issues_summary(project_id: str) -> str:
        """이슈 요약 (read-only)."""
        return _json(await call_cad_read(f"projects/{project_id}/issues/summary"))

    @mcp.tool()
    async def cad_list_bridge_sessions(
        project_id: str,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """브리지 세션 목록 (read-only)."""
        return _json(await call_cad_read(
            f"bridge/projects/{project_id}/sessions",
            query={"status": status, "limit": limit},
        ))

    @mcp.tool()
    async def cad_get_bridge_session(session_id: str) -> str:
        """브리지 세션 조회 (read-only)."""
        return _json(await call_cad_read(f"bridge/sessions/{session_id}"))

    @mcp.tool()
    async def cad_get_bridge_batch(batch_id: str) -> str:
        """브리지 배치 조회 (read-only)."""
        return _json(await call_cad_read(f"bridge/batches/{batch_id}"))

    @mcp.tool()
    async def cad_get_bridge_batch_logs(batch_id: str) -> str:
        """브리지 배치 로그 (read-only)."""
        return _json(await call_cad_read(f"bridge/batches/{batch_id}/logs"))

    # download_export 는 바이너리 응답 — URL 만 반환
    @mcp.tool()
    async def cad_get_download_export_url(export_job_id: str) -> str:
        """익스포트 다운로드 URL 조회 (read-only, 바이너리 직접 반환 없음)."""
        return _json({"download_path": f"/api/v1/cad/exports/{export_job_id}/download",
                      "note": "Use orchestrator proxy with auth to download the file."})


# ═════════════════════════════════════════════════════════════════════
# WRITE 도구 (20개) — orchestrator 경유 필수
# 모든 write 도구는 actor / task_id / approval_token 이 필수다.
#
# 워크플로:
#   1. POST /api/v1/tasks  → task_id + approval_token_id 발급
#   2. POST /api/v1/tasks/{task_id}/approve  → admin/owner 승인
#   3. 이 도구 호출 시 task_id + approval_token_id + actor 제공
# ═════════════════════════════════════════════════════════════════════

if _MCP_AVAILABLE:
    # ── projects ──────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_create_project(
        name: str,
        description: str = "",
        trade_type: Optional[str] = None,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """프로젝트 생성 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                "projects", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body={"name": name, "description": description, "trade_type": trade_type},
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_update_project(
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """프로젝트 수정 (write — orchestrator + approval 필수)."""
        body = {k: v for k, v in {"name": name, "description": description}.items()
                if v is not None}
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body=body,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_delete_project(
        project_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """프로젝트 삭제 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}", "DELETE",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── drawings ──────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_update_drawing(
        drawing_id: str,
        discipline: Optional[str] = None,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """도면 메타 수정 (write — orchestrator + approval 필수)."""
        body = {k: v for k, v in {"discipline": discipline}.items() if v is not None}
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"drawings/{drawing_id}", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body=body,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_delete_drawing(
        drawing_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """도면 삭제 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"drawings/{drawing_id}", "DELETE",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── parse ─────────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_parse_drawing(
        drawing_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """단일 도면 파싱 시작 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"drawings/{drawing_id}/parse", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_start_parse_bulk(
        drawing_ids: list,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """다중 도면 파싱 일괄 시작 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                "parse/start", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body={"drawing_ids": drawing_ids},
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── mappings ──────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_create_mapping(
        project_id: str,
        entity_type: str,
        quantity_item: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """매핑 수동 생성 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}/mappings", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body={"entity_type": entity_type, "quantity_item": quantity_item},
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_auto_generate_mappings(
        project_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """매핑 자동 생성 트리거 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}/mappings/auto-generate", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_update_mapping(
        mapping_id: str,
        quantity_item: Optional[str] = None,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """매핑 수정 (write — orchestrator + approval 필수)."""
        body = {k: v for k, v in {"quantity_item": quantity_item}.items() if v is not None}
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"mappings/{mapping_id}", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body=body,
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── quantity ──────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_calculate_quantity(
        project_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """물량 계산 트리거 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}/quantity/calculate", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_confirm_quantity_row(
        row_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """물량 행 확인 처리 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"quantity/rows/{row_id}/confirm", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── exports ───────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_create_export(
        project_id: str,
        format: str = "xlsx",
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """익스포트 생성 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}/exports", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body={"format": format},
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── issues ────────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_update_issue(
        issue_id: str,
        status: Optional[str] = None,
        resolution: Optional[str] = None,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """이슈 상태/해결 수정 (write — orchestrator + approval 필수)."""
        body = {k: v for k, v in {"status": status, "resolution": resolution}.items()
                if v is not None}
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"issues/{issue_id}", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body=body,
            ))
        except McpWriteError as e:
            return _write_error(e)

    # ── bridge ────────────────────────────────────────────────────────

    @mcp.tool()
    async def cad_start_bridge_session(
        project_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """브리지 세션 시작 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                "bridge/sessions", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
                body={"project_id": project_id},
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_upload_bridge_batch(
        session_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """브리지 선택 배치 업로드 (write — orchestrator + approval 필수).

        실제 파일 데이터는 별도 채널로 전달 — 이 도구는 배치 레코드 생성만 수행.
        """
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"bridge/sessions/{session_id}/batches", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_close_bridge_session(
        session_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """브리지 세션 종료 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"bridge/sessions/{session_id}/close", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_bridge_heartbeat(
        session_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """브리지 세션 heartbeat (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"bridge/sessions/{session_id}/heartbeat", "PATCH",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    @mcp.tool()
    async def cad_trigger_bridge_batch_quantity(
        batch_id: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """브리지 배치 물량 산출 트리거 (write — orchestrator + approval 필수)."""
        try:
            return _json(await call_cad_write_via_orchestrator(
                f"bridge/batches/{batch_id}/quantity", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
            ))
        except McpWriteError as e:
            return _write_error(e)

    # upload_drawing 은 multipart — orchestrator 경유 필수 (별도 핸들링)
    @mcp.tool()
    async def cad_upload_drawing(
        project_id: str,
        file_path: str,
        actor: str = "",
        task_id: str = "",
        approval_token: str = "",
    ) -> str:
        """도면 파일 업로드 (write — orchestrator + approval 필수, 로컬 파일 필요).

        file_path: STORAGE_ROOT 내 파일 경로 (컨테이너 /storage 마운트 볼륨 기준)
        """
        import pathlib
        storage_root = pathlib.Path(
            __import__("mcp_server.config", fromlist=["STORAGE_ROOT"]).STORAGE_ROOT
        )
        abs_path = storage_root / pathlib.Path(file_path).name  # path traversal 차단
        if not abs_path.exists():
            return json.dumps({"error": "file_not_found",
                               "detail": f"{file_path} not in STORAGE_ROOT"})
        try:
            with open(abs_path, "rb") as f:
                file_bytes = f.read()
            return _json(await call_cad_write_via_orchestrator(
                f"projects/{project_id}/drawings/upload", "POST",
                actor=actor, task_id=task_id, approval_token=approval_token,
                files={"file": (abs_path.name, file_bytes, "application/octet-stream")},
            ))
        except McpWriteError as e:
            return _write_error(e)


# ── 서버 진입점 ──────────────────────────────────────────────────────

if not _MCP_AVAILABLE:
    async def cad_agent_health() -> str:
        """Check localhost CAD agent health without touching AutoCAD COM."""
        return cad_agent_health_json()

    async def cad_agent_connect(timeout_seconds: int = 20) -> str:
        """Start/connect localhost CAD agent to AutoCAD COM and keep it alive."""
        return cad_agent_connect_json(timeout_seconds)

    async def cad_agent_status() -> str:
        """Return persistent localhost CAD agent connection status."""
        return cad_agent_status_json()

    async def cad_agent_active_document(timeout_seconds: int = 10) -> str:
        """Return active document info through the persistent localhost CAD agent."""
        return cad_agent_active_document_json(timeout_seconds)

    async def cad_local_adapter_ping() -> str:
        """Local CAD adapter ping. Does not execute AutoCAD commands."""
        return cad_local_adapter_ping_json()

    async def cad_local_adapter_status() -> str:
        """Local CAD adapter/module status. Does not execute AutoCAD commands."""
        return cad_local_adapter_status_json()

    async def cad_local_autocad_ping(timeout_seconds: int = 10) -> str:
        """Local AutoCAD COM backend ping with timeout isolation."""
        return cad_local_autocad_ping_json(timeout_seconds)

    async def cad_local_bridge_health(timeout_seconds: int = 5) -> str:
        """End-to-end CAD bridge health without modifying drawings."""
        return cad_local_bridge_health_json(timeout_seconds)

    async def cad_local_adapter_execute(tool_id: str, args: Optional[dict] = None) -> str:
        """Execute a local CAD read-only tool; unsafe tools are blocked locally."""
        return cad_local_adapter_execute_json(tool_id, args or {})


if __name__ == "__main__":
    if not _MCP_AVAILABLE:
        raise SystemExit("mcp 패키지가 설치되지 않았습니다. pip install mcp")

    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in {"sse", "streamable-http"}:
        mcp.run(transport=transport)
    else:
        mcp.run()  # stdio (기본)
