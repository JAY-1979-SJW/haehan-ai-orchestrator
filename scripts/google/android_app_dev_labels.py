"""Android app development domain labels for Google developer surfaces."""
from __future__ import annotations

from datetime import date
from typing import Any

VERIFIED_ON = "2026-05-25"

SOURCE_URLS = {
    "android_compose": "https://developer.android.com/compose",
    "android_compose_setup": "https://developer.android.com/develop/ui/compose/setup",
    "play_console_start": "https://support.google.com/googleplay/android-developer/answer/6112435",
    "play_console_internal_testing": "https://play.google.com/console/about/internal-testing/",
    "play_console_service_fee": "https://support.google.com/googleplay/android-developer/answer/112622",
    "firebase_pricing": "https://firebase.google.com/pricing",
    "firebase_pricing_plans": "https://firebase.google.com/docs/projects/billing/firebase-pricing-plans",
    "google_developers_products": "https://developers.google.com/products",
    "chrome_developers": "https://developer.chrome.com/",
    "google_cloud_free": "https://cloud.google.com/free",
    "google_cloud_pricing": "https://cloud.google.com/pricing",
    "vertex_ai_pricing": "https://cloud.google.com/vertex-ai/generative-ai/pricing",
}

ANDROID_APP_DEV_LABELS: dict[str, dict[str, Any]] = {
    "android_developers": {
        "surface_key": "android_developers",
        "host": "developer.android.com",
        "stage": "build",
        "service": "Android Developers",
        "cost_label": "free_documentation_and_tools",
        "free_summary": "Android developer documentation, Jetpack Compose guidance, and Android Studio setup guidance are free to access.",
        "user_can_request": [
            "Find Android app architecture guidance.",
            "Check Jetpack Compose and Material 3 UI guidance.",
            "Prepare Android Studio setup and project scaffolding steps.",
        ],
        "approval_required_for": [],
        "not_allowed": ["Credential handling", "publishing changes"],
        "source_keys": ["android_compose", "android_compose_setup"],
    },
    "play_console": {
        "surface_key": "play_console",
        "host": "play.google.com",
        "stage": "release",
        "service": "Google Play Console",
        "cost_label": "one_time_registration_fee_then_release_tools",
        "free_summary": "Play Console release/testing tools are available after developer registration; internal testing can distribute builds to trusted testers.",
        "paid_summary": "Developer registration has a one-time US$25 fee. Apps or in-app products using Google Play billing can be subject to service fees.",
        "usage_limit_summary": "Internal testing supports up to 100 invited testers and builds are available quickly after being added.",
        "user_can_request": [
            "Prepare internal, closed, open, or production release plans.",
            "Check app listing, testing, policy, and release readiness.",
            "Prepare package name, artifact, release notes, and rollout checklist.",
        ],
        "approval_required_for": ["Developer registration/payment", "package registration", "artifact upload", "release rollout", "store listing changes"],
        "not_allowed": ["Final rollout/release without explicit approval", "payment or identity submission by automation"],
        "source_keys": ["play_console_start", "play_console_internal_testing", "play_console_service_fee"],
    },
    "firebase_console": {
        "surface_key": "firebase_console",
        "host": "console.firebase.google.com",
        "stage": "backend",
        "service": "Firebase",
        "cost_label": "spark_free_blaze_pay_as_you_go",
        "free_summary": "Firebase Spark plan has no-cost products and no payment method requirement for eligible usage.",
        "paid_summary": "Blaze plan links billing for pay-as-you-go usage and paid Google Cloud features; no-cost quotas can still apply.",
        "usage_limit_summary": "Common no-cost products include Analytics, Crashlytics, Cloud Messaging, Remote Config, App Distribution, and others; quotas vary by product.",
        "user_can_request": [
            "Plan Firebase Auth, Firestore/Realtime Database, Hosting, Crashlytics, FCM, Analytics, App Distribution, and Remote Config.",
            "Label which Firebase features are no-cost versus billing-linked.",
            "Prepare Firebase project and release support checklist.",
        ],
        "approval_required_for": ["Billing plan upgrade", "rules deploy", "database/storage destructive change", "secret/config change"],
        "not_allowed": ["Deploy rules or change billing without explicit approval"],
        "source_keys": ["firebase_pricing", "firebase_pricing_plans"],
    },
    "cloud_android_backend": {
        "surface_key": "cloud_console",
        "host": "console.cloud.google.com",
        "stage": "backend_infra",
        "service": "Google Cloud for Android backend",
        "cost_label": "billing_project_required_for_cloud_resources",
        "free_summary": "Some Google Cloud products have free tiers or trial credits, but production resources must be checked per product.",
        "paid_summary": "Cloud Run, Storage, SQL, IAM, APIs/Credentials, Vertex AI, and related services can incur usage-based costs.",
        "usage_limit_summary": "Use project, region, quota, and billing checks before resource creation.",
        "user_can_request": [
            "Prepare Android backend API, storage, auth, logging, monitoring, and AI integration plans.",
            "Check API credentials, IAM, Cloud Run, Storage, SQL, and Monitoring surfaces read-only.",
            "Prepare cost and rollback checklist before infrastructure changes.",
        ],
        "approval_required_for": ["API key creation", "IAM change", "deploy", "resource create/update/delete", "billing change"],
        "not_allowed": ["Cloud state change without approval phrase", "secret value export"],
        "source_keys": ["google_cloud_free", "google_cloud_pricing"],
    },
    "google_developers": {
        "surface_key": "google_developers",
        "host": "developers.google.com",
        "stage": "build",
        "service": "Google for Developers",
        "cost_label": "free_public_documentation_product_index",
        "free_summary": "Google product documentation and API discovery pages are public; product usage costs depend on the selected API.",
        "paid_summary": "Maps, Cloud, AI, and other product APIs can have product-specific quotas, billing, or enablement requirements.",
        "usage_limit_summary": "Treat docs as free read-only; check each API's quota and pricing page before enabling it.",
        "user_can_request": [
            "Find official Google API/product docs for an Android feature.",
            "Map OAuth, Maps, ML, Workspace, and Cloud API integration options.",
            "Prepare API enablement and consent-screen checklists.",
        ],
        "approval_required_for": ["API enablement", "OAuth consent change", "credential creation", "billing-linked API use"],
        "not_allowed": ["Enable APIs or create credentials without explicit approval"],
        "source_keys": ["google_developers_products"],
    },
    "chrome_developers": {
        "surface_key": "chrome_developers",
        "host": "developer.chrome.com",
        "stage": "build",
        "service": "Chrome for Developers",
        "cost_label": "free_public_documentation",
        "free_summary": "Chrome, web platform, PWA, and WebView guidance is public and free to read.",
        "paid_summary": "No Android release fee is tied to reading Chrome developer docs; deployment costs depend on the hosting or store channel used.",
        "usage_limit_summary": "Use for Android WebView, Trusted Web Activity, PWA, and browser compatibility guidance.",
        "user_can_request": [
            "Check Android WebView or PWA guidance.",
            "Map browser compatibility and performance requirements.",
            "Prepare web-to-Android integration notes.",
        ],
        "approval_required_for": [],
        "not_allowed": ["Publish extension/app changes from docs-only surface"],
        "source_keys": ["chrome_developers"],
    },
    "cloud_apis_credentials": {
        "surface_key": "cloud_apis_credentials",
        "host": "console.cloud.google.com",
        "stage": "backend_infra",
        "service": "Google Cloud APIs and Credentials",
        "cost_label": "credential_surface_approval_required",
        "free_summary": "Credential pages can be inspected read-only; creating credentials is a state-changing operation.",
        "paid_summary": "The APIs used by credentials may incur charges depending on product, quota, and billing project.",
        "usage_limit_summary": "Confirm project, API, OAuth consent, referrer/package restrictions, and rotation policy before creating credentials.",
        "user_can_request": [
            "Prepare API key or OAuth credential creation plans.",
            "Check package name/SHA certificate restriction requirements.",
            "Prepare secret storage and rotation checklist.",
        ],
        "approval_required_for": ["credential create/update/delete", "OAuth consent publish", "API enablement"],
        "not_allowed": ["Export secrets", "create unrestricted keys without approval"],
        "source_keys": ["google_cloud_pricing"],
    },
    "cloud_iam": {
        "surface_key": "cloud_iam",
        "host": "console.cloud.google.com",
        "stage": "backend_infra",
        "service": "Google Cloud IAM",
        "cost_label": "access_control_surface_approval_required",
        "free_summary": "IAM can be inspected read-only to understand access and service accounts.",
        "paid_summary": "IAM itself is access control, but roles can permit paid resource creation or data access.",
        "usage_limit_summary": "Use least privilege and record project/member/role before any change.",
        "user_can_request": [
            "Review service account and Android backend access design.",
            "Prepare least-privilege role mapping.",
            "Prepare access rollback checklist.",
        ],
        "approval_required_for": ["role grant/revoke", "service account key creation", "policy binding change"],
        "not_allowed": ["Grant broad roles without explicit approval", "export service account keys"],
        "source_keys": ["google_cloud_pricing"],
    },
    "cloud_run": {
        "surface_key": "cloud_run",
        "host": "console.cloud.google.com",
        "stage": "backend_infra",
        "service": "Cloud Run",
        "cost_label": "usage_based_backend_runtime",
        "free_summary": "Cloud Run may include product-specific free usage, but project billing and quotas must be checked before deployment.",
        "paid_summary": "Runtime, networking, build, logging, and dependent services can incur charges.",
        "usage_limit_summary": "Confirm region, min instances, concurrency, ingress, service account, and rollback before deploy.",
        "user_can_request": [
            "Plan Android backend API deployment.",
            "Prepare Cloud Run environment variable and secret design.",
            "Prepare smoke test and rollback steps.",
        ],
        "approval_required_for": ["service deploy", "traffic shift", "env/secret change", "delete service"],
        "not_allowed": ["Deploy or shift traffic without explicit approval"],
        "source_keys": ["google_cloud_pricing"],
    },
    "cloud_storage": {
        "surface_key": "cloud_storage",
        "host": "console.cloud.google.com",
        "stage": "backend_infra",
        "service": "Cloud Storage",
        "cost_label": "usage_based_storage",
        "free_summary": "Storage configuration can be inspected read-only; no-cost usage depends on product/region/quota.",
        "paid_summary": "Stored data, operations, retrieval, egress, and lifecycle choices can incur charges.",
        "usage_limit_summary": "Confirm bucket, region, IAM, lifecycle, public access, and retention before change.",
        "user_can_request": [
            "Plan Android file/media storage.",
            "Prepare upload/download permission model.",
            "Prepare lifecycle and retention policy.",
        ],
        "approval_required_for": ["bucket create/delete", "IAM/public access change", "object delete", "retention/lifecycle change"],
        "not_allowed": ["Expose buckets publicly without explicit approval"],
        "source_keys": ["google_cloud_pricing"],
    },
    "cloud_logging": {
        "surface_key": "cloud_logging",
        "host": "console.cloud.google.com",
        "stage": "operate",
        "service": "Cloud Logging",
        "cost_label": "operations_observability_usage_based",
        "free_summary": "Logs can be inspected read-only if access exists.",
        "paid_summary": "Ingestion, storage, routing, and retention can have product-specific pricing.",
        "usage_limit_summary": "Define log level, retention, redaction, and alerting policy before production.",
        "user_can_request": [
            "Plan Android backend log inspection.",
            "Prepare privacy-safe logging rules.",
            "Prepare incident triage views.",
        ],
        "approval_required_for": ["sink creation", "retention change", "alerting/routing change"],
        "not_allowed": ["Export sensitive logs without approval"],
        "source_keys": ["google_cloud_pricing"],
    },
    "cloud_monitoring": {
        "surface_key": "cloud_monitoring",
        "host": "console.cloud.google.com",
        "stage": "operate",
        "service": "Cloud Monitoring",
        "cost_label": "operations_observability_usage_based",
        "free_summary": "Dashboards and metrics can be inspected read-only if access exists.",
        "paid_summary": "Metric ingestion, uptime checks, alerting channels, and dependent services can have product-specific pricing.",
        "usage_limit_summary": "Define SLOs, alert thresholds, notification channels, and escalation rules before production.",
        "user_can_request": [
            "Plan Android backend uptime and error monitoring.",
            "Prepare SLO and alert rules.",
            "Prepare dashboard requirements.",
        ],
        "approval_required_for": ["alert policy change", "notification channel change", "dashboard create/update"],
        "not_allowed": ["Create noisy alerts or external notifications without approval"],
        "source_keys": ["google_cloud_pricing"],
    },
    "vertex_ai": {
        "surface_key": "vertex_ai",
        "host": "console.cloud.google.com",
        "stage": "ai_integration",
        "service": "Vertex AI",
        "cost_label": "usage_based_ai_cloud_service",
        "free_summary": "Docs and console inspection are read-only; model usage must be checked against current Vertex AI pricing and quotas.",
        "paid_summary": "Generative AI calls, tuning, batch jobs, endpoints, storage, and logging can incur charges.",
        "usage_limit_summary": "Confirm model, region, quota, safety policy, data handling, and budget controls before calling or deploying models.",
        "user_can_request": [
            "Plan Android AI feature integration.",
            "Prepare model, quota, safety, and cost checklist.",
            "Prepare server-side proxy and API-key protection design.",
        ],
        "approval_required_for": ["prompt/job execution", "model deploy", "endpoint create/update", "quota or billing change"],
        "not_allowed": ["Run paid model jobs or expose keys without explicit approval"],
        "source_keys": ["vertex_ai_pricing", "google_cloud_pricing"],
    },
}

