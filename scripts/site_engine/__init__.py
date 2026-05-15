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
from scripts.site_engine.adapters.browser import (
    BrowserActionKind,
    BrowserActionPlan,
    BrowserActionResult,
    build_readonly_navigation_plan,
    build_click_plan,
    build_input_plan,
    build_download_plan,
    build_upload_plan,
    build_submit_plan,
)
from scripts.site_engine.form_resolver import (
    FormFieldCandidate,
    FormFieldKind,
    FormFieldSensitivity,
    FormResolutionInput,
    FormResolutionResult,
    resolve_form_fields,
    classify_field_sensitivity,
    mask_field_value,
)
from scripts.site_engine.capability_detector import (
    PageCapability,
    CapabilityDetectionInput,
    CapabilityDetectionResult,
    detect_capabilities_from_snapshot,
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
