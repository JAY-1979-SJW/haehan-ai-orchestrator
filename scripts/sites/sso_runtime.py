"""Shared SSO/subdomain runtime rules for large portal providers."""
from __future__ import annotations

from typing import Any

from ai_orchestrator.local_agent.common_tool_runtime import (
    EXECUTION_LOCAL_AGENT,
    RISK_READ,
    TOOL_BROWSER,
    build_common_tool_task,
    dry_run_common_tool_flow,
)

from .subdomain_registry import get_provider, get_service

FORBIDDEN_SSO_FIELDS = frozenset(
    {
        "authorization",
        "auth_header",
        "api_key",
        "access_token",
        "refresh_token",
        "device_token",
        "token",
        "secret",
        "password",
        "otp",
        "cookie",
        "cookies",
        "session",
        "localstorage",
        "sessionstorage",
    }
)

BLOCKED_OPERATION_KEYWORDS = frozenset(
    {
        "write",
        "create",
        "delete",
        "publish",
        "send",
        "purchase",
        "billing",
        "iam",
        "deploy",
        "secret",
        "credential",
        "submit",
        "click",
        "type",
    }
)

SSO_CONNECTION_POLICY = {
    "entry_first": True,
    "account_state_before_subdomain": True,
    "target_subdomain_before_approval": True,
    "direct_oauth_entry_allowed": False,
    "error_code_for_direct_oauth": "SSO_DIRECT_OAUTH_ENTRY_BLOCKED",
}

OAUTH_CLIENT_POLICY = {
    "client_type_must_match_runtime": True,
    "redirect_uri_must_match_client_registration": True,
    "scope_must_match_declared_workflow": True,
    "web_app_client_for_local_cli_allowed": False,
    "local_cli_preferred_client_type": "desktop_app",
    "agent_non_secret_prefill_allowed": True,
    "prefill_requires_observable_target": True,
    "final_external_create_requires_user": True,
    "request_user_input_when_prefill_blocked": True,
    "error_code_for_mismatch": "OAUTH_CLIENT_REDIRECT_SCOPE_MISMATCH",
}


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in FORBIDDEN_SSO_FIELDS:
                return True
            if _contains_forbidden_field(child):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_field(item) for item in value)
    return False


def build_login_entry_task(provider_id: str) -> dict[str, Any]:
    provider = get_provider(provider_id)
    return build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action="web_open_url_readonly",
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        requires_approval=False,
        params={
            "url": provider.login_entry_url,
            "target_url_host": provider.login_entry_url.split("/")[2],
            "wait_until": "domcontentloaded",
            "timeout_ms": 15000,
            "allow_private_network": False,
        },
        metadata={
            "site_id": provider.provider_id,
            "sso_provider": provider.provider_id,
            "sso_stage": "login_entry_user_present",
            "sso_connection_policy": SSO_CONNECTION_POLICY,
            "oauth_client_policy": OAUTH_CLIENT_POLICY,
            "auto_login": False,
            "user_present_required": True,
            "shared_profile_required": True,
            "same_profile_subdomain_navigation": True,
            "secret_export_allowed": False,
        },
    )


def build_subdomain_readonly_task(provider_id: str, service_key: str) -> dict[str, Any]:
    provider = get_provider(provider_id)
    service = get_service(provider_id, service_key)
    return build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action=service.default_action,
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        requires_approval=False,
        params={
            "url": service.url,
            "target_url_host": service.host,
            "wait_until": "domcontentloaded",
            "timeout_ms": 15000,
            "allow_private_network": False,
        },
        metadata={
            "site_id": provider.provider_id,
            "sso_provider": provider.provider_id,
            "sso_service": service.key,
            "sso_stage": "subdomain_readonly",
            "sso_connection_policy": SSO_CONNECTION_POLICY,
            "oauth_client_policy": OAUTH_CLIENT_POLICY,
            "auto_login": False,
            "user_present_required": True,
            "shared_profile_required": True,
            "same_profile_subdomain_navigation": True,
            "secret_export_allowed": False,
        },
    )


def build_blocked_operation_result(provider_id: str, service_key: str, operation: str) -> dict[str, Any]:
    get_service(provider_id, service_key)
    normalized = (operation or "").strip().lower()
    if normalized == "read":
        raise ValueError("read operation is not blocked")
    return {
        "ok": False,
        "reason": "sso_subdomain_operation_requires_separate_approval_gate",
        "provider_id": provider_id,
        "service_key": service_key,
        "operation": operation,
        "state_change": False,
        "sso_connection_policy": SSO_CONNECTION_POLICY,
        "oauth_client_policy": OAUTH_CLIENT_POLICY,
        "local_agent_task": None,
    }


def dry_run_subdomain_readonly_task(provider_id: str, service_key: str) -> dict[str, Any]:
    task = build_subdomain_readonly_task(provider_id, service_key)
    result = dry_run_common_tool_flow(task)
    return {
        "ok": bool(result.get("ok")),
        "provider_id": provider_id,
        "service_key": service_key,
        "state_change": False,
        "local_agent_task": task,
        "dry_run_result": result,
        "contains_forbidden_field": _contains_forbidden_field({"task": task, "result": result}),
    }


def dry_run_login_entry_task(provider_id: str) -> dict[str, Any]:
    task = build_login_entry_task(provider_id)
    result = dry_run_common_tool_flow(task)
    return {
        "ok": bool(result.get("ok")),
        "provider_id": provider_id,
        "state_change": False,
        "local_agent_task": task,
        "dry_run_result": result,
        "contains_forbidden_field": _contains_forbidden_field({"task": task, "result": result}),
    }