ANDROID_APP_DEV_STAGES = [
    {
        "stage": "build",
        "surface_keys": ["android_developers", "google_developers", "chrome_developers"],
        "output": "app architecture, UI, local build, docs mapping",
    },
    {
        "stage": "backend",
        "surface_keys": ["firebase_console", "cloud_console"],
        "output": "auth, data, messaging, analytics, crash, API/backend plan",
    },
    {
        "stage": "test",
        "surface_keys": ["play_console", "firebase_console"],
        "output": "internal testing, app distribution, QA checklist",
    },
    {
        "stage": "release",
        "surface_keys": ["play_console"],
        "output": "package name, artifact, listing, policy, release plan",
    },
    {
        "stage": "operate",
        "surface_keys": ["play_console", "firebase_console", "cloud_monitoring", "cloud_logging"],
        "output": "vitals, crash, analytics, logs, monitoring, rollout status",
    },
]


def build_android_app_dev_labels() -> dict[str, Any]:
    return {
        "site_id": "google",
        "tab_key": "developer",
        "domain_group": "android_app_development",
        "verified_on": VERIFIED_ON,
        "generated_on": date.today().isoformat(),
        "source_urls": SOURCE_URLS,
        "labels": ANDROID_APP_DEV_LABELS,
        "stages": ANDROID_APP_DEV_STAGES,
        "ui_policy": {
            "show_cost_badge": True,
            "show_free_limit_badge": True,
            "show_release_gate": True,
            "state_change": "approval_required",
            "secret_export": "blocked",
        },
    }


def label_for_surface(surface_key: str) -> dict[str, Any]:
    for label in ANDROID_APP_DEV_LABELS.values():
        if label["surface_key"] == surface_key:
            return label
    return {
        "surface_key": surface_key,
        "cost_label": "not_android_app_dev_primary_surface",
        "free_summary": "",
        "paid_summary": "",
        "usage_limit_summary": "",
        "source_keys": [],
    }


__all__ = [
    "ANDROID_APP_DEV_LABELS",
    "ANDROID_APP_DEV_STAGES",
    "SOURCE_URLS",
    "build_android_app_dev_labels",
    "label_for_surface",
]
