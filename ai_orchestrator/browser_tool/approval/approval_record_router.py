"""Browser Approval Record HTTP API Router.

FastAPI router for approval request/decision endpoints using approval_record_store.
Provides REST API for browser workflow approval management.
Test-only implementation (no DB write, JSONL-based append-only storage).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.browser_tool.approval.approval_record_store import (
    ApprovalTransitionError,
    append_approval_record,
    append_decision_if_pending,
    build_approval_decision,
    build_approval_request,
    get_latest_approval_status,
    read_approval_records,
)
from ai_orchestrator.browser_tool.approval.approval_record_store import (
    get_approval_history as get_approval_history_records,
)
from ai_orchestrator.core import config
from ai_orchestrator.core.config import APPROVAL_RECORD_STORE_PATH
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

approval_record_router = APIRouter(
    prefix="/browser-approvals",
    tags=["browser-approvals"],
)


# ── Request Models ────────────────────────────────────────────────────


class ApprovalRequestCreate(BaseModel):
    """Create approval request."""

    workflow_run_id: str
    workflow_id: str
    action_name: str
    operation_type: str
    approval_scope: str = ""
    requested_by: str
    requested_role: str
    tenant_id: str = ""
    user_id: str = ""
    site_id: str = ""
    target_domain: str = ""
    target_url: str = ""
    request_reason: str = ""
    expires_in_hours: int = 24


class ApprovalDecisionCreate(BaseModel):
    """Create approval decision (GRANTED, REJECTED, EXPIRED, REVOKED)."""

    decided_by: str
    decided_role: str
    decision_reason: str = ""
    approval_event_type: str | None = None  # Inferred from endpoint, optional in request


# ── Response Models ───────────────────────────────────────────────────


class ApprovalRecordResponse(BaseModel):
    """Approval record response (public contract)."""

    approval_event_id: str
    approval_id: str
    workflow_run_id: str
    approval_status: str  # PENDING, APPROVED, REJECTED, EXPIRED, REVOKED
    approval_event_type: str
    created_at: str
    target_url_redacted: str
    target_url_hash: str
    safe_to_execute: bool = False  # Always false
    approval_required: bool
    decided_by: str | None = None
    decision_reason: str | None = None
    expires_at: str | None = None


class ApprovalListResponse(BaseModel):
    """List of approval records."""

    ok: bool
    approvals: list[ApprovalRecordResponse]
    count: int
    error: str | None = None


class ApprovalHistoryResponse(BaseModel):
    """Approval history for a specific approval_id."""

    ok: bool
    approval_id: str
    events: list[dict]
    count: int
    error: str | None = None


# ── Helper Functions ──────────────────────────────────────────────────


def _to_approval_response(record: dict) -> ApprovalRecordResponse:
    """Convert approval record dict to response model."""
    return ApprovalRecordResponse(
        approval_event_id=record.get("approval_event_id", ""),
        approval_id=record.get("approval_id", ""),
        workflow_run_id=record.get("workflow_run_id", ""),
        approval_status=record.get("approval_status", ""),
        approval_event_type=record.get("approval_event_type", ""),
        created_at=record.get("created_at", ""),
        target_url_redacted=record.get("target_url_redacted", ""),
        target_url_hash=record.get("target_url_hash", ""),
        safe_to_execute=False,  # Policy: always false
        approval_required=record.get("approval_required", True),
        decided_by=record.get("decided_by"),
        decision_reason=record.get("decision_reason"),
        expires_at=record.get("expires_at"),
    )


# ── API Endpoints ─────────────────────────────────────────────────────


@approval_record_router.get("/requests", response_model=ApprovalListResponse)
def list_approvals(
    status: str | None = None,
    approval_id: str | None = None,
    _user: dict = Depends(require_role("admin", "owner")),
) -> ApprovalListResponse:
    """List approval requests.

    Query params:
      - status: Filter by approval_status (PENDING, APPROVED, REJECTED, EXPIRED, REVOKED)
      - approval_id: Filter by approval_id
    """
    try:
        records = read_approval_records(APPROVAL_RECORD_STORE_PATH)
    except FileNotFoundError:
        return ApprovalListResponse(
            ok=True,
            approvals=[],
            count=0,
        )
    except Exception as e:  # noqa: BLE001 - 승인요청 생성/승인/거부/이력조회 API - approve/reject 처리 중 예외 발생시 승인 상태를 반환하지 않고 HTTPException 500 을 raise 함(fail-loud), 조회 계열만 ok:False 로 폴백
        logger.error("Failed to read approval records: %s", e)
        return ApprovalListResponse(
            ok=False,
            approvals=[],
            count=0,
            error=f"Failed to read approval records: {e!s}",
        )

    # Filter to latest status per approval_id
    latest_by_id: dict[str, dict] = {}
    for record in records:
        aid = record.get("approval_id", "")
        if aid and (aid not in latest_by_id or record.get("created_at", "") >= latest_by_id[aid].get("created_at", "")):
            latest_by_id[aid] = record

    # Apply filters
    filtered = []
    for record in latest_by_id.values():
        if status and record.get("approval_status") != status:
            continue
        if approval_id and record.get("approval_id") != approval_id:
            continue
        filtered.append(record)

    approvals = [_to_approval_response(r) for r in filtered]
    return ApprovalListResponse(
        ok=True,
        approvals=approvals,
        count=len(approvals),
    )


@approval_record_router.get("/requests/{approval_id}", response_model=ApprovalRecordResponse)
def get_approval(
    approval_id: str,
    _user: dict = Depends(require_role("admin", "owner")),
) -> ApprovalRecordResponse:
    """Get approval request by approval_id."""
    try:
        latest = get_latest_approval_status(approval_id, APPROVAL_RECORD_STORE_PATH)
        if not latest:
            raise HTTPException(status_code=404, detail="Approval not found")
        return _to_approval_response(latest)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get approval: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@approval_record_router.post("/requests", response_model=ApprovalRecordResponse)
def create_approval(
    req: ApprovalRequestCreate,
    _user: dict = Depends(require_role("admin", "owner")),
) -> ApprovalRecordResponse:
    """Create approval request."""
    try:
        actor = _user.get("actor", req.requested_by) if config.AUTH_ENABLED else req.requested_by
        role = _user.get("role", req.requested_role) if config.AUTH_ENABLED else req.requested_role
        approval_record = build_approval_request(
            workflow_run_id=req.workflow_run_id,
            workflow_id=req.workflow_id,
            action_name=req.action_name,
            operation_type=req.operation_type,
            approval_scope=req.approval_scope,
            requested_by=actor,
            requested_role=role,
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            site_id=req.site_id,
            target_domain=req.target_domain,
            target_url=req.target_url,
            request_reason=req.request_reason,
            expires_in_hours=req.expires_in_hours,
        )

        result = append_approval_record(approval_record, APPROVAL_RECORD_STORE_PATH)
        if not result.success:
            logger.error("Failed to append approval record: %s", result.error_message)
            raise HTTPException(status_code=400, detail=result.error_message or "Failed to create approval")

        # Return the created record
        record_dict = {
            "approval_event_id": approval_record.approval_event_id,
            "approval_id": approval_record.approval_id,
            "workflow_run_id": approval_record.workflow_run_id,
            "approval_status": approval_record.approval_status,
            "approval_event_type": approval_record.approval_event_type,
            "created_at": approval_record.created_at,
            "target_url_redacted": approval_record.target_url_redacted,
            "target_url_hash": approval_record.target_url_hash,
            "approval_required": approval_record.approval_required,
            "decided_by": None,
            "decision_reason": None,
            "expires_at": approval_record.expires_at,
        }
        return _to_approval_response(record_dict)

    except Exception as e:
        logger.error("Failed to create approval: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@approval_record_router.post("/requests/{approval_id}/approve", response_model=ApprovalRecordResponse)
def approve_request(
    approval_id: str,
    req: ApprovalDecisionCreate,
    _user: dict = Depends(require_role("admin", "owner")),
) -> ApprovalRecordResponse:
    """Grant approval for a request."""
    try:
        actor = _user.get("actor", req.decided_by) if config.AUTH_ENABLED else req.decided_by
        role = _user.get("role", req.decided_role) if config.AUTH_ENABLED else req.decided_role
        # Set event type to APPROVAL_GRANTED (endpoint implies this)
        event_type = "APPROVAL_GRANTED"

        decision_record = build_approval_decision(
            approval_id=approval_id,
            approval_event_type=event_type,
            decided_by=actor,
            decided_role=role,
            decision_reason=req.decision_reason,
        )

        try:
            result = append_decision_if_pending(decision_record, APPROVAL_RECORD_STORE_PATH)
        except ApprovalTransitionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if not result.success:
            logger.error("Failed to append approval decision: %s", result.error_message)
            raise HTTPException(status_code=400, detail=result.error_message or "Failed to approve")

        # Return the decision record
        record_dict = {
            "approval_event_id": decision_record.approval_event_id,
            "approval_id": decision_record.approval_id,
            "workflow_run_id": decision_record.workflow_run_id,
            "approval_status": decision_record.approval_status,
            "approval_event_type": decision_record.approval_event_type,
            "created_at": decision_record.created_at,
            "target_url_redacted": decision_record.target_url_redacted,
            "target_url_hash": decision_record.target_url_hash,
            "approval_required": decision_record.approval_required,
            "decided_by": decision_record.decided_by,
            "decision_reason": decision_record.decision_reason,
            "expires_at": decision_record.expires_at,
        }
        return _to_approval_response(record_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to approve request: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@approval_record_router.post("/requests/{approval_id}/reject", response_model=ApprovalRecordResponse)
def reject_request(
    approval_id: str,
    req: ApprovalDecisionCreate,
    _user: dict = Depends(require_role("admin", "owner")),
) -> ApprovalRecordResponse:
    """Reject approval for a request."""
    try:
        actor = _user.get("actor", req.decided_by) if config.AUTH_ENABLED else req.decided_by
        role = _user.get("role", req.decided_role) if config.AUTH_ENABLED else req.decided_role
        # Set event type to APPROVAL_REJECTED (endpoint implies this)
        event_type = "APPROVAL_REJECTED"

        decision_record = build_approval_decision(
            approval_id=approval_id,
            approval_event_type=event_type,
            decided_by=actor,
            decided_role=role,
            decision_reason=req.decision_reason,
        )

        try:
            result = append_decision_if_pending(decision_record, APPROVAL_RECORD_STORE_PATH)
        except ApprovalTransitionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if not result.success:
            logger.error("Failed to append approval decision: %s", result.error_message)
            raise HTTPException(status_code=400, detail=result.error_message or "Failed to reject")

        # Return the decision record
        record_dict = {
            "approval_event_id": decision_record.approval_event_id,
            "approval_id": decision_record.approval_id,
            "workflow_run_id": decision_record.workflow_run_id,
            "approval_status": decision_record.approval_status,
            "approval_event_type": decision_record.approval_event_type,
            "created_at": decision_record.created_at,
            "target_url_redacted": decision_record.target_url_redacted,
            "target_url_hash": decision_record.target_url_hash,
            "approval_required": decision_record.approval_required,
            "decided_by": decision_record.decided_by,
            "decision_reason": decision_record.decision_reason,
            "expires_at": decision_record.expires_at,
        }
        return _to_approval_response(record_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to reject request: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@approval_record_router.get("/requests/{approval_id}/history", response_model=ApprovalHistoryResponse)
def get_approval_history_endpoint(
    approval_id: str,
    _user: dict = Depends(require_role("admin", "owner")),
) -> ApprovalHistoryResponse:
    """Get approval event history for a specific approval_id."""
    try:
        events = get_approval_history_records(approval_id, APPROVAL_RECORD_STORE_PATH)
        return ApprovalHistoryResponse(
            ok=True,
            approval_id=approval_id,
            events=events,
            count=len(events),
        )
    except FileNotFoundError:
        return ApprovalHistoryResponse(
            ok=True,
            approval_id=approval_id,
            events=[],
            count=0,
        )
    except Exception as e:  # noqa: BLE001 - 승인요청 생성/승인/거부/이력조회 API - approve/reject 처리 중 예외 발생시 승인 상태를 반환하지 않고 HTTPException 500 을 raise 함(fail-loud), 조회 계열만 ok:False 로 폴백
        logger.error("Failed to get approval history: %s", e)
        return ApprovalHistoryResponse(
            ok=False,
            approval_id=approval_id,
            events=[],
            count=0,
            error=str(e),
        )
