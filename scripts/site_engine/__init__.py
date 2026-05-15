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
]
