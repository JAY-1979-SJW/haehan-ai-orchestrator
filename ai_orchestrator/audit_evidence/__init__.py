"""Audit/Evidence 표준화 패키지 — 기준선 모델 및 adapter.

이 패키지는 기존 audit_logger / task_state / approval / evidence_store를
대체하지 않는다. 표준 계약 모델과 read-only adapter를 제공한다.

금지:
- DB write 금지
- 외부 API 호출 금지
- secret/token/password/session/cookie 노출 금지
- 기존 저장 구조 변경 금지
"""
from ai_orchestrator.audit_evidence.models import (
    ArtifactEvidenceRef,
    AuditEventStatus,
    ExecutionAttempt,
    ExternalAppHandoff,
    SafetyVerdict,
    StandardAuditEvent,
)

__all__ = [
    "StandardAuditEvent",
    "ExecutionAttempt",
    "SafetyVerdict",
    "ExternalAppHandoff",
    "ArtifactEvidenceRef",
    "AuditEventStatus",
]
