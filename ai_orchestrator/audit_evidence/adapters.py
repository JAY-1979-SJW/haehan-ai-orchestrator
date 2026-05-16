"""Audit/Evidence read-only adapter — 기존 구조 → 표준 모델 변환.

기존 audit_logger / task_state / approval / evidence_store를 대체하지 않는다.
read-only 변환만 수행한다. 원본 데이터 수정 금지. DB write 금지.

금지:
- 원본 dict 수정 금지
- 외부 호출 금지
- DB write 금지
- secret/token/password/session/cookie 노출 금지
"""
from __future__ import annotations

from typing import Any, Optional

from ai_orchestrator.audit_evidence.models import (
    ArtifactEvidenceRef,
    ExecutionAttempt,
    ExternalAppHandoff,
    SafetyVerdict,
    StandardAuditEvent,
)
from ai_orchestrator.safety_policy.secret_redaction import strip_sensitive_fields


def audit_event_dict_to_standard(raw: dict[str, Any]) -> StandardAuditEvent:
    """audit_logger event dict → StandardAuditEvent 변환."""
    safe = strip_sensitive_fields(raw)
    return StandardAuditEvent.create(
        event_type=safe.get("event_type", "unknown"),
        task_id=str(safe.get("task_id", "")),
        actor=str(safe.get("actor", safe.get("role", "system"))),
        status=str(safe.get("decision", safe.get("status", "unknown"))),
        summary=str(safe.get("note", safe.get("action_type", ""))),
        safety_verdict=safe.get("allowed"),
        artifact_refs=(),
        metadata={k: v for k, v in safe.items() if k not in {
            "event_type", "task_id", "actor", "role", "decision",
            "status", "note", "action_type", "allowed",
        }},
        redaction_applied=True,
    )


def task_state_to_execution_attempt(raw: dict[str, Any]) -> ExecutionAttempt:
    """task_state record → ExecutionAttempt 변환."""
    safe = strip_sensitive_fields(raw)
    state = safe.get("state", "unknown")
    loc = safe.get("execution_location", "unknown")
    return ExecutionAttempt.create(
        task_id=str(safe.get("task_id", "")),
        execution_location=loc,
        risk_level=str(safe.get("risk_level", "unknown")),
        status=state,
        policy_decision=str(safe.get("policy_decision", safe.get("reason", ""))),
        safe_to_execute_on_server=safe.get("safe_to_execute_on_server", False),
        finished_at=safe.get("updated_at"),
        error_code=safe.get("error_code"),
        error_message=safe.get("error") if isinstance(safe.get("error"), str) else None,
        artifact_refs=(),
    )


def policy_decision_to_safety_verdict(
    task_id: str,
    policy_id: str,
    decision_dict: dict[str, Any],
) -> SafetyVerdict:
    """policy decision dict → SafetyVerdict 변환."""
    safe = strip_sensitive_fields(decision_dict)
    blocked = bool(safe.get("is_blocked", False))
    decision_str = "block" if blocked else (
        "hold" if safe.get("is_external_app_hold") else "allow"
    )
    return SafetyVerdict.create(
        task_id=task_id,
        policy_id=policy_id,
        decision=decision_str,
        reason=str(safe.get("reason", "")),
        required_execution_location=str(safe.get("execution_location", "unknown")),
        requires_approval=bool(safe.get("requires_approval", False)),
        requires_user_direct=bool(safe.get("requires_user_direct", False)),
        requires_oauth_setup=bool(safe.get("requires_oauth_setup", False)),
        blocked=blocked,
    )


def evidence_dict_to_artifact_ref(raw: dict[str, Any]) -> ArtifactEvidenceRef:
    """evidence_store record → ArtifactEvidenceRef 변환."""
    safe = strip_sensitive_fields(raw)
    return ArtifactEvidenceRef.create(
        artifact_type=str(safe.get("action_name", "evidence")),
        content_type=str(safe.get("content_type", "application/json")),
        storage_ref=str(safe.get("evidence_files_ref", safe.get("evidence_id", ""))),
        safe_name=str(safe.get("result_status", safe.get("action_name", "evidence"))),
        source_task_id=str(safe.get("task_id", safe.get("approval_request_id", ""))),
        evidence_level="standard",
        redaction_applied=True,
    )


def build_external_app_handoff(
    task_id: str,
    bridge_id: str,
    app_type: str,
    handoff_mode: str,
    approval_required: bool,
    user_direct_required: bool,
    safety_policy_ids: tuple[str, ...] = (),
    auto_execute_allowed: bool = False,
) -> ExternalAppHandoff:
    """외부 앱 핸드오프 기록 생성 (실제 실행 없음)."""
    return ExternalAppHandoff.create(
        task_id=task_id,
        bridge_id=bridge_id,
        app_type=app_type,
        handoff_mode=handoff_mode,
        status="handoff_recorded",
        approval_required=approval_required,
        user_direct_required=user_direct_required,
        safety_policy_ids=safety_policy_ids,
        auto_execute_allowed=auto_execute_allowed,
    )
