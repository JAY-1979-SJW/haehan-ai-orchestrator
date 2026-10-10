"""Shared SSO/subdomain runtime rules for large portal providers."""
from __future__ import annotations

import urllib.parse
from typing import Any

from core.agent_runtime.runtime.common_tool_runtime import (
    EXECUTION_LOCAL_AGENT,
    RISK_READ,
    TOOL_BROWSER,
    build_common_tool_task,
    dry_run_common_tool_flow,
)
from scripts.site_engine.subdomain_registry import get_provider, get_service

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

OCCASIONAL_SITE_LOGIN_POLICY = {
    "developed_site_required": False,
    "tool_development_required": False,
    "one_time_or_infrequent_use": True,
    "entry_url_required": True,
    "auto_login": False,
    "credential_replay_allowed": False,
    "user_enters_credentials": True,
    "agent_password_or_otp_entry_allowed": False,
    "user_may_disclose_raw_credentials_to_agent": False,
    "raw_credential_handoff_allowed": False,
    "credential_capture_allowed_even_with_user_request": False,
    "allowed_agent_login_role": "open_login_surface_detect_completion_save_session_only",
    "readonly_session_check_only": True,
    "state_change_allowed": False,
    "final_approval_required_for_state_change": True,
}

RAW_CREDENTIAL_HANDOFF_POLICY = {
    "accepted": False,
    "reason": "raw_login_credentials_must_not_be_disclosed_to_agent",
    "user_authority_boundary": (
        "The user may decide to log in, but the user enters credentials directly "
        "in the browser or an approved local secret store; the agent does not "
        "receive, echo, log, store, replay, or type raw passwords, OTPs, or recovery codes."
    ),
    "allowed_flow": "user_present_login_then_agent_detects_completion_and_saves_domain_session",
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


def _normalize_public_entry_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("occasional site login requires an http(s) entry URL")
    host = parsed.hostname or ""
    if host.lower() in {"localhost"} or host.startswith("127.") or host == "::1":
        raise ValueError("occasional site login entry URL must not be localhost")
    clean = urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            "",
            "",
            "",
        )
    )
    return clean, host


def build_occasional_site_login_task(entry_url: str, *, site_label: str = "") -> dict[str, Any]:
    """Build a user-present login handoff for an undeveloped or infrequent site."""
    clean_url, host = _normalize_public_entry_url(entry_url)
    return build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action="web_open_url_readonly",
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        requires_approval=False,
        params={
            "url": clean_url,
            "target_url_host": host,
            "wait_until": "domcontentloaded",
            "timeout_ms": 15000,
            "allow_private_network": False,
        },
        metadata={
            "site_id": site_label or host,
            "site_label": site_label or host,
            "sso_stage": "occasional_site_login_user_present",
            "occasional_site_login_policy": OCCASIONAL_SITE_LOGIN_POLICY,
            "auto_login": False,
            "user_present_required": True,
            "shared_profile_required": True,
            "same_profile_subdomain_navigation": False,
            "secret_export_allowed": False,
            "developed_site_required": False,
            "tool_development_required": False,
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


def build_raw_credential_handoff_rejection(*, site_label: str = "") -> dict[str, Any]:
    """Return the locked result for attempts to give raw login secrets to the agent."""
    return {
        "ok": False,
        "blocked": True,
        "site_label": site_label,
        "policy": RAW_CREDENTIAL_HANDOFF_POLICY,
        "secret_values_output": False,
        "agent_may_receive_raw_credentials": False,
        "agent_may_type_password_or_otp": False,
        "allowed_next_step": RAW_CREDENTIAL_HANDOFF_POLICY["allowed_flow"],
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


def dry_run_occasional_site_login_task(entry_url: str, *, site_label: str = "") -> dict[str, Any]:
    task = build_occasional_site_login_task(entry_url, site_label=site_label)
    result = dry_run_common_tool_flow(task)
    return {
        "ok": bool(result.get("ok")),
        "entry_url": task["params"]["url"],
        "state_change": False,
        "local_agent_task": task,
        "dry_run_result": result,
        "contains_forbidden_field": _contains_forbidden_field({"task": task, "result": result}),
    }
