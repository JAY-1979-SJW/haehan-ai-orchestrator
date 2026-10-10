"""Locked Google module ownership and implementation contracts."""

from __future__ import annotations

from typing import Any

GOOGLE_TOP_MODULE = {
    "key": "google_manager",
    "label": "Google Management",
    "purpose": "Route Google work through bounded submodules with home-login, approval, and no-secret gates.",
    "entry_commands": ["google check", "google modules", "google taxonomy", "google work", "google surfaces"],
    "default_login_entry": "https://www.google.com/",
    "session_policy": "home_login_user_present_then_submodule_work",
    "secret_policy": "no_plain_secret_output_final_secret_issue_approval",
    "final_action_policy": "prepare_and_prefill_allowed_final_submit_requires_user_approval",
}

SUBMODULE_OWNERS: dict[str, dict[str, Any]] = {
    "search_entry": {
        "module": "scripts.google.search",
        "router_tasks": ["login", "surfaces", "subdomains", "tabs"],
        "mode": "browser_readonly",
        "status": "managed",
    },
    "identity_access": {
        "module": "scripts.google.identity",
        "router_tasks": ["login", "session-check"],
        "mode": "user_present_only",
        "status": "managed",
    },
    "workspace_productivity": {
        "module": "scripts.google.workspace",
        "router_tasks": ["mail", "drive", "calendar", "docs", "sheets", "basic"],
        "mode": "api_preferred_then_browser_gate",
        "status": "implemented_partial",
    },
    "cloud_backend": {
        "module": "scripts.google.cloud",
        "router_tasks": ["cloud", "console"],
        "mode": "console_readonly_then_approval",
        "status": "implemented_catalog_first",
    },
    "ai_model": {
        "module": "scripts.google.ai",
        "router_tasks": ["ai", "vision"],
        "mode": "free_tier_or_usage_gate",
        "status": "managed",
    },
    "android_app": {
        "module": "scripts.google.android_app_dev_report",
        "router_tasks": ["android", "android-app", "app-dev"],
        "mode": "docs_and_console_plan",
        "status": "managed",
    },
    "marketing_seo": {
        "module": "scripts.google.marketing",
        "router_tasks": ["ads"],
        "mode": "readonly_reporting_paid_actions_approval",
        "status": "catalog_first",
    },
    "youtube_creator": {
        "module": "scripts.google.youtube",
        "router_tasks": ["youtube"],
        "mode": "research_readonly_upload_approval",
        "status": "implemented_partial",
    },
    "media_private": {
        "module": "scripts.google.media",
        "router_tasks": ["surfaces", "tabs"],
        "mode": "readonly_private_then_approval",
        "status": "catalog_only",
    },
    "developer_tools": {
        "module": "scripts.google.developer",
        "router_tasks": ["surfaces", "tabs"],
        "mode": "public_docs_readonly_console_approval",
        "status": "catalog_only",
    },
}

SURFACE_IMPLEMENTATION_MODULES: dict[str, str] = {
    "gmail": "scripts.google.workspace.gmail",
    "drive": "scripts.google.workspace.drive",
    "calendar": "scripts.google.workspace.calendar_tasks",
    "docs": "scripts.google.workspace.docs",
    "sheets": "scripts.google.workspace.sheets",
    "slides": "scripts.google.workspace.slides",
    "forms": "scripts.google.workspace.forms",
    "meet": "scripts.google.workspace.meet",
    "chat": "scripts.google.workspace.chat",
    "contacts": "scripts.google.workspace.contacts",
    "keep": "scripts.google.workspace.keep",
    "tasks": "scripts.google.workspace.tasks",
    "cloud_console": "scripts.google.cloud.console",
    "maps_platform": "scripts.google.cloud.maps_platform",
    "cloud_apis_credentials": "scripts.google.cloud.api_credentials",
    "cloud_iam": "scripts.google.cloud.iam",
    "cloud_billing": "scripts.google.cloud.billing",
    "cloud_run": "scripts.google.cloud.run",
    "compute_engine": "scripts.google.cloud.compute",
    "cloud_storage": "scripts.google.cloud.storage",
    "bigquery": "scripts.google.cloud.bigquery",
    "gke": "scripts.google.cloud.gke",
    "cloud_sql": "scripts.google.cloud.sql",
    "pubsub": "scripts.google.cloud.pubsub",
    "secret_manager": "scripts.google.cloud.secret_manager",
    "cloud_logging": "scripts.google.cloud.cloud_logging_catalog",
    "cloud_monitoring": "scripts.google.cloud.monitoring",
    "youtube": "scripts.google.youtube.search",
    "youtube_studio": "scripts.google.common.youtube_upload",
    "ai_studio": "scripts.google.ai",
    "gemini": "scripts.google.ai",
    "vertex_ai": "scripts.google.ai",
    "android_developers": "scripts.google.android_app_dev_report",
    "play_console": "scripts.google.android_app_dev_report",
    "firebase_console": "scripts.google.android_app_dev_report",
    "ads": "scripts.google.ads_signup",
}
