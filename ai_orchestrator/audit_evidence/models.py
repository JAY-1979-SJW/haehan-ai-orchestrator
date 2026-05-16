"""Audit/Evidence 표준 계약 모델.

기존 audit_logger / task_state / approval / evidence_store를 대체하지 않는다.
표준 필드 계약만 정의하며, to_safe_dict()로 secret redaction을 적용한다.

금지:
- 실제 DB 연결 금지
- 외부 API 호출 금지
- secret/token/password/session/cookie 필드 정의 금지
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from ai_orchestrator.safety_policy.secret_redaction import (
    strip_sensitive_fields,
    assert_no_sensitive_fields,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class AuditEventStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    HELD = "held"
    FAILED = "failed"


class ExecutionLocation(str, Enum):
    SERVER = "server"
    LOCAL_AGENT = "local_agent"
    USER_DIRECT = "user_direct"
    EXTERNAL_APP = "external_app"
    UNKNOWN = "unknown"


class HandoffMode(str, Enum):
    FILE_DROP = "file_drop"
    IPC = "ipc"
    API_BRIDGE = "api_bridge"
    USER_MANUAL = "user_manual"


class EvidenceLevel(str, Enum):
    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    FULL = "full"


@dataclass(frozen=True)
class StandardAuditEvent:
    """표준 감사 이벤트 — 11개 필드 계약."""

    event_id: str
    event_type: str
    task_id: str
    actor: str
    status: str
    timestamp: str
    summary: str
    safety_verdict: Optional[str]
    artifact_refs: tuple[str, ...]
    metadata: dict[str, Any]
    redaction_applied: bool

    @classmethod
    def create(
        cls,
        event_type: str,
        task_id: str,
        actor: str,
        status: str,
        summary: str,
        safety_verdict: Optional[str] = None,
        artifact_refs: tuple[str, ...] = (),
        metadata: Optional[dict[str, Any]] = None,
        redaction_applied: bool = True,
    ) -> "StandardAuditEvent":
        return cls(
            event_id=_new_id("ae_"),
            event_type=event_type,
            task_id=task_id,
            actor=actor,
            status=status,
            timestamp=_now_iso(),
            summary=summary,
            safety_verdict=safety_verdict,
            artifact_refs=artifact_refs,
            metadata=metadata or {},
            redaction_applied=redaction_applied,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        raw = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "actor": self.actor,
            "status": self.status,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "safety_verdict": self.safety_verdict,
            "artifact_refs": list(self.artifact_refs),
            "metadata": strip_sensitive_fields(self.metadata),
            "redaction_applied": self.redaction_applied,
        }
        return strip_sensitive_fields(raw)


@dataclass(frozen=True)
class ExecutionAttempt:
    """실행 시도 기록 — 실행 위치/정책판정/결과 계약."""

    attempt_id: str
    task_id: str
    execution_location: str
    risk_level: str
    started_at: str
    finished_at: Optional[str]
    status: str
    policy_decision: str
    safe_to_execute_on_server: bool
    error_code: Optional[str]
    error_message: Optional[str]
    artifact_refs: tuple[str, ...]

    @classmethod
    def create(
        cls,
        task_id: str,
        execution_location: str,
        risk_level: str,
        status: str,
        policy_decision: str,
        safe_to_execute_on_server: bool,
        finished_at: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        artifact_refs: tuple[str, ...] = (),
    ) -> "ExecutionAttempt":
        return cls(
            attempt_id=_new_id("ea_"),
            task_id=task_id,
            execution_location=execution_location,
            risk_level=risk_level,
            started_at=_now_iso(),
            finished_at=finished_at,
            status=status,
            policy_decision=policy_decision,
            safe_to_execute_on_server=safe_to_execute_on_server,
            error_code=error_code,
            error_message=error_message,
            artifact_refs=artifact_refs,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        raw = {
            "attempt_id": self.attempt_id,
            "task_id": self.task_id,
            "execution_location": self.execution_location,
            "risk_level": self.risk_level,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "policy_decision": self.policy_decision,
            "safe_to_execute_on_server": self.safe_to_execute_on_server,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "artifact_refs": list(self.artifact_refs),
        }
        return strip_sensitive_fields(raw)


@dataclass(frozen=True)
class SafetyVerdict:
    """안전 판정 — block/hold/user_direct/oauth_required 계약."""

    verdict_id: str
    task_id: str
    policy_id: str
    decision: str
    reason: str
    required_execution_location: str
    requires_approval: bool
    requires_user_direct: bool
    requires_oauth_setup: bool
    blocked: bool
    checked_at: str

    @classmethod
    def create(
        cls,
        task_id: str,
        policy_id: str,
        decision: str,
        reason: str,
        required_execution_location: str,
        requires_approval: bool = False,
        requires_user_direct: bool = False,
        requires_oauth_setup: bool = False,
        blocked: bool = False,
    ) -> "SafetyVerdict":
        return cls(
            verdict_id=_new_id("sv_"),
            task_id=task_id,
            policy_id=policy_id,
            decision=decision,
            reason=reason,
            required_execution_location=required_execution_location,
            requires_approval=requires_approval,
            requires_user_direct=requires_user_direct,
            requires_oauth_setup=requires_oauth_setup,
            blocked=blocked,
            checked_at=_now_iso(),
        )

    def to_safe_dict(self) -> dict[str, Any]:
        raw = {
            "verdict_id": self.verdict_id,
            "task_id": self.task_id,
            "policy_id": self.policy_id,
            "decision": self.decision,
            "reason": self.reason,
            "required_execution_location": self.required_execution_location,
            "requires_approval": self.requires_approval,
            "requires_user_direct": self.requires_user_direct,
            "requires_oauth_setup": self.requires_oauth_setup,
            "blocked": self.blocked,
            "checked_at": self.checked_at,
        }
        return strip_sensitive_fields(raw)


@dataclass(frozen=True)
class ExternalAppHandoff:
    """외부 앱 핸드오프 기록 — CAD/HWPX/Excel/Tax/Bid 계약."""

    handoff_id: str
    task_id: str
    bridge_id: str
    app_type: str
    handoff_mode: str
    status: str
    requested_at: str
    completed_at: Optional[str]
    input_artifact_refs: tuple[str, ...]
    output_artifact_refs: tuple[str, ...]
    approval_required: bool
    user_direct_required: bool
    safety_policy_ids: tuple[str, ...]
    auto_execute_allowed: bool

    @classmethod
    def create(
        cls,
        task_id: str,
        bridge_id: str,
        app_type: str,
        handoff_mode: str,
        status: str,
        approval_required: bool,
        user_direct_required: bool,
        safety_policy_ids: tuple[str, ...] = (),
        input_artifact_refs: tuple[str, ...] = (),
        output_artifact_refs: tuple[str, ...] = (),
        completed_at: Optional[str] = None,
        auto_execute_allowed: bool = False,
    ) -> "ExternalAppHandoff":
        return cls(
            handoff_id=_new_id("hf_"),
            task_id=task_id,
            bridge_id=bridge_id,
            app_type=app_type,
            handoff_mode=handoff_mode,
            status=status,
            requested_at=_now_iso(),
            completed_at=completed_at,
            input_artifact_refs=input_artifact_refs,
            output_artifact_refs=output_artifact_refs,
            approval_required=approval_required,
            user_direct_required=user_direct_required,
            safety_policy_ids=safety_policy_ids,
            auto_execute_allowed=auto_execute_allowed,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        raw = {
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "bridge_id": self.bridge_id,
            "app_type": self.app_type,
            "handoff_mode": self.handoff_mode,
            "status": self.status,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "input_artifact_refs": list(self.input_artifact_refs),
            "output_artifact_refs": list(self.output_artifact_refs),
            "approval_required": self.approval_required,
            "user_direct_required": self.user_direct_required,
            "safety_policy_ids": list(self.safety_policy_ids),
            "auto_execute_allowed": self.auto_execute_allowed,
        }
        return strip_sensitive_fields(raw)


@dataclass(frozen=True)
class ArtifactEvidenceRef:
    """아티팩트/증거 참조 — 바이너리 원문 미포함, 경로 참조만."""

    artifact_id: str
    artifact_type: str
    content_type: str
    storage_ref: str
    safe_name: str
    source_task_id: str
    evidence_level: str
    created_at: str
    redaction_applied: bool

    @classmethod
    def create(
        cls,
        artifact_type: str,
        content_type: str,
        storage_ref: str,
        safe_name: str,
        source_task_id: str,
        evidence_level: str = EvidenceLevel.STANDARD,
        redaction_applied: bool = True,
    ) -> "ArtifactEvidenceRef":
        return cls(
            artifact_id=_new_id("ar_"),
            artifact_type=artifact_type,
            content_type=content_type,
            storage_ref=storage_ref,
            safe_name=safe_name,
            source_task_id=source_task_id,
            evidence_level=evidence_level,
            created_at=_now_iso(),
            redaction_applied=redaction_applied,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        raw = {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content_type": self.content_type,
            "storage_ref": self.storage_ref,
            "safe_name": self.safe_name,
            "source_task_id": self.source_task_id,
            "evidence_level": self.evidence_level,
            "created_at": self.created_at,
            "redaction_applied": self.redaction_applied,
        }
        return strip_sensitive_fields(raw)
