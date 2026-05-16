"""ai_orchestrator 도메인 기준 타입 패키지."""
from .enums import (
    RiskLevel,
    ExecutionLocation,
    TaskStatus,
    ApprovalStatus,
    Verdict,
)
from .response_envelope import ApiResponse, ApiError, ApiMeta, api_success, api_error
from .response_adapter import wrap_legacy_dict

from .models import (
    WorkTradeScope,
    IntegrationStatus,
    HandoffMode,
    SafetyDecision,
    ArtifactType,
    EvidenceLevel,
    Task,
    WorkTrade,
    ExternalWork,
    Integration,
    Artifact,
    SafetyPolicy,
    ExternalAppBridge,
    AuditEvent,
    make_task,
    make_audit_event,
    DOMAIN_FORBIDDEN_FIELDS,
    assert_no_forbidden_fields,
)

__all__ = [
    # enums
    "RiskLevel", "ExecutionLocation", "TaskStatus", "ApprovalStatus", "Verdict",
    # response
    "ApiResponse", "ApiError", "ApiMeta", "api_success", "api_error",
    "wrap_legacy_dict",
    # domain models (new)
    "WorkTradeScope", "IntegrationStatus", "HandoffMode",
    "SafetyDecision", "ArtifactType", "EvidenceLevel",
    "Task", "WorkTrade", "ExternalWork", "Integration",
    "Artifact", "SafetyPolicy", "ExternalAppBridge", "AuditEvent",
    "make_task", "make_audit_event",
    "DOMAIN_FORBIDDEN_FIELDS", "assert_no_forbidden_fields",
]
