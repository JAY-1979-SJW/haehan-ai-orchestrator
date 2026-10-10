"""Google tab-level feature logic.

Each Google tab exposes the same read/approval boundary so the app can attach
tabs without knowing the surface-specific implementation details.
"""
from __future__ import annotations

from typing import Any

from scripts.google.common import subdomain_logic
from scripts.google.common import tab_registry

TAB_USER_GUIDANCE: dict[str, dict[str, Any]] = {
    "search": {
        "user_can_request": [
            "Open Google home or search surface read-only.",
            "Check whether the Google account indicator is visible.",
            "Inspect public search/home controls without submitting a search.",
        ],
        "approval_required_for": [],
        "not_allowed": ["Credential entry", "cookie/session export"],
    },
    "identity": {
        "user_can_request": [
            "Open Google Account entry page.",
            "Check visible login/account state without reading secrets.",
            "Confirm whether user-present login is needed.",
        ],
        "approval_required_for": ["Any account/security setting change"],
        "not_allowed": ["Automatic login", "password/OTP handling", "session export"],
    },
    "workspace": {
        "user_can_request": [
            "Open Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Meet, Chat, Contacts, Keep, or Tasks read-only.",
            "Prepare drafts or plans for mail, file, calendar, document, sheet, form, chat, contact, note, or task work.",
            "Check which Workspace actions require approval before execution.",
        ],
        "approval_required_for": ["Send", "share", "upload", "create", "edit", "publish", "delete"],
        "not_allowed": ["Final send/share/publish without explicit approval"],
    },
    "cloud": {
        "user_can_request": [
            "Open Google Cloud Console surfaces read-only.",
            "Check project console, APIs and credentials, IAM, Billing, Cloud Run, Compute Engine, Storage, BigQuery, GKE, SQL, Pub/Sub, Secret Manager, Logging, Monitoring, and Vertex AI status.",
            "Ask for a safe plan before creating keys, changing IAM, deploying, creating resources, or changing billing.",
        ],
        "approval_required_for": ["API key creation", "IAM changes", "billing changes", "deploy", "resource create/update/delete", "secret changes"],
        "not_allowed": ["Final cloud state change without approval phrase", "secret value export"],
    },
    "ai": {
        "user_can_request": [
            "Open AI Studio, Gemini, or Vertex AI read-only.",
            "Inspect visible project/model controls.",
            "Prepare a plan for model, API key, or deployment work.",
        ],
        "approval_required_for": ["Prompt submission", "API key creation", "model training/deploy"],
        "not_allowed": ["Submitting private prompts or generating keys without approval"],
    },
    "youtube": {
        "user_can_request": [
            "Open YouTube or YouTube Studio read-only.",
            "Inspect channel/upload/metadata surfaces.",
            "Prepare upload or metadata plans without publishing.",
        ],
        "approval_required_for": ["Upload", "publish", "metadata edit", "comment/interact"],
        "not_allowed": ["Final publish or public channel change without approval"],
    },
    "marketing": {
        "user_can_request": [
            "Open Search Console, Business Profile, Analytics, Tag Manager, Ads, Merchant Center, AdSense, or Looker Studio read-only.",
            "Check visible property/account/report controls.",
            "Prepare SEO, indexing, analytics, ads, or reporting plans.",
        ],
        "approval_required_for": ["Indexing request", "public business listing change", "tag publish", "ad spend", "merchant listing changes"],
        "not_allowed": ["Public listing, ad spend, or tag publish without approval"],
    },
    "developer": {
        "user_can_request": [
            "Open Google developer documentation read-only.",
            "Open Play Console, Firebase, Apps Script, or Colab surfaces read-only.",
            "Prepare app, Firebase, script, or notebook action plans.",
        ],
        "approval_required_for": ["App release", "Firebase config change", "Apps Script deploy", "notebook code execution"],
        "not_allowed": ["Release/deploy/code execution without approval"],
    },
    "media": {
        "user_can_request": [
            "Open Google Photos read-only.",
            "Inspect visible album/media controls without downloading private media.",
            "Prepare organization or sharing plans.",
        ],
        "approval_required_for": ["Upload", "delete", "share", "album changes"],
        "not_allowed": ["Private media export or destructive media change without approval"],
    },
}


