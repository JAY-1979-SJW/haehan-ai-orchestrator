"""
Action Task API — 서버 외부 진입점.

역할:
  POST /api/actions/prepare  → prepare_action_task 호출, approval request 저장
  POST /api/actions/evidence → evidence safe field 저장

정책 판단(risk/approval/params_hash)은 action_task_handoff.prepare_action_task에 위임.
API 계층에서 직접 정책 구현 금지.

보안:
  - 서버에서 외부 URL 브라우저 실행 금지
  - raw params 저장 금지
  - 민감 필드 저장 금지
  - dry_run 기본 True
"""
from __future__ import annotations

from typing import Any

from ai_orchestrator.server.action_task_handoff import (
    VERDICT_APPROVAL_REQUIRED,
    VERDICT_HANDOFF_READY,
    prepare_action_task,
)
from ai_orchestrator.server.action_approval_audit_store import (
    STATUS_PENDING,
    save_approval_request,
    update_approval_status,
    get_approval_request,
    list_approval_requests,
)
from ai_orchestrator.server.action_evidence_store import (
    validate_evidence_fields,
    save_evidence,
    get_evidence,
    list_evidence,
)


# ── prepare ───────────────────────────────────────────────────────────────────

def api_prepare_action(
    *,
    action_name: str,
    params: dict[str, Any] | None = None,
    requested_by: str = "anonymous",
    user_intent_summary: str = "",
    site_context: str = "",
    target_context: str = "",
    approval_token: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    action 실행 준비 진입점.

    dry_run=True(기본)이면 handoff payload를 생성하지만 실제 실행하지 않는다.
    정책 판단은 prepare_action_task에 완전히 위임한다.

    approval request가 생성되면 approval_audit_store에도 저장한다.
    """
    result = prepare_action_task(
        action_name=action_name,
        params=params,
        requested_by=requested_by,
        approval_token=approval_token,
        user_intent_summary=user_intent_summary,
        site_context=site_context,
        target_context=target_context,
    )

    verdict = result.get("verdict")
    approval_request_id = result.get("approval_request_id")
    params_hash = result.get("params_hash", "")
    summary = result.get("summary") or {}

    # APPROVAL_REQUIRED인 경우 audit store에 기록
    if verdict == VERDICT_APPROVAL_REQUIRED and approval_request_id:
        try:
            save_approval_request(
                approval_request_id=approval_request_id,
                action_name=action_name,
                params_hash=params_hash,
                requested_by=requested_by,
                scope_safe={
                    "action_name": action_name,
                    "site_context": site_context,
                    "target_context": target_context,
                },
                summary_safe={
                    "user_intent_summary": user_intent_summary,
                    **{k: v for k, v in summary.items()
                       if isinstance(v, (str, int, float, bool, type(None)))},
                },
                status=STATUS_PENDING,
            )
        except Exception as e:
            result.setdefault("warnings", []).append(f"audit store 기록 실패: {e}")

    # HANDOFF_READY + approval_request_id 있으면 consumed 상태 기록
    if verdict == VERDICT_HANDOFF_READY and approval_request_id:
        try:
            update_approval_status(
                approval_request_id,
                status="APPROVED_AND_CONSUMED",
                verdict=verdict,
                consumed_at=None,
            )
        except Exception as e:
            result.setdefault("warnings", []).append(f"audit 소비 상태 기록 실패: {e}")

    result["dry_run"] = dry_run
    return result


# ── evidence ──────────────────────────────────────────────────────────────────

def api_receive_evidence(
    *,
    action_name: str,
    approval_request_id: str,
    params_hash: str,
    result_status: str,
    result_fields_safe: dict[str, Any] | None = None,
    evidence_files_ref: list[str] | None = None,
    local_agent_run_id: str = "",
    occurred_at: str = "",
) -> dict[str, Any]:
    """
    local agent 실행 결과(evidence)를 수신하고 safe field만 저장한다.

    금지 필드 포함 시 즉시 BLOCKED 반환.
    실제 파일 내용 저장 금지 — 경로 ref만 허용.
    """
    fields = dict(result_fields_safe or {})

    violations = validate_evidence_fields(fields)
    if violations:
        return {
            "accepted": False,
            "blocked_reason": violations,
            "evidence_id": None,
        }

    record = save_evidence(
        action_name=action_name,
        approval_request_id=approval_request_id,
        params_hash=params_hash,
        result_status=result_status,
        result_fields_safe=fields,
        evidence_files_ref=evidence_files_ref,
        local_agent_run_id=local_agent_run_id,
        occurred_at=occurred_at,
    )

    return {
        "accepted": True,
        "blocked_reason": None,
        "evidence_id": record["evidence_id"],
        "stored_at": record["stored_at"],
    }


# ── 조회 helpers ──────────────────────────────────────────────────────────────

def api_get_approval_request(approval_request_id: str) -> dict[str, Any] | None:
    return get_approval_request(approval_request_id)


def api_list_approval_requests(
    action_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_approval_requests(action_name=action_name, limit=limit)


def api_get_evidence(evidence_id: str) -> dict[str, Any] | None:
    return get_evidence(evidence_id)


def api_list_evidence(
    approval_request_id: str | None = None,
    action_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_evidence(
        approval_request_id=approval_request_id,
        action_name=action_name,
        limit=limit,
    )
