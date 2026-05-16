"""ai_orchestrator Policy Layer 패키지.

책임:
- SafetyPolicy registry 단일 기준선 제공
- secret redaction 단일 source 제공
- 기존 execution_location_guard, action_risk_policy, server_egress_policy는 원본 유지
- 이 패키지는 통합 참조 계층 (얇은 registry)

이번 공정: 방화구획 기준선 고정 (Policy Layer Safety Registry Lock)
"""
from .safety_policy_registry import (
    SafetyPolicyRecord,
    get_policy,
    list_all_policies,
    list_policy_ids,
    get_policies_by_category,
    is_scope_blocked_by_policy,
    get_enforcement_decision,
    get_safe_to_execute_on_server,
    EXTERNAL_APP_HOLD_SCOPES,
    OAUTH_REQUIRED_SCOPES,
    USER_DIRECT_SCOPES,
    LOCAL_AGENT_SCOPES,
)
from .secret_redaction import (
    FORBIDDEN_SECRET_FIELDS,
    list_forbidden_secret_fields,
    contains_forbidden_secret_key,
    redact_sensitive_fields,
    strip_sensitive_fields,
    assert_no_sensitive_fields,
)

__all__ = [
    # safety policy registry
    "SafetyPolicyRecord",
    "get_policy",
    "list_all_policies",
    "list_policy_ids",
    "get_policies_by_category",
    "is_scope_blocked_by_policy",
    "get_enforcement_decision",
    "get_safe_to_execute_on_server",
    "EXTERNAL_APP_HOLD_SCOPES",
    "OAUTH_REQUIRED_SCOPES",
    "USER_DIRECT_SCOPES",
    "LOCAL_AGENT_SCOPES",
    # secret redaction
    "FORBIDDEN_SECRET_FIELDS",
    "list_forbidden_secret_fields",
    "contains_forbidden_secret_key",
    "redact_sensitive_fields",
    "strip_sensitive_fields",
    "assert_no_sensitive_fields",
]
