"""scripts.site_engine — 범용 사이트 자동화 엔진 기반."""
from scripts.site_engine.types import (
    ExecutionLocation,
    GateDecision,
    SiteActionKind,
    SiteCapability,
    SiteProfileStatus,
)
from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.registry import SiteProfileRegistry, get_default_registry
from scripts.site_engine.audit import (
    SiteEngineAuditEvent,
    build_audit_event,
    mask_sensitive,
)
from scripts.site_engine.execution_gate import (
    ActionSensitivity,
    ExecutionDecision,
    ExecutionGateInput,
    ExecutionGateResult,
    GateReason,
    evaluate_execution_gate,
    require_approval_for_action,
    block_for_sensitive_credential_action,
    resolve_execution_location,
)

__all__ = [
    "ExecutionLocation",
    "GateDecision",
    "SiteActionKind",
    "SiteCapability",
    "SiteProfileStatus",
    "SiteActionPolicy",
    "SiteProfile",
    "SiteProfileRegistry",
    "get_default_registry",
    "SiteEngineAuditEvent",
    "build_audit_event",
    "mask_sensitive",
    "ActionSensitivity",
    "ExecutionDecision",
    "ExecutionGateInput",
    "ExecutionGateResult",
    "GateReason",
    "evaluate_execution_gate",
    "require_approval_for_action",
    "block_for_sensitive_credential_action",
    "resolve_execution_location",
]