def _tabs_by_key() -> dict[str, dict[str, Any]]:
    summary = tab_registry.build_google_tab_summary()
    return {tab["key"]: tab for tab in summary["tabs"]}


def get_tab_summary(tab_key: str) -> dict[str, Any]:
    normalized = (tab_key or "").strip().lower()
    try:
        return _tabs_by_key()[normalized]
    except KeyError as exc:
        raise KeyError(f"unknown Google tab: {tab_key}") from exc


def list_tab_surfaces(tab_key: str) -> list[dict[str, Any]]:
    return list(get_tab_summary(tab_key)["surfaces"])


def list_tab_actions(tab_key: str) -> list[dict[str, Any]]:
    return list(get_tab_summary(tab_key)["actions"])


def list_tab_hosts(tab_key: str) -> list[str]:
    return list(get_tab_summary(tab_key)["hosts"])


def build_tab_logic_catalog(tab_key: str) -> dict[str, Any]:
    tab = get_tab_summary(tab_key)
    guidance = TAB_USER_GUIDANCE.get(tab["key"], {})
    return {
        "site_id": "google",
        "tab_key": tab["key"],
        "label": tab["label"],
        "owner_package": tab["owner_package"],
        "policy": tab["policy"],
        "surface_count": tab["surface_count"],
        "action_count": tab["action_count"],
        "read_action_count": tab["read_action_count"],
        "approval_action_count": tab["approval_action_count"],
        "hosts": tab["hosts"],
        "surfaces": tab["surfaces"],
        "actions": tab["actions"],
        "user_guidance": {
            "user_can_request": guidance.get("user_can_request", []),
            "approval_required_for": guidance.get("approval_required_for", []),
            "not_allowed": guidance.get("not_allowed", []),
        },
        "execution_policy": {
            "login": "user_present_only_no_credential_replay",
            "read": "local_agent_web_open_url_readonly",
            "state_change": "prepare_then_explicit_approval",
            "unknown_host": "fail_closed",
            "secret_export": "blocked",
        },
    }


def build_all_tab_logic_catalog() -> dict[str, Any]:
    tabs = [build_tab_logic_catalog(tab.key) for tab in tab_registry.GOOGLE_TABS]
    return {
        "site_id": "google",
        "tab_count": len(tabs),
        "tabs": tabs,
        "connection_lock": "server_first_task_queue_to_local_agent_websocket",
    }


def classify_tab_operation(tab_key: str, key_or_host: str, operation: str = "read") -> dict[str, Any]:
    tab = get_tab_summary(tab_key)
    result = subdomain_logic.classify_google_subdomain_operation(key_or_host, operation)
    host = result.get("host") or ""

    if result.get("operation") == "login_entry":
        return {
            **result,
            "tab_key": tab["key"],
            "tab_policy": tab["policy"],
        }

    if host and host not in tab["hosts"]:
        return {
            "ok": False,
            "reason": "google_subdomain_not_in_tab_fail_closed",
            "tab_key": tab["key"],
            "host": host,
            "operation": operation,
            "state_change": False,
            "approval_required": False,
            "local_agent_task": None,
        }

    return {
        **result,
        "tab_key": tab["key"],
        "tab_policy": tab["policy"],
    }


__all__ = [
    "TAB_USER_GUIDANCE",
    "build_all_tab_logic_catalog",
    "build_tab_logic_catalog",
    "classify_tab_operation",
    "get_tab_summary",
    "list_tab_actions",
    "list_tab_hosts",
    "list_tab_surfaces",
]
