"""CAD API action 스펙 테이블 (pure data, 외부 의존 없음).

cad-backend(cad-quantity FastAPI) 의 ``/api/v1/*`` 엔드포인트 42개를
로컬 agent 의 task action 으로 매핑한다. ``action_registry`` 는 메타
데이터 등록에, ``task_executor`` 는 httpx 기반 프록시 호출 생성에
이 테이블을 공용으로 소비한다.

제외 엔드포인트:
- GET /health, GET /health/detail, GET /version — root-level 이라
  orchestrator 의 cad_proxy(/api/v1/cad/* 전용) 로 닿지 않음. 시스템
  상태 점검은 orchestrator 자체의 /api/v1/health 로 갈음.

포맷:
    CadApiAction(
        action,          # 로컬 action 이름 (예: "cad.list_projects")
        method,          # HTTP method (GET/POST/PATCH/DELETE)
        path_template,   # cad_proxy 뒤 상대 경로 (예: "projects/{project_id}")
        path_params,     # 템플릿에 채워질 task 키들 (tuple of str)
        body_kind,       # None | "json" | "multipart" (upload 전용)
        query_keys,      # task 에서 꺼내 query string 으로 전달할 키들
        risk_level,      # "low"(읽기) | "medium"(쓰기)
        read_only,       # True 면 approval 불필요
        requires_file_path,  # True 면 AGENT_WORK_DIR 안 file_path 필수 (upload 전용)
        requires_save_as,    # True 면 AGENT_OUTPUT_DIR 안 save_as 필수 (없음)
        summary,         # 사람이 읽는 1줄 요약
    )

``risk_level`` / ``read_only`` 규칙:
- GET → low / read_only=True → approval 불필요
- POST/PATCH/DELETE → medium / read_only=False → approval_token 필수
- 기존 policy 기준 그대로 (정책 완화·강화 없음).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class CadApiAction:
    action: str
    method: str
    path_template: str
    path_params: Tuple[str, ...]
    body_kind: Optional[str]          # None | "json" | "multipart"
    query_keys: Tuple[str, ...]
    risk_level: str                   # "low" | "medium"
    read_only: bool
    requires_file_path: bool
    requires_save_as: bool
    summary: str


def _ro(action, method, path, path_params=(), query=(), summary=""):
    """읽기 액션 — GET 전용, approval 불필요."""
    return CadApiAction(
        action=action, method="GET", path_template=path,
        path_params=path_params, body_kind=None, query_keys=query,
        risk_level="low", read_only=True,
        requires_file_path=False, requires_save_as=False,
        summary=summary,
    )


def _wr(action, method, path, path_params=(), body="json", query=(), summary=""):
    """쓰기 액션 — POST/PATCH/DELETE, approval_token 필수(medium).

    save_as/file_path 요구는 기본 False — CAD API write 는 서버 리소스에
    대한 조작이라 로컬 파일 경로가 필요 없다. 특수 경우(upload_drawing
    등) 만 override.
    """
    assert method in ("POST", "PATCH", "DELETE"), method
    return CadApiAction(
        action=action, method=method, path_template=path,
        path_params=path_params, body_kind=body, query_keys=query,
        risk_level="medium", read_only=False,
        requires_file_path=False, requires_save_as=False,
        summary=summary,
    )


# ═════════════════════════════════════════════════════════════════════
# 42개 CAD API action 스펙
# path_template 는 cad_proxy prefix(/api/v1/cad/) **뒤** 경로.
# orchestrator cad_proxy 는 이를 cad-backend 의 /api/v1/<path> 로 중계.
# ═════════════════════════════════════════════════════════════════════

CAD_API_ACTIONS: Tuple[CadApiAction, ...] = (
    # ── projects ─────────────────────────────────────────────────
    _ro("cad.list_projects", "GET", "projects",
        query=("status", "trade_type", "limit", "offset"),
        summary="프로젝트 목록 조회"),
    _wr("cad.create_project", "POST", "projects",
        summary="프로젝트 생성"),
    _ro("cad.get_project", "GET", "projects/{project_id}",
        path_params=("project_id",),
        summary="프로젝트 단건 조회"),
    _wr("cad.update_project", "PATCH", "projects/{project_id}",
        path_params=("project_id",),
        summary="프로젝트 수정"),
    _wr("cad.delete_project", "DELETE", "projects/{project_id}",
        path_params=("project_id",), body=None,
        summary="프로젝트 삭제"),

    # ── drawings (project-scoped) ────────────────────────────────
    _ro("cad.list_drawings", "GET", "projects/{project_id}/drawings",
        path_params=("project_id",),
        query=("discipline", "parse_status", "limit"),
        summary="프로젝트 도면 목록"),
    # upload 는 multipart + 로컬 파일 필요 — 특수 handler 사용
    CadApiAction(
        action="cad.upload_drawing",
        method="POST",
        path_template="projects/{project_id}/drawings/upload",
        path_params=("project_id",),
        body_kind="multipart",
        query_keys=(),
        risk_level="medium",
        read_only=False,
        requires_file_path=True,      # 로컬 파일에서 업로드
        requires_save_as=False,
        summary="도면 파일 업로드 (multipart, 로컬 파일 필요)",
    ),
    _ro("cad.get_drawing", "GET", "drawings/{drawing_id}",
        path_params=("drawing_id",),
        summary="도면 단건 조회"),
    _wr("cad.update_drawing", "PATCH", "drawings/{drawing_id}",
        path_params=("drawing_id",),
        summary="도면 메타 수정"),
    _wr("cad.delete_drawing", "DELETE", "drawings/{drawing_id}",
        path_params=("drawing_id",), body=None,
        summary="도면 삭제"),

    # ── parse ────────────────────────────────────────────────────
    _wr("cad.parse_drawing", "POST", "drawings/{drawing_id}/parse",
        path_params=("drawing_id",), body=None,
        summary="단일 도면 파싱 시작"),
    _ro("cad.list_drawing_parse_jobs", "GET",
        "drawings/{drawing_id}/parse-jobs",
        path_params=("drawing_id",), query=("limit",),
        summary="도면의 파싱 작업 이력"),
    _ro("cad.get_drawing_parse_status", "GET",
        "drawings/{drawing_id}/parse/status",
        path_params=("drawing_id",),
        summary="도면 파싱 상태"),
    _wr("cad.start_parse_bulk", "POST", "parse/start",
        summary="다중 도면 파싱 일괄 시작"),
    _ro("cad.get_parse_job", "GET", "parse/jobs/{job_id}",
        path_params=("job_id",),
        summary="파싱 작업 단건 조회"),
    _ro("cad.get_parse_logs", "GET", "parse/jobs/{job_id}/logs",
        path_params=("job_id",),
        summary="파싱 작업 로그"),
    _ro("cad.get_project_parse_status", "GET",
        "projects/{project_id}/parse/status",
        path_params=("project_id",),
        summary="프로젝트 전체 파싱 상태"),
    _ro("cad.list_parsed_entities", "GET",
        "projects/{project_id}/parsed-entities",
        path_params=("project_id",),
        query=("drawing_id", "entity_type", "limit", "offset"),
        summary="파싱된 엔터티 목록"),

    # ── mappings ─────────────────────────────────────────────────
    _ro("cad.list_mappings", "GET", "projects/{project_id}/mappings",
        path_params=("project_id",), query=("limit",),
        summary="매핑 목록"),
    _wr("cad.create_mapping", "POST", "projects/{project_id}/mappings",
        path_params=("project_id",),
        summary="매핑 수동 생성"),
    _wr("cad.auto_generate_mappings", "POST",
        "projects/{project_id}/mappings/auto-generate",
        path_params=("project_id",), body=None,
        summary="매핑 자동 생성 트리거"),
    _wr("cad.update_mapping", "PATCH", "mappings/{mapping_id}",
        path_params=("mapping_id",),
        summary="매핑 수정"),

    # ── quantity ─────────────────────────────────────────────────
    _wr("cad.calculate_quantity", "POST",
        "projects/{project_id}/quantity/calculate",
        path_params=("project_id",),
        summary="물량 계산 트리거"),
    _ro("cad.list_quantity_rows", "GET",
        "projects/{project_id}/quantity/rows",
        path_params=("project_id",),
        query=("discipline", "item_group", "review_required",
               "limit", "offset"),
        summary="물량 행 목록"),
    _ro("cad.get_quantity_summary", "GET",
        "projects/{project_id}/quantity/summary",
        path_params=("project_id",),
        summary="물량 요약"),
    _wr("cad.confirm_quantity_row", "PATCH",
        "quantity/rows/{row_id}/confirm",
        path_params=("row_id",),
        summary="물량 행 확인 처리"),

    # ── exports ──────────────────────────────────────────────────
    _ro("cad.list_exports", "GET", "projects/{project_id}/exports",
        path_params=("project_id",), query=("limit",),
        summary="익스포트 목록"),
    _wr("cad.create_export", "POST", "projects/{project_id}/exports",
        path_params=("project_id",),
        summary="익스포트 생성"),
    _ro("cad.get_export", "GET", "exports/{export_job_id}",
        path_params=("export_job_id",),
        summary="익스포트 단건 조회"),
    _ro("cad.download_export", "GET",
        "exports/{export_job_id}/download",
        path_params=("export_job_id",),
        summary="익스포트 다운로드 (바이너리 응답)"),

    # ── issues ───────────────────────────────────────────────────
    _ro("cad.list_issues", "GET", "projects/{project_id}/issues",
        path_params=("project_id",),
        query=("severity", "status", "issue_type", "limit", "offset"),
        summary="이슈 목록"),
    _ro("cad.get_issues_summary", "GET",
        "projects/{project_id}/issues/summary",
        path_params=("project_id",),
        summary="이슈 요약"),
    _wr("cad.update_issue", "PATCH", "issues/{issue_id}",
        path_params=("issue_id",),
        summary="이슈 상태/해결 수정"),

    # ── bridge (PC 브리지 프로토콜) ───────────────────────────────
    _ro("cad.list_bridge_sessions", "GET",
        "bridge/projects/{project_id}/sessions",
        path_params=("project_id",), query=("status", "limit"),
        summary="브리지 세션 목록"),
    _wr("cad.start_bridge_session", "POST", "bridge/sessions",
        summary="브리지 세션 시작"),
    _ro("cad.get_bridge_session", "GET", "bridge/sessions/{session_id}",
        path_params=("session_id",),
        summary="브리지 세션 조회"),
    _wr("cad.upload_bridge_batch", "POST",
        "bridge/sessions/{session_id}/batches",
        path_params=("session_id",),
        summary="브리지 선택 배치 업로드"),
    _wr("cad.close_bridge_session", "PATCH",
        "bridge/sessions/{session_id}/close",
        path_params=("session_id",), body=None,
        summary="브리지 세션 종료"),
    _wr("cad.bridge_heartbeat", "PATCH",
        "bridge/sessions/{session_id}/heartbeat",
        path_params=("session_id",),
        summary="브리지 세션 heartbeat"),
    _ro("cad.get_bridge_batch", "GET", "bridge/batches/{batch_id}",
        path_params=("batch_id",),
        summary="브리지 배치 조회"),
    _ro("cad.get_bridge_batch_logs", "GET",
        "bridge/batches/{batch_id}/logs",
        path_params=("batch_id",),
        summary="브리지 배치 로그"),
    _wr("cad.trigger_bridge_batch_quantity", "POST",
        "bridge/batches/{batch_id}/quantity",
        path_params=("batch_id",), body=None,
        summary="브리지 배치 물량 산출 트리거"),
)


def action_names() -> Tuple[str, ...]:
    return tuple(a.action for a in CAD_API_ACTIONS)


def get_spec(action: str) -> Optional[CadApiAction]:
    for a in CAD_API_ACTIONS:
        if a.action == action:
            return a
    return None


__all__ = [
    "CadApiAction",
    "CAD_API_ACTIONS",
    "action_names",
    "get_spec",
]
