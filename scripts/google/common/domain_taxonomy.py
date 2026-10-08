"""Google domain taxonomy, handling policy, and user-facing labels."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.google.common import surfaces, tab_registry, workflows
from scripts.google.common.report_io import print_report_summary, save_json_md_report

ROOT = Path(__file__).resolve().parents[3]
DATA_REPORT_DIR = ROOT / "data" / "google_domain_taxonomy_reports"
LATEST_REPORT = ROOT / "data" / "google_domain_taxonomy_latest.json"
DOC_REPORT_DIR = ROOT / "docs" / "reports"


GROUPS: dict[str, dict[str, Any]] = {
    "search_entry": {
        "label": "Search / Entry",
        "section": "Public Entry",
        "default_handling": "readonly_public_navigation",
        "default_cost_label": "free_public_read",
        "priority": 10,
    },
    "identity_access": {
        "label": "Identity / Access",
        "section": "Account And SSO",
        "default_handling": "user_present_login_only",
        "default_cost_label": "account_required_no_direct_cost",
        "priority": 20,
    },
    "workspace_productivity": {
        "label": "Workspace / Productivity",
        "section": "Private Work Data",
        "default_handling": "api_preferred_readonly_then_approval",
        "default_cost_label": "workspace_plan_or_account_dependent",
        "priority": 30,
    },
    "cloud_backend": {
        "label": "Cloud / Backend",
        "section": "Server And Infrastructure",
        "default_handling": "readonly_project_context_then_approval",
        "default_cost_label": "usage_based_or_billing_project_required",
        "priority": 40,
    },
    "ai_model": {
        "label": "AI / Model Tools",
        "section": "AI Execution",
        "default_handling": "readonly_then_approval_for_prompt_key_or_deploy",
        "default_cost_label": "free_tier_or_usage_based_by_product",
        "priority": 50,
    },
    "android_app": {
        "label": "Android App Development",
        "section": "App Build Release Operate",
        "default_handling": "docs_free_console_approval_gated",
        "default_cost_label": "free_docs_registration_or_usage_based_console",
        "priority": 60,
    },
    "marketing_seo": {
        "label": "Marketing / SEO / Analytics",
        "section": "Site Growth And Measurement",
        "default_handling": "readonly_property_context_then_approval",
        "default_cost_label": "free_reporting_or_spend_billing_dependent",
        "priority": 70,
    },
    "youtube_creator": {
        "label": "YouTube / Creator",
        "section": "Video Channel Operations",
        "default_handling": "readonly_channel_context_then_approval",
        "default_cost_label": "free_viewing_publish_or_monetization_policy_dependent",
        "priority": 80,
    },
    "media_private": {
        "label": "Personal Media",
        "section": "Private Media",
        "default_handling": "readonly_private_media_then_approval",
        "default_cost_label": "account_storage_plan_dependent",
        "priority": 90,
    },
    "developer_tools": {
        "label": "Developer Tools",
        "section": "Developer Automation",
        "default_handling": "public_docs_readonly_console_actions_approval_gated",
        "default_cost_label": "free_docs_usage_or_execution_dependent",
        "priority": 100,
    },
}


SURFACE_GROUPS: dict[str, str] = {
    "google_home": "search_entry",
    "google_account": "identity_access",
    "gmail": "workspace_productivity",
    "drive": "workspace_productivity",
    "calendar": "workspace_productivity",
    "docs": "workspace_productivity",
    "sheets": "workspace_productivity",
    "slides": "workspace_productivity",
    "forms": "workspace_productivity",
    "meet": "workspace_productivity",
    "chat": "workspace_productivity",
    "contacts": "workspace_productivity",
    "keep": "workspace_productivity",
    "tasks": "workspace_productivity",
    "cloud_console": "cloud_backend",
    "maps_platform": "cloud_backend",
    "cloud_apis_credentials": "cloud_backend",
    "cloud_iam": "cloud_backend",
    "cloud_billing": "cloud_backend",
    "cloud_run": "cloud_backend",
    "compute_engine": "cloud_backend",
    "cloud_storage": "cloud_backend",
    "bigquery": "cloud_backend",
    "gke": "cloud_backend",
    "cloud_sql": "cloud_backend",
    "pubsub": "cloud_backend",
    "secret_manager": "cloud_backend",
    "cloud_logging": "cloud_backend",
    "cloud_monitoring": "cloud_backend",
    "ai_studio": "ai_model",
    "gemini": "ai_model",
    "vertex_ai": "ai_model",
    "android_developers": "android_app",
    "play_console": "android_app",
    "firebase_console": "android_app",
    "search_console": "marketing_seo",
    "business_profile": "marketing_seo",
    "analytics": "marketing_seo",
    "tag_manager": "marketing_seo",
    "ads": "marketing_seo",
    "merchant_center": "marketing_seo",
    "adsense": "marketing_seo",
    "looker_studio": "marketing_seo",
    "youtube": "youtube_creator",
    "youtube_studio": "youtube_creator",
    "photos": "media_private",
    "google_developers": "developer_tools",
    "chrome_developers": "developer_tools",
    "apps_script": "developer_tools",
    "colab": "developer_tools",
}


SURFACE_SUBSECTIONS: dict[str, str] = {
    "google_home": "home_and_public_search",
    "google_account": "account_security_and_session",
    "gmail": "mail",
    "drive": "files",
    "calendar": "calendar",
    "docs": "documents",
    "sheets": "spreadsheets",
    "slides": "presentations",
    "forms": "forms_and_responses",
    "meet": "meetings",
    "chat": "messaging",
    "contacts": "contacts",
    "keep": "notes",
    "tasks": "tasks",
    "cloud_console": "project_overview",
    "maps_platform": "maps_api_billing_keys",
    "cloud_apis_credentials": "apis_credentials_oauth",
    "cloud_iam": "identity_access_management",
    "cloud_billing": "billing_budget_payment",
    "cloud_run": "serverless_runtime",
    "compute_engine": "virtual_machines_network_disks",
    "cloud_storage": "object_storage",
    "bigquery": "data_warehouse",
    "gke": "kubernetes_clusters",
    "cloud_sql": "managed_database",
    "pubsub": "messaging_topics",
    "secret_manager": "secrets",
    "cloud_logging": "logs",
    "cloud_monitoring": "metrics_alerts",
    "ai_studio": "ai_prompt_and_api_key_lab",
    "gemini": "chat_ai_app",
    "vertex_ai": "cloud_ai_training_deploy",
    "android_developers": "android_docs_and_ui_guidance",
    "play_console": "android_release_testing_store",
    "firebase_console": "mobile_backend_and_analytics",
    "search_console": "seo_indexing_property",
    "business_profile": "public_business_listing",
    "analytics": "web_app_analytics",
    "tag_manager": "tag_container_publish",
    "ads": "paid_ads_campaigns",
    "merchant_center": "product_listing_feed",
    "adsense": "site_monetization",
    "looker_studio": "reports_dashboards",
    "youtube": "video_viewing_interaction",
    "youtube_studio": "channel_upload_publish_analytics",
    "photos": "private_photo_library",
    "google_developers": "google_api_docs_index",
    "chrome_developers": "chrome_webview_pwa_docs",
    "apps_script": "workspace_script_automation",
    "colab": "notebook_runtime",
}


HIGH_RISK_TERMS = ("billing", "iam", "credential", "secret", "deploy", "release", "publish", "spend", "delete")
PRIVATE_TERMS = ("private", "contact", "media", "prompt", "logs")


PAGE_TAB_SPECS: dict[str, list[tuple[str, str, str]]] = {
    "google_home": [
        ("search", "Search", "readonly"),
        ("apps_launcher", "Google apps launcher", "readonly"),
        ("account_indicator", "Account indicator", "readonly_sensitive"),
    ],
    "google_account": [
        ("home", "Account home", "readonly_sensitive"),
        ("security", "Security", "approval_required"),
        ("personal_info", "Personal info", "approval_required"),
        ("data_privacy", "Data and privacy", "approval_required"),
        ("payments", "Payments and subscriptions", "approval_required"),
    ],
    "gmail": [
        ("inbox", "Inbox", "readonly_private"),
        ("search", "Mail search", "readonly_private"),
        ("compose", "Compose draft", "no_final_submit"),
        ("sent", "Sent mail", "readonly_private"),
        ("settings", "Settings", "approval_required"),
    ],
    "drive": [
        ("my_drive", "My Drive", "readonly_private"),
        ("shared", "Shared files", "readonly_private"),
        ("recent", "Recent files", "readonly_private"),
        ("upload", "Upload", "approval_required"),
        ("share", "Share and permissions", "approval_required"),
    ],
    "calendar": [
        ("calendar_view", "Calendar view", "readonly_private"),
        ("event_detail", "Event detail", "readonly_private"),
        ("create_event", "Create event", "no_final_submit"),
        ("settings", "Calendar settings", "approval_required"),
    ],
    "docs": [("recent", "Recent documents", "readonly_private"), ("editor", "Document editor", "approval_required"), ("share", "Share", "approval_required")],
    "sheets": [("recent", "Recent spreadsheets", "readonly_private"), ("grid", "Sheet grid", "approval_required"), ("share", "Share", "approval_required")],
    "slides": [("recent", "Recent presentations", "readonly_private"), ("editor", "Presentation editor", "approval_required"), ("present_share", "Present and share", "approval_required")],
    "forms": [("forms_home", "Forms home", "readonly_private"), ("questions", "Questions", "approval_required"), ("responses", "Responses", "readonly_private"), ("send", "Send form", "approval_required")],
    "meet": [("home", "Meet home", "readonly_private"), ("join", "Join meeting", "approval_required"), ("create", "Create meeting", "approval_required")],
    "chat": [("spaces", "Spaces", "readonly_private"), ("direct_messages", "Direct messages", "readonly_private"), ("send_message", "Send message", "approval_required")],
    "contacts": [("contacts", "Contacts", "readonly_private"), ("labels", "Labels", "approval_required"), ("create_edit", "Create or edit contact", "approval_required")],
    "keep": [("notes", "Notes", "readonly_private"), ("labels", "Labels", "approval_required"), ("archive_trash", "Archive and trash", "approval_required")],
    "tasks": [("task_lists", "Task lists", "readonly_private"), ("task_detail", "Task detail", "readonly_private"), ("create_edit", "Create or edit task", "approval_required")],
    "cloud_console": [("dashboard", "Project dashboard", "readonly_sensitive"), ("resources", "Resources", "readonly_sensitive"), ("activity", "Activity", "readonly_sensitive")],
    "maps_platform": [("apis", "Maps APIs", "readonly_sensitive"), ("keys", "API keys", "approval_required"), ("quotas_billing", "Quotas and billing", "approval_required")],
    "cloud_apis_credentials": [("enabled_apis", "Enabled APIs", "readonly_sensitive"), ("credentials", "Credentials", "approval_required"), ("oauth_consent", "OAuth consent", "approval_required")],
    "cloud_iam": [("principals", "Principals", "readonly_sensitive"), ("roles", "Roles", "approval_required"), ("service_accounts", "Service accounts", "approval_required")],
    "cloud_billing": [("billing_accounts", "Billing accounts", "readonly_sensitive"), ("budgets", "Budgets", "approval_required"), ("payment_profile", "Payment profile", "approval_required")],
    "cloud_run": [("services", "Services", "readonly_sensitive"), ("revisions", "Revisions", "readonly_sensitive"), ("deploy", "Deploy", "approval_required")],
    "compute_engine": [("vm_instances", "VM instances", "readonly_sensitive"), ("disks", "Disks", "approval_required"), ("networking", "Networking", "approval_required")],
    "cloud_storage": [("buckets", "Buckets", "readonly_sensitive"), ("objects", "Objects", "readonly_sensitive"), ("permissions", "Permissions", "approval_required")],
    "bigquery": [("explorer", "Explorer", "readonly_sensitive"), ("query", "Query editor", "approval_required"), ("export", "Export", "approval_required")],
    "gke": [("clusters", "Clusters", "readonly_sensitive"), ("workloads", "Workloads", "readonly_sensitive"), ("apply_change", "Apply change", "approval_required")],
    "cloud_sql": [("instances", "Instances", "readonly_sensitive"), ("databases", "Databases", "approval_required"), ("backups", "Backups", "approval_required")],
    "pubsub": [("topics", "Topics", "readonly_sensitive"), ("subscriptions", "Subscriptions", "readonly_sensitive"), ("publish", "Publish message", "approval_required")],
    "secret_manager": [("secrets", "Secrets", "secret_sensitive"), ("versions", "Versions", "secret_sensitive"), ("create_update", "Create or update secret", "approval_required")],
    "cloud_logging": [("logs_explorer", "Logs Explorer", "readonly_private"), ("queries", "Saved queries", "approval_required"), ("sinks", "Sinks", "approval_required")],
    "cloud_monitoring": [("dashboards", "Dashboards", "readonly_sensitive"), ("alerts", "Alert policies", "approval_required"), ("uptime_checks", "Uptime checks", "approval_required")],
    "ai_studio": [("prompts", "Prompts", "no_final_submit"), ("api_keys", "API keys", "approval_required"), ("models", "Models", "readonly_sensitive")],
    "gemini": [("chat", "Chat", "no_final_submit"), ("history", "History", "readonly_private"), ("settings", "Settings", "approval_required")],
    "vertex_ai": [("model_garden", "Model Garden", "readonly_sensitive"), ("endpoints", "Endpoints", "approval_required"), ("jobs", "Jobs", "approval_required")],
    "android_developers": [("docs", "Docs", "readonly"), ("jetpack_compose", "Jetpack Compose", "readonly"), ("samples", "Samples", "readonly")],
    "play_console": [("dashboard", "Dashboard", "readonly_sensitive"), ("testing", "Testing tracks", "approval_required"), ("releases", "Releases", "approval_required"), ("store_listing", "Store listing", "approval_required"), ("policy", "Policy", "readonly_sensitive")],
    "firebase_console": [("project_overview", "Project overview", "readonly_sensitive"), ("auth", "Authentication", "approval_required"), ("firestore", "Firestore", "approval_required"), ("hosting", "Hosting", "approval_required"), ("crashlytics", "Crashlytics", "readonly_private")],
    "search_console": [("overview", "Overview", "readonly_sensitive"), ("performance", "Performance", "readonly_sensitive"), ("url_inspection", "URL inspection", "no_final_submit"), ("indexing", "Indexing", "approval_required"), ("sitemaps", "Sitemaps", "approval_required")],
    "business_profile": [("profile", "Business profile", "readonly_sensitive"), ("posts", "Posts", "approval_required"), ("reviews", "Reviews", "approval_required"), ("photos", "Photos", "approval_required")],
    "analytics": [("reports", "Reports", "readonly_sensitive"), ("explore", "Explore", "readonly_sensitive"), ("admin", "Admin", "approval_required"), ("export", "Export", "approval_required")],
    "tag_manager": [("workspace", "Workspace", "readonly_sensitive"), ("tags", "Tags", "approval_required"), ("triggers", "Triggers", "approval_required"), ("versions", "Versions", "approval_required"), ("publish", "Publish", "approval_required")],
    "ads": [("overview", "Overview", "readonly_sensitive"), ("campaigns", "Campaigns", "approval_required"), ("budgets", "Budgets", "approval_required"), ("billing", "Billing", "approval_required")],
    "merchant_center": [("overview", "Overview", "readonly_sensitive"), ("products", "Products", "approval_required"), ("feeds", "Feeds", "approval_required"), ("shipping_tax", "Shipping and tax", "approval_required")],
    "adsense": [("sites", "Sites", "readonly_sensitive"), ("ads", "Ads", "approval_required"), ("payments", "Payments", "approval_required"), ("reports", "Reports", "readonly_sensitive")],
    "looker_studio": [("reports", "Reports", "readonly_sensitive"), ("data_sources", "Data sources", "approval_required"), ("share", "Share", "approval_required")],
    "youtube": [
        ("home", "Home", "readonly"),
        ("search", "Search", "readonly"),
        ("subscriptions", "Subscriptions", "readonly_private"),
        ("library_history", "Library and history", "readonly_private"),
        ("shorts", "Shorts", "readonly"),
        ("channel", "Channel page", "readonly_private"),
        ("interactions", "Like, comment, subscribe", "approval_required"),
    ],
    "youtube_studio": [
        ("dashboard", "Dashboard", "readonly_sensitive"),
        ("content", "Content", "readonly_sensitive"),
        ("upload", "Upload video", "no_final_submit"),
        ("analytics", "Analytics", "readonly_sensitive"),
        ("comments", "Comments", "approval_required"),
        ("subtitles", "Subtitles", "approval_required"),
        ("copyright", "Copyright", "readonly_sensitive"),
        ("earn", "Earn / monetization", "approval_required"),
        ("customization", "Customization", "approval_required"),
        ("settings", "Settings", "approval_required"),
    ],
    "photos": [("photos", "Photos", "readonly_private"), ("albums", "Albums", "readonly_private"), ("sharing", "Sharing", "approval_required"), ("upload", "Upload", "approval_required")],
    "google_developers": [("products", "Products", "readonly"), ("docs", "Docs", "readonly"), ("api_guides", "API guides", "readonly")],
    "chrome_developers": [("docs", "Docs", "readonly"), ("webview", "WebView", "readonly"), ("pwa", "PWA", "readonly")],
    "apps_script": [("projects", "Projects", "readonly_sensitive"), ("editor", "Editor", "approval_required"), ("deployments", "Deployments", "approval_required"), ("triggers", "Triggers", "approval_required")],
    "colab": [("notebooks", "Notebooks", "readonly_private"), ("runtime", "Runtime", "approval_required"), ("files", "Files", "readonly_private"), ("sharing", "Sharing", "approval_required")],
}


def _host(url: str) -> str:
    return url.split("/")[2] if "://" in url else ""


def _approval_level(surface: dict[str, Any], approval_actions: list[dict[str, Any]]) -> str:
    risk = surface["risk"].lower()
    if any(term in risk for term in HIGH_RISK_TERMS) or approval_actions:
        return "explicit_approval_required"
    if "write_possible" in risk or "state" in risk:
        return "approval_required_for_mutation"
    return "readonly_allowed"


def _data_classification(surface: dict[str, Any]) -> str:
    risk = surface["risk"].lower()
    if "secret" in risk or "credential" in risk:
        return "secret_sensitive"
    if "billing" in risk or "iam" in risk:
        return "admin_sensitive"
    if any(term in risk for term in PRIVATE_TERMS):
        return "private_or_account_data"
    if "public" in risk or risk == "read":
        return "public_read"
    return "account_context"


def _user_can_request(surface: dict[str, Any], group: dict[str, Any], subsection: str) -> list[str]:
    label = surface["label"]
    return [
        f"Open {label} read-only and identify visible account/project/property context.",
        f"Classify {label} controls under `{subsection}` before attaching app UI.",
        f"Prepare a dry-run plan for {label} changes without final submission.",
    ]


def _approval_required_for(surface: dict[str, Any], approval_actions: list[dict[str, Any]]) -> list[str]:
    if approval_actions:
        return sorted({action["operation"] for action in approval_actions})
    risk = surface["risk"].lower()
    required = []
    if "write" in risk or "publish" in risk:
        required.append("create/update/publish/delete")
    if "billing" in risk or "spend" in risk:
        required.append("billing_or_spend_change")
    if "credential" in risk or "secret" in risk:
        required.append("credential_or_secret_change")
    if "deploy" in risk or "release" in risk:
        required.append("deploy_or_release")
    return required


def _not_allowed(surface: dict[str, Any]) -> list[str]:
    blocked = ["credential replay", "cookie/session export", "final submit without approval"]
    risk = surface["risk"].lower()
    if "secret" in risk or "credential" in risk:
        blocked.append("secret value export")
    if "billing" in risk or "spend" in risk:
        blocked.append("payment or spend change without explicit approval")
    return blocked


def _page_tabs(surface: dict[str, Any]) -> list[dict[str, Any]]:
    tabs = []
    for tab_key, label, handling in PAGE_TAB_SPECS[surface["key"]]:
        state_change = handling in {"approval_required", "no_final_submit"}
        tabs.append(
            {
                "tab_key": tab_key,
                "label": label,
                "handling": handling,
                "state_change_possible": state_change,
                "approval_required": handling == "approval_required",
                "final_submit": "blocked_without_approval_phrase" if state_change else "not_applicable",
                "user_can_request": [
                    f"Open {surface['label']} / {label} read-only.",
                    f"Classify visible controls in {surface['label']} / {label}.",
                    f"Prepare a dry-run plan before changing {surface['label']} / {label}.",
                ],
            }
        )
    return tabs


def build_google_domain_taxonomy() -> dict[str, Any]:
    surface_catalog = surfaces.build_surface_catalog()
    tab_summary = tab_registry.build_google_tab_summary()
    action_catalog = workflows.build_action_catalog()
    tab_by_surface = {
        surface_key: tab
        for tab in tab_summary["tabs"]
        for surface_key in tab["surface_keys"]
    }
    actions_by_surface: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in action_catalog["actions"]:
        actions_by_surface[action["surface_key"]].append(action)

    missing = sorted(set(item["key"] for item in surface_catalog["surfaces"]) - set(SURFACE_GROUPS))
    stale = sorted(set(SURFACE_GROUPS) - set(item["key"] for item in surface_catalog["surfaces"]))
    missing_page_tabs = sorted(set(item["key"] for item in surface_catalog["surfaces"]) - set(PAGE_TAB_SPECS))
    stale_page_tabs = sorted(set(PAGE_TAB_SPECS) - set(item["key"] for item in surface_catalog["surfaces"]))
    if missing or stale or missing_page_tabs or stale_page_tabs:
        raise ValueError(
            "Google domain taxonomy mismatch: "
            f"missing={missing}, stale={stale}, "
            f"missing_page_tabs={missing_page_tabs}, stale_page_tabs={stale_page_tabs}"
        )

    domain_items = []
    for surface in surface_catalog["surfaces"]:
        surface_key = surface["key"]
        group_key = SURFACE_GROUPS[surface_key]
        group = GROUPS[group_key]
        actions = actions_by_surface.get(surface_key, [])
        approval_actions = [action for action in actions if action["requires_approval"]]
        read_actions = [action for action in actions if not action["requires_approval"]]
        subsection = SURFACE_SUBSECTIONS[surface_key]
        domain_items.append(
            {
                "surface_key": surface_key,
                "domain_group": group_key,
                "domain_group_label": group["label"],
                "section": group["section"],
                "subsection": subsection,
                "tab_key": tab_by_surface[surface_key]["key"],
                "tab_label": tab_by_surface[surface_key]["label"],
                "host": _host(surface["url"]),
                "url": surface["url"],
                "label": surface["label"],
                "category": surface["category"],
                "access_mode": surface["access_mode"],
                "risk": surface["risk"],
                "status": surface["status"],
                "handling_policy": group["default_handling"],
                "cost_label": group["default_cost_label"],
                "data_classification": _data_classification(surface),
                "approval_level": _approval_level(surface, approval_actions),
                "read_actions": [action["key"] for action in read_actions],
                "approval_actions": [action["key"] for action in approval_actions],
                "user_can_request": _user_can_request(surface, group, subsection),
                "approval_required_for": _approval_required_for(surface, approval_actions),
                "not_allowed": _not_allowed(surface),
                "page_tabs": _page_tabs(surface),
            }
        )

    groups = []
    for group_key, group in sorted(GROUPS.items(), key=lambda item: item[1]["priority"]):
        items = [item for item in domain_items if item["domain_group"] == group_key]
        groups.append(
            {
                "domain_group": group_key,
                "label": group["label"],
                "section": group["section"],
                "priority": group["priority"],
                "surface_count": len(items),
                "hosts": sorted({item["host"] for item in items}),
                "surface_keys": [item["surface_key"] for item in items],
                "approval_surface_count": sum(1 for item in items if item["approval_level"] != "readonly_allowed"),
            }
        )

    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_lock": "each_google_surface_has_exactly_one_domain_group_and_subsection",
        "counts": {
            "domain_groups": len(groups),
            "surfaces": len(domain_items),
            "hosts": len({item["host"] for item in domain_items}),
            "page_tabs": sum(len(item["page_tabs"]) for item in domain_items),
            "approval_surfaces": sum(1 for item in domain_items if item["approval_level"] != "readonly_allowed"),
            "readonly_surfaces": sum(1 for item in domain_items if item["approval_level"] == "readonly_allowed"),
        },
        "execution_policy": {
            "login": "user_present_only_no_credential_replay",
            "read": "local_agent_web_open_url_readonly",
            "state_change": "prepare_then_explicit_approval",
            "final_submit": "blocked_without_approval_phrase",
            "secret_export": "blocked",
            "unknown_domain": "fail_closed",
        },
        "groups": groups,
        "domains": domain_items,
    }


def build_google_page_tab_catalog(surface_key: str | None = None) -> dict[str, Any]:
    taxonomy = build_google_domain_taxonomy()
    domains = taxonomy["domains"]
    if surface_key:
        normalized = surface_key.strip().lower()
        domains = [
            item
            for item in domains
            if item["surface_key"] == normalized
            or item["host"] == normalized
            or item["domain_group"] == normalized
            or item["tab_key"] == normalized
        ]
    return {
        "site_id": "google",
        "filter": surface_key or "",
        "surface_count": len(domains),
        "page_tab_count": sum(len(item["page_tabs"]) for item in domains),
        "surfaces": [
            {
                "surface_key": item["surface_key"],
                "label": item["label"],
                "domain_group": item["domain_group"],
                "tab_key": item["tab_key"],
                "host": item["host"],
                "page_tabs": item["page_tabs"],
            }
            for item in domains
        ],
    }


def save_google_domain_taxonomy(report: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path, Path]:
    report = report or build_google_domain_taxonomy()
    json_path, md_path = save_json_md_report(
        report, DATA_REPORT_DIR, DOC_REPORT_DIR, LATEST_REPORT, "google_domain_taxonomy", _render_markdown
    )
    return report, json_path, md_path


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Google Domain Taxonomy And Handling Labels",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Domain groups: {report['counts']['domain_groups']}",
        f"- Surfaces: {report['counts']['surfaces']}",
        f"- Hosts: {report['counts']['hosts']}",
        f"- Page tabs: {report['counts']['page_tabs']}",
        f"- Approval surfaces: {report['counts']['approval_surfaces']}",
        f"- Read-only surfaces: {report['counts']['readonly_surfaces']}",
        "",
        "## Groups",
        "",
    ]
    for group in report["groups"]:
        lines.append(
            f"- `{group['domain_group']}`: {group['label']} / {group['section']} "
            f"(surfaces={group['surface_count']}, approval={group['approval_surface_count']})"
        )
    lines.extend(["", "## Domain Labels", ""])
    for item in report["domains"]:
        lines.extend(
            [
                f"### {item['label']}",
                f"- Surface: `{item['surface_key']}`",
                f"- Group: `{item['domain_group']}` / `{item['subsection']}`",
                f"- Host: `{item['host']}`",
                f"- Handling: `{item['handling_policy']}`",
                f"- Cost label: `{item['cost_label']}`",
                f"- Data: `{item['data_classification']}`",
                f"- Approval: `{item['approval_level']}`",
                f"- User can request: {'; '.join(item['user_can_request'])}",
                f"- Approval required for: {', '.join(item['approval_required_for'])}",
                f"- Not allowed: {', '.join(item['not_allowed'])}",
                f"- Page tabs: {', '.join(tab['tab_key'] for tab in item['page_tabs'])}",
                "",
            ]
        )
    return "\n".join(lines)


def print_google_domain_taxonomy_summary(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    fields = [("groups", "domain_groups")] + [
        (key, key) for key in ("surfaces", "hosts", "page_tabs", "approval_surfaces", "readonly_surfaces")
    ]
    print_report_summary("Google domain taxonomy", report["counts"], fields, json_path, md_path, LATEST_REPORT)


def print_google_page_tab_summary(catalog: dict[str, Any]) -> None:
    print("=" * 60)
    print("Google page tab labels")
    print("=" * 60)
    print(f"filter: {catalog['filter'] or '(all)'}")
    print(f"surfaces: {catalog['surface_count']}")
    print(f"page_tabs: {catalog['page_tab_count']}")
    for surface in catalog["surfaces"]:
        tabs = ", ".join(item["tab_key"] for item in surface["page_tabs"])
        print(f"- {surface['surface_key']} ({surface['host']}): {tabs}")


def main() -> int:
    report, json_path, md_path = save_google_domain_taxonomy()
    print_google_domain_taxonomy_summary(report, json_path, md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
