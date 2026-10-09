"""Google subdomain feature logic.

This module converts the locked Google surface and workflow catalogs into a
host-oriented execution contract. It does not perform Google login, credential
entry, or account-content scraping. Login remains user-present only, and every
state-changing operation is returned as an approval-gated plan boundary.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from core.agent_runtime.runtime.common_tool_runtime import (
    EXECUTION_LOCAL_AGENT,
    RISK_READ,
    TOOL_BROWSER,
    build_common_tool_task,
)
from scripts.google.common import surfaces, workflows
from scripts.site_engine.sso_runtime import (
    build_login_entry_task,
    build_subdomain_readonly_task,
)
from scripts.site_engine.subdomain_registry import get_provider

READ_OPERATIONS = frozenset({"read", "open", "status", "inspect"})
LOGIN_OPERATIONS = frozenset({"login", "signin", "sign_in", "account_login"})
CREDENTIAL_OPERATIONS = frozenset(
    {"credential", "credentials", "password", "otp", "cookie", "session_export"}
)
GOOGLE_CONNECTION_SEQUENCE = (
    {
        "step": 1,
        "stage": "google_home",
        "url": "https://www.google.com/",
        "required": True,
        "verification": "host_is_www_google_com_and_page_reachable",
    },
    {
        "step": 2,
        "stage": "account_state",
        "url": "https://myaccount.google.com/",
        "required": True,
        "verification": "user_present_account_state_only_no_secret_export",
    },
    {
        "step": 3,
        "stage": "target_subdomain",
        "url": "",
        "required": True,
        "verification": "registered_google_subdomain_reachable_in_same_profile",
    },
    {
        "step": 4,
        "stage": "approval_url",
        "url": "",
        "required": False,
        "verification": "approval_or_oauth_url_only_after_steps_1_to_3",
    },
)


def _host(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return ""
    if "://" in candidate:
        return urlparse(candidate).netloc.lower()
    return candidate.strip("/")


def _google_sso_service_by_key_or_host(key_or_host: str) -> Any | None:
    google = get_provider("google")
    normalized = (key_or_host or "").strip().lower()
    host = _host(normalized)
    for service in google.services:
        if service.key == normalized or service.host == host:
            return service
    return None


def _surface_host_index() -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in surfaces.build_surface_catalog()["surfaces"]:
        index[_host(item["url"])].append(item)
    return dict(index)


def _action_host_index() -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in workflows.build_action_catalog()["actions"]:
        index[_host(item["target_url"])].append(item)
    return dict(index)


def build_google_subdomain_logic_catalog() -> dict[str, Any]:
    """Build a deterministic Google host-to-feature catalog."""
    surface_by_host = _surface_host_index()
    action_by_host = _action_host_index()
    google = get_provider("google")
    all_hosts = sorted(set(surface_by_host) | set(action_by_host) | {service.host for service in google.services})
    subdomains: list[dict[str, Any]] = []

    for host in all_hosts:
        host_surfaces = surface_by_host.get(host, [])
        host_actions = action_by_host.get(host, [])
        read_actions = [action for action in host_actions if not action["requires_approval"]]
        approval_actions = [action for action in host_actions if action["requires_approval"]]
        sso_service = next((service for service in google.services if service.host == host), None)
        subdomains.append(
            {
                "host": host,
                "sso_service_key": sso_service.key if sso_service else "",
                "surface_keys": [item["key"] for item in host_surfaces],
                "surface_labels": [item["label"] for item in host_surfaces],
                "read_actions": [item["key"] for item in read_actions],
                "approval_actions": [item["key"] for item in approval_actions],
                "risk_boundary": (
                    "approval_required_for_state_change"
                    if approval_actions
                    else "readonly_only"
                ),
                "execution_policy": {
                    "login": "user_present_only_no_credential_replay",
                    "read": "local_agent_web_open_url_readonly",
                    "state_change": "prepare_then_explicit_approval",
                    "final_submit": "blocked_without_approval_phrase",
                    "secret_export": "blocked",
                },
            }
        )

    return {
        "site_id": "google",
        "login_policy": "user_present_sso_profile",
        "connection_lock": "server_first_task_queue_to_local_agent_websocket",
        "auto_login": False,
        "credential_replay_allowed": False,
        "same_profile_subdomain_navigation": True,
        "browser_runtime": "managed_local_agent_cdp_profile",
        "default_browser_allowed": False,
        "connection_sequence_lock": list(GOOGLE_CONNECTION_SEQUENCE),
        "subdomain_count": len(subdomains),
        "subdomains": subdomains,
    }


def _first_surface_for_host(host: str) -> dict[str, Any] | None:
    items = _surface_host_index().get(host, [])
    return items[0] if items else None


def _build_readonly_task_for_host_or_service(key_or_host: str) -> dict[str, Any]:
    sso_service = _google_sso_service_by_key_or_host(key_or_host)
    if sso_service:
        return build_subdomain_readonly_task("google", sso_service.key)

    host = _host(key_or_host)
    surface = _first_surface_for_host(host)
    if not surface:
        raise KeyError(f"unknown Google subdomain: {key_or_host}")
    return build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action="web_open_url_readonly",
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        requires_approval=False,
        params={
            "url": surface["url"],
            "target_url_host": host,
            "wait_until": "domcontentloaded",
            "timeout_ms": 15000,
            "allow_private_network": False,
        },
        metadata={
            "site_id": "google",
            "sso_provider": "google",
            "sso_stage": "subdomain_readonly",
            "google_surface": surface["key"],
            "auto_login": False,
            "user_present_required": True,
            "shared_profile_required": True,
            "same_profile_subdomain_navigation": True,
            "secret_export_allowed": False,
        },
    )


def build_google_login_entry_logic() -> dict[str, Any]:
    task = build_login_entry_task("google")
    return {
        "ok": True,
        "provider_id": "google",
        "operation": "login_entry",
        "state_change": False,
        "auto_login": False,
        "credential_replay_allowed": False,
        "user_present_required": True,
        "connection_sequence_lock": list(GOOGLE_CONNECTION_SEQUENCE),
        "local_agent_task": task,
    }


def classify_google_subdomain_operation(key_or_host: str, operation: str = "read") -> dict[str, Any]:
    """Classify a Google subdomain operation without executing it."""
    normalized_operation = (operation or "read").strip().lower()
    if normalized_operation in LOGIN_OPERATIONS:
        return build_google_login_entry_logic()
    if normalized_operation in CREDENTIAL_OPERATIONS:
        return {
            "ok": False,
            "reason": "google_login_requires_user_present_no_credential_replay",
            "operation": normalized_operation,
            "state_change": False,
            "approval_required": False,
            "local_agent_task": None,
        }

    host = _host(key_or_host)
    sso_service = _google_sso_service_by_key_or_host(key_or_host)
    if sso_service:
        host = sso_service.host
    if host not in _surface_host_index() and not sso_service:
        return {
            "ok": False,
            "reason": "unknown_google_subdomain_fail_closed",
            "host": host,
            "operation": normalized_operation,
            "state_change": False,
            "approval_required": False,
            "local_agent_task": None,
        }

    if normalized_operation in READ_OPERATIONS:
        return {
            "ok": True,
            "reason": "readonly_google_subdomain_task_built",
            "host": host,
            "operation": normalized_operation,
            "state_change": False,
            "approval_required": False,
            "local_agent_task": _build_readonly_task_for_host_or_service(key_or_host),
        }

    approval_actions = [
        action
        for action in _action_host_index().get(host, [])
        if action["requires_approval"]
        and (
            normalized_operation == action["operation"]
            or normalized_operation in action["key"]
        )
    ]
    return {
        "ok": False,
        "reason": "google_subdomain_operation_requires_approval_gate",
        "host": host,
        "operation": normalized_operation,
        "state_change": True,
        "approval_required": True,
        "approval_phrase": workflows.APPROVAL_PHRASE,
        "candidate_actions": [action["key"] for action in approval_actions],
        "local_agent_task": None,
    }
