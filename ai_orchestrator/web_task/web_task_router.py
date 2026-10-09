"""웹 작업 표준 실행 API.

엔드포인트:
  GET  /api/v1/web-tasks/registry          — 등록된 작업 목록 (admin/owner)
  POST /api/v1/web-tasks/run               — 작업 실행 요청 (admin/owner)
  GET  /api/v1/web-tasks/templates         — 템플릿 목록 (admin/owner)
  POST /api/v1/web-tasks/run-from-template — 템플릿 기반 실행 (admin/owner)

POST /run / /run-from-template 동작:
  dry_run=true  → adapter.fill_form(page=None, dry_run=True) 로 검증·summary 반환.
                  approval 생성 없음, submit 없음.
  dry_run=false → pending approval 생성 + 텔레그램 발송 + 즉시 반환.
                  (status: pending_approval, 승인 후 실행은 기존 게이트 처리)

보안:
  - admin/owner 만 실행 허용
  - 미등록 provider/action_type → 404
  - 미등록 template_id → 404
  - validate_params 실패 → 422 (FORM_FIELD_MISSING, missing_fields/invalid_fields 포함)
  - params 원문 audit log / API 응답 노출 금지 (safe 필드만 허용)
  - default_params 원문은 템플릿 조회 API 응답에 포함하지 않음 (default_param_keys 만)
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.sites.adapters.dev_reg_base import ErrorCode, validate_params
from ai_orchestrator.web_task.web_task_approval_service import create_web_task_pending_approval
from ai_orchestrator.web_task.web_task_registry import get_entry, list_entries
from ai_orchestrator.web_task.web_task_templates import get_template, list_templates, merge_params
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

web_task_router = APIRouter(prefix="/web-tasks", tags=["web-tasks"])

# audit log / 응답에 포함 가능한 params 필드 화이트리스트
_SAFE_PARAM_KEYS: frozenset[str] = frozenset(
    {
        "app_name",
        "company_name",
        "service_url",
        "redirect_uri",
        "contact_email",
        "purpose",
        "requested_scopes",
    }
)


class WebTaskRunRequest(BaseModel):
    provider: str
    action_type: str
    params: dict = {}
    dry_run: bool = False


class WebTaskRunFromTemplateRequest(BaseModel):
    template_id: str
    override_params: dict = {}
    dry_run: bool = False


# ── 검증 헬퍼 ────────────────────────────────────────────────────────────


def _classify_validation(params: dict) -> tuple[list[str], list[str], list[str]]:
    """validate_params() 결과를 missing/invalid 로 분류.

    반환: (errors, missing_fields, invalid_fields)
    """
    errors = validate_params(params)
    missing: list[str] = []
    invalid: list[str] = []
    if not str(params.get("app_name", "")).strip():
        missing.append("app_name")
    return errors, missing, invalid


def _raise_validation_error(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    action_type: str,
    provider: str,
    actor: str,
    role: str,
    errors: list[str],
    missing: list[str],
    invalid: list[str],
) -> None:
    log_event(
        "WEB_TASK_VALIDATION_FAILED",
        "web-task",
        action_type=action_type,
        actor=actor,
        role=role,
        note=f"provider={provider} missing={','.join(missing) or '-'}",
    )
    raise HTTPException(
        status_code=422,
        detail={
            "error": ErrorCode.FORM_FIELD_MISSING,
            "error_code": ErrorCode.FORM_FIELD_MISSING,
            "message": "; ".join(errors),
            "missing_fields": missing,
            "invalid_fields": invalid,
        },
    )


# ── 공통 실행 로직 ──────────────────────────────────────────────────────


def _execute_web_task(
    *,
    provider: str,
    action_type: str,
    params: dict,
    dry_run: bool,
    actor: str,
    role: str,
) -> dict:
    """provider/action_type/params 기반 표준 실행.

    /run 과 /run-from-template 가 공유하는 핵심 로직.
    레지스트리 조회 → params 검증 → dry_run 또는 pending approval 생성.
    """
    provider = provider.strip().lower()
    action_type = action_type.strip().lower()
    params = dict(params or {})

    # ── 1. 레지스트리 조회 ─────────────────────────────────────────────
    entry = get_entry(provider, action_type)
    if entry is None:
        log_event(
            "WEB_TASK_REJECTED_UNKNOWN_TASK",
            "web-task",
            action_type=action_type,
            actor=actor,
            role=role,
            note=f"provider={provider}",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "UNKNOWN_TASK", "message": f"미등록 작업: {provider}/{action_type}"},
        )

    # ── 2. params 공통 검증 ───────────────────────────────────────────
    errors, missing, invalid = _classify_validation(params)
    if errors:
        _raise_validation_error(
            action_type=action_type,
            provider=provider,
            actor=actor,
            role=role,
            errors=errors,
            missing=missing,
            invalid=invalid,
        )

    # ── 3a. dry_run 분기 ──────────────────────────────────────────────
    if dry_run:
        adapter = entry.adapter_class()
        fill_result = adapter.fill_form(None, {**params, "dry_run": True})

        log_event(
            "WEB_TASK_DRY_RUN_COMPLETED",
            "web-task",
            risk_level=entry.risk_level,
            action_type=action_type,
            actor=actor,
            role=role,
            note=f"provider={provider} success={fill_result.success}",
        )

        return {
            "dry_run": True,
            "provider": provider,
            "action_type": action_type,
            "risk_level": entry.risk_level,
            "requires_approval": entry.requires_approval,
            "success": fill_result.success,
            "summary": fill_result.summary,
            "field_names": fill_result.field_names,
            "target_url": fill_result.target_url,
            "error": fill_result.error,
            "error_code": fill_result.error_code,
        }

    # ── 3b. real_run: pending approval 생성 ──────────────────────────
    task_id = f"wt-{uuid.uuid4().hex[:12]}"

    # dry_run 으로 summary 생성 (page=None, DOM 조작 없음)
    adapter = entry.adapter_class()
    fill_result = adapter.fill_form(None, {**params, "dry_run": True})
    summary = fill_result.summary if fill_result.success else f"[summary 생성 실패] {fill_result.error}"

    log_event(
        "WEB_TASK_RUN_REQUESTED",
        task_id,
        risk_level=entry.risk_level,
        action_type=action_type,
        target=fill_result.target_url,
        actor=actor,
        role=role,
        note=f"provider={provider}",
    )

    # 승인 생성 조립 (token 발행 → pending 생성 → Telegram 발송 → mark)
    approval = create_web_task_pending_approval(
        task_id=task_id,
        provider=provider,
        action_type=action_type,
        risk_level=entry.risk_level,
        requires_approval=entry.requires_approval,
        summary=summary,
        target_url=fill_result.target_url,
        requested_by=actor,
        actor_role=role,
    )

    log_event(
        "WEB_TASK_PENDING_APPROVAL_CREATED",
        task_id,
        risk_level=entry.risk_level,
        action_type=action_type,
        target=fill_result.target_url,
        actor=actor,
        role=role,
        note=f"provider={provider}",
    )

    return {
        "dry_run": False,
        "status": "pending_approval",
        "task_id": task_id,
        "provider": provider,
        "action_type": action_type,
        "risk_level": entry.risk_level,
        "requires_approval": entry.requires_approval,
        "expires_at": approval.expires_at,
    }


# ── 라우트 ───────────────────────────────────────────────────────────────


@web_task_router.get("/registry")
def get_web_task_registry(
    user: dict = Depends(require_role("admin", "owner")),
):
    """등록된 웹 작업 목록 반환."""
    return {"tasks": list_entries()}


@web_task_router.post("/run")
def run_web_task(
    body: WebTaskRunRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """웹 작업 실행 요청 (provider/action_type 직접 지정)."""
    return _execute_web_task(
        provider=body.provider,
        action_type=body.action_type,
        params=body.params,
        dry_run=body.dry_run,
        actor=user["actor"],
        role=user["role"],
    )


@web_task_router.get("/templates")
def get_web_task_templates(
    user: dict = Depends(require_role("admin", "owner")),
):
    """등록된 템플릿 목록 반환.

    default_params 원문은 노출하지 않고 키 목록(default_param_keys) 만 반환한다.
    """
    return {"templates": list_templates()}


@web_task_router.post("/run-from-template")
def run_web_task_from_template(
    body: WebTaskRunFromTemplateRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """템플릿 기반 웹 작업 실행 요청.

    template_id 로 default_params 를 가져와 override_params 와 병합 후
    기존 /run 과 동일한 실행 경로(_execute_web_task)를 사용한다.
    """
    actor = user["actor"]
    role = user["role"]
    template_id = (body.template_id or "").strip()

    template = get_template(template_id)
    if template is None:
        log_event(
            "WEB_TASK_TEMPLATE_NOT_FOUND",
            "web-task",
            actor=actor,
            role=role,
            note=f"template_id={template_id or '-'}",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "TEMPLATE_NOT_FOUND", "message": f"미등록 템플릿: {template_id or '-'}"},
        )

    merged = merge_params(template, body.override_params or {})

    log_event(
        "WEB_TASK_TEMPLATE_USED",
        "web-task",
        action_type=template.action_type,
        actor=actor,
        role=role,
        note=(f"template_id={template.template_id} provider={template.provider} dry_run={body.dry_run}"),
    )

    result = _execute_web_task(
        provider=template.provider,
        action_type=template.action_type,
        params=merged,
        dry_run=body.dry_run,
        actor=actor,
        role=role,
    )
    # 응답에 template_id 만 추가 (override_params 원문 노출 금지)
    result["template_id"] = template.template_id
    return result
