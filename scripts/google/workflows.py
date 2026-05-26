"""Approval-gated Google business workflow catalog.

The catalog is intentionally broader than the current browser adapters. It
records the workflow contract for every Google business surface so prepare,
approval, execution, verification, and logging stay consistent while the
surface-specific adapters are filled in.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import surfaces

ROOT = Path(__file__).resolve().parents[2]
LATEST_ACTION_CATALOG = ROOT / "data" / "google_work_action_catalog_latest.json"
ACTION_CATALOG_DIR = ROOT / "data" / "google_work_action_catalogs"
LATEST_PREPARE = ROOT / "data" / "google_prepare_latest.json"
PREPARE_DIR = ROOT / "data" / "google_prepares"
EXECUTION_DIR = ROOT / "data" / "google_execution_results"
LATEST_ADAPTER_CATALOG = ROOT / "data" / "google_execution_adapter_catalog_latest.json"
ADAPTER_CATALOG_DIR = ROOT / "data" / "google_execution_adapter_catalogs"
VERIFICATION_DIR = ROOT / "data" / "google_execution_verifications"
LATEST_UNDEVELOPED_REPORT = ROOT / "data" / "google_work_undeveloped_latest.json"
UNDEVELOPED_REPORT_DIR = ROOT / "data" / "google_work_undeveloped_reports"

APPROVAL_PHRASE = "GOOGLE_APPROVED_EXECUTE"


@dataclass(frozen=True)
class GoogleWorkAction:
    key: str
    surface_key: str
    label: str
    operation: str
    target_url: str
    risk: str
    requires_approval: bool
    required_inputs: list[str]
    prepare_outputs: list[str]
    execute_mode: str
    status: str
    approval_phrase: str = APPROVAL_PHRASE


@dataclass(frozen=True)
class GoogleExecutionAdapter:
    action_key: str
    adapter_key: str
    adapter_type: str
    execute_mode: str
    implementation_status: str
    final_state_policy: str
    browser_target_url: str
    evidence_required: list[str]
    verification_checks: list[str]
    rollback_notes: list[str]


def _surface_map() -> dict[str, dict]:
    return {item["key"]: item for item in surfaces.build_surface_catalog()["surfaces"]}


def _read_actions() -> tuple[GoogleWorkAction, ...]:
    actions: list[GoogleWorkAction] = []
    for item in surfaces.build_surface_catalog()["surfaces"]:
        actions.append(
            GoogleWorkAction(
                key=f"{item['key']}_open",
                surface_key=item["key"],
                label=f"Open/read {item['label']}",
                operation="read",
                target_url=item["url"],
                risk=item["risk"],
                requires_approval=False,
                required_inputs=[],
                prepare_outputs=["surface_context", "visible_controls", "completion_notes"],
                execute_mode="browser_open_readonly",
                status="implemented",
            )
        )
    return tuple(actions)


WRITE_ACTIONS: tuple[GoogleWorkAction, ...] = (
    GoogleWorkAction(
        key="gmail_send_email",
        surface_key="gmail",
        label="Prepare and send Gmail message",
        operation="send",
        target_url="https://mail.google.com/mail/u/0/#inbox?compose=new",
        risk="private_data_send",
        requires_approval=True,
        required_inputs=["to", "subject", "body"],
        prepare_outputs=["draft_plan", "recipient_validation", "send_confirmation"],
        execute_mode="api_preferred_or_browser_final_click",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="drive_upload_share_file",
        surface_key="drive",
        label="Upload and share Drive file",
        operation="upload_share",
        target_url="https://drive.google.com/drive/u/0/my-drive",
        risk="private_data_write_share",
        requires_approval=True,
        required_inputs=["local_path", "folder", "share_target", "role"],
        prepare_outputs=["upload_plan", "share_plan", "permission_diff"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="calendar_create_event",
        surface_key="calendar",
        label="Create Calendar event",
        operation="create",
        target_url="https://calendar.google.com/calendar/u/0/r/eventedit",
        risk="private_calendar_write",
        requires_approval=True,
        required_inputs=["title", "start", "end", "attendees"],
        prepare_outputs=["event_payload", "attendee_check", "timezone_check"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="docs_create_edit_document",
        surface_key="docs",
        label="Create or edit Docs document",
        operation="create_edit",
        target_url="https://docs.google.com/document/u/0/",
        risk="private_doc_write",
        requires_approval=True,
        required_inputs=["title", "content_source", "share_target"],
        prepare_outputs=["document_outline", "content_diff", "share_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="sheets_update_cells",
        surface_key="sheets",
        label="Update Sheets cells",
        operation="update",
        target_url="https://docs.google.com/spreadsheets/u/0/",
        risk="private_sheet_write",
        requires_approval=True,
        required_inputs=["spreadsheet", "range", "values"],
        prepare_outputs=["cell_diff", "backup_plan", "validation_summary"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="slides_create_presentation",
        surface_key="slides",
        label="Create Slides presentation",
        operation="create",
        target_url="https://docs.google.com/presentation/u/0/",
        risk="private_presentation_write",
        requires_approval=True,
        required_inputs=["title", "deck_source", "share_target"],
        prepare_outputs=["deck_outline", "asset_manifest", "share_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="forms_create_publish",
        surface_key="forms",
        label="Create and publish Forms form",
        operation="create_publish",
        target_url="https://docs.google.com/forms/u/0/",
        risk="form_publish_write",
        requires_approval=True,
        required_inputs=["title", "questions", "response_destination"],
        prepare_outputs=["form_schema", "response_plan", "publish_checklist"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="meet_create_meeting",
        surface_key="meet",
        label="Create Meet meeting",
        operation="create",
        target_url="https://meet.google.com/",
        risk="meeting_create_or_join",
        requires_approval=True,
        required_inputs=["title", "attendees", "time"],
        prepare_outputs=["meeting_plan", "attendee_check"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="chat_send_message",
        surface_key="chat",
        label="Send Google Chat message",
        operation="send",
        target_url="https://chat.google.com/",
        risk="message_send",
        requires_approval=True,
        required_inputs=["space_or_user", "message"],
        prepare_outputs=["message_preview", "target_check"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="contacts_create_update",
        surface_key="contacts",
        label="Create or update Contact",
        operation="create_update",
        target_url="https://contacts.google.com/",
        risk="contact_data_write",
        requires_approval=True,
        required_inputs=["name", "email", "phone"],
        prepare_outputs=["contact_diff", "duplicate_check"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="keep_create_note",
        surface_key="keep",
        label="Create Keep note",
        operation="create",
        target_url="https://keep.google.com/",
        risk="note_data_write",
        requires_approval=True,
        required_inputs=["title", "body"],
        prepare_outputs=["note_preview"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="tasks_create_task",
        surface_key="tasks",
        label="Create Google Task",
        operation="create",
        target_url="https://tasks.google.com/embed/",
        risk="task_data_write",
        requires_approval=True,
        required_inputs=["title", "due"],
        prepare_outputs=["task_payload", "list_check"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="photos_upload_share",
        surface_key="photos",
        label="Upload and share Google Photos media",
        operation="upload_share",
        target_url="https://photos.google.com/",
        risk="private_media_write_share",
        requires_approval=True,
        required_inputs=["local_path", "album", "share_target"],
        prepare_outputs=["media_manifest", "album_check", "share_plan"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="youtube_comment_or_subscribe",
        surface_key="youtube",
        label="Comment, like, or subscribe on YouTube",
        operation="public_interaction",
        target_url="https://www.youtube.com/",
        risk="public_account_interaction",
        requires_approval=True,
        required_inputs=["target_url", "action", "text"],
        prepare_outputs=["interaction_preview", "account_check"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="youtube_studio_upload_video",
        surface_key="youtube_studio",
        label="Upload YouTube Studio video",
        operation="upload_publish",
        target_url="https://studio.youtube.com/",
        risk="channel_publish_write",
        requires_approval=True,
        required_inputs=["video_path", "title", "description", "visibility"],
        prepare_outputs=["upload_manifest", "metadata_preview", "publish_checklist"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="youtube_studio_edit_video_metadata",
        surface_key="youtube_studio",
        label="Edit YouTube Studio video metadata",
        operation="edit",
        target_url="https://studio.youtube.com/",
        risk="channel_metadata_write",
        requires_approval=True,
        required_inputs=["video_id_or_url", "title", "description", "visibility"],
        prepare_outputs=["metadata_diff", "publish_checklist"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="search_console_submit_indexing",
        surface_key="search_console",
        label="Submit Search Console indexing request",
        operation="submit",
        target_url="https://search.google.com/search-console",
        risk="site_indexing_write",
        requires_approval=True,
        required_inputs=["property", "url"],
        prepare_outputs=["property_check", "url_inspection_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="search_console_submit_sitemap",
        surface_key="search_console",
        label="Submit Search Console sitemap",
        operation="submit",
        target_url="https://search.google.com/search-console/sitemaps",
        risk="site_indexing_write",
        requires_approval=True,
        required_inputs=["property", "sitemap_url"],
        prepare_outputs=["property_check", "sitemap_validation"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="ai_studio_create_api_key",
        surface_key="ai_studio",
        label="Create Google AI Studio API key",
        operation="create_key",
        target_url="https://aistudio.google.com/app/apikey",
        risk="credential_key_write",
        requires_approval=True,
        required_inputs=["project", "key_label"],
        prepare_outputs=["project_check", "key_policy", "secret_storage_plan"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="gemini_submit_prompt",
        surface_key="gemini",
        label="Submit Gemini prompt",
        operation="submit_prompt",
        target_url="https://gemini.google.com/",
        risk="private_prompt_submission",
        requires_approval=True,
        required_inputs=["prompt"],
        prepare_outputs=["prompt_preview", "data_sensitivity_check"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="play_console_prepare_release",
        surface_key="play_console",
        label="Prepare Google Play app release",
        operation="release",
        target_url="https://play.google.com/console/",
        risk="app_release_publish",
        requires_approval=True,
        required_inputs=["app", "track", "artifact_path", "release_notes"],
        prepare_outputs=["release_manifest", "track_check", "policy_checklist"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="firebase_deploy_rules",
        surface_key="firebase_console",
        label="Deploy Firebase rules/config",
        operation="deploy",
        target_url="https://console.firebase.google.com/",
        risk="infra_rules_write",
        requires_approval=True,
        required_inputs=["project", "rules_path", "target"],
        prepare_outputs=["rules_diff", "project_check", "rollback_plan"],
        execute_mode="cli_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_create_api_credential",
        surface_key="cloud_apis_credentials",
        label="Create Google Cloud API credential",
        operation="create_key",
        target_url="https://console.cloud.google.com/apis/credentials",
        risk="credential_key_write",
        requires_approval=True,
        required_inputs=["project", "credential_type", "label"],
        prepare_outputs=["project_check", "credential_policy", "secret_storage_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_iam_change_role",
        surface_key="cloud_iam",
        label="Change Google Cloud IAM role",
        operation="iam_change",
        target_url="https://console.cloud.google.com/iam-admin/iam",
        risk="iam_write",
        requires_approval=True,
        required_inputs=["project", "principal", "role", "change"],
        prepare_outputs=["iam_diff", "least_privilege_check", "rollback_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_billing_budget_or_link",
        surface_key="cloud_billing",
        label="Change Google Cloud billing budget/link",
        operation="billing_change",
        target_url="https://console.cloud.google.com/billing",
        risk="billing_write",
        requires_approval=True,
        required_inputs=["billing_account", "project", "change"],
        prepare_outputs=["billing_diff", "cost_impact_check"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_run_deploy_service",
        surface_key="cloud_run",
        label="Deploy Cloud Run service",
        operation="deploy",
        target_url="https://console.cloud.google.com/run",
        risk="deploy_write",
        requires_approval=True,
        required_inputs=["project", "service", "region", "image"],
        prepare_outputs=["deploy_manifest", "env_diff", "rollback_plan"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="compute_engine_create_vm",
        surface_key="compute_engine",
        label="Create Compute Engine VM",
        operation="create",
        target_url="https://console.cloud.google.com/compute/instances",
        risk="compute_resource_write",
        requires_approval=True,
        required_inputs=["project", "zone", "machine_type", "image"],
        prepare_outputs=["vm_manifest", "cost_check", "network_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_storage_create_bucket",
        surface_key="cloud_storage",
        label="Create Cloud Storage bucket",
        operation="create",
        target_url="https://console.cloud.google.com/storage/browser",
        risk="storage_write",
        requires_approval=True,
        required_inputs=["project", "bucket", "location", "access"],
        prepare_outputs=["bucket_manifest", "iam_check", "lifecycle_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="bigquery_run_query_or_export",
        surface_key="bigquery",
        label="Run BigQuery query or export",
        operation="query_export",
        target_url="https://console.cloud.google.com/bigquery",
        risk="data_query_or_export",
        requires_approval=True,
        required_inputs=["project", "query_or_job", "destination"],
        prepare_outputs=["query_preview", "cost_check", "data_sensitivity_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="gke_apply_change",
        surface_key="gke",
        label="Apply Google Kubernetes Engine change",
        operation="apply",
        target_url="https://console.cloud.google.com/kubernetes",
        risk="cluster_write",
        requires_approval=True,
        required_inputs=["project", "cluster", "manifest_path"],
        prepare_outputs=["manifest_diff", "cluster_check", "rollback_plan"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_sql_change_instance",
        surface_key="cloud_sql",
        label="Change Cloud SQL instance",
        operation="change",
        target_url="https://console.cloud.google.com/sql",
        risk="database_write",
        requires_approval=True,
        required_inputs=["project", "instance", "change"],
        prepare_outputs=["database_diff", "backup_check", "rollback_plan"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="pubsub_create_or_publish",
        surface_key="pubsub",
        label="Create Pub/Sub resource or publish message",
        operation="create_publish",
        target_url="https://console.cloud.google.com/cloudpubsub",
        risk="messaging_write",
        requires_approval=True,
        required_inputs=["project", "topic_or_subscription", "payload"],
        prepare_outputs=["resource_diff", "message_preview"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="secret_manager_create_update",
        surface_key="secret_manager",
        label="Create or update Secret Manager secret",
        operation="create_update",
        target_url="https://console.cloud.google.com/security/secret-manager",
        risk="secret_write",
        requires_approval=True,
        required_inputs=["project", "secret_name", "secret_source"],
        prepare_outputs=["secret_metadata", "redaction_check", "iam_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_logging_create_sink",
        surface_key="cloud_logging",
        label="Create Cloud Logging sink/query config",
        operation="create",
        target_url="https://console.cloud.google.com/logs",
        risk="logs_config_write",
        requires_approval=True,
        required_inputs=["project", "sink_or_query", "destination"],
        prepare_outputs=["log_filter_preview", "destination_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="cloud_monitoring_create_alert",
        surface_key="cloud_monitoring",
        label="Create Cloud Monitoring alert/dashboard",
        operation="create",
        target_url="https://console.cloud.google.com/monitoring",
        risk="monitoring_config_write",
        requires_approval=True,
        required_inputs=["project", "policy_or_dashboard", "notification_channel"],
        prepare_outputs=["policy_preview", "channel_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="vertex_ai_start_job_or_deploy",
        surface_key="vertex_ai",
        label="Start Vertex AI job or deployment",
        operation="job_deploy",
        target_url="https://console.cloud.google.com/vertex-ai",
        risk="ai_cost_deploy_write",
        requires_approval=True,
        required_inputs=["project", "job_or_model", "config"],
        prepare_outputs=["job_manifest", "cost_check", "data_sensitivity_check"],
        execute_mode="cli_or_api_preferred",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="apps_script_deploy",
        surface_key="apps_script",
        label="Deploy Apps Script project",
        operation="deploy",
        target_url="https://script.google.com/home",
        risk="script_deploy_write",
        requires_approval=True,
        required_inputs=["project", "version", "deployment_target"],
        prepare_outputs=["script_diff", "oauth_scope_check", "rollback_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="colab_execute_notebook",
        surface_key="colab",
        label="Execute Colab notebook",
        operation="execute",
        target_url="https://colab.research.google.com/",
        risk="notebook_code_execution",
        requires_approval=True,
        required_inputs=["notebook", "runtime", "parameters"],
        prepare_outputs=["notebook_diff", "runtime_check", "data_sensitivity_check"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="maps_platform_change_key_or_quota",
        surface_key="maps_platform",
        label="Change Maps Platform key/quota",
        operation="change",
        target_url="https://console.cloud.google.com/google/maps-apis",
        risk="api_key_billing_write",
        requires_approval=True,
        required_inputs=["project", "api_or_key", "change"],
        prepare_outputs=["key_or_quota_diff", "billing_check"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="business_profile_post_or_update",
        surface_key="business_profile",
        label="Post or update Google Business Profile",
        operation="post_update",
        target_url="https://business.google.com/",
        risk="public_business_listing_write",
        requires_approval=True,
        required_inputs=["location", "change", "content"],
        prepare_outputs=["listing_diff", "public_preview"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="analytics_export_or_configure",
        surface_key="analytics",
        label="Export or configure Google Analytics",
        operation="export_configure",
        target_url="https://analytics.google.com/",
        risk="analytics_data_or_config",
        requires_approval=True,
        required_inputs=["property", "report_or_change", "destination"],
        prepare_outputs=["report_plan", "config_diff", "share_check"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="tag_manager_publish_version",
        surface_key="tag_manager",
        label="Publish Google Tag Manager version",
        operation="publish",
        target_url="https://tagmanager.google.com/",
        risk="site_tag_publish",
        requires_approval=True,
        required_inputs=["account", "container", "workspace", "version_notes"],
        prepare_outputs=["tag_diff", "preview_check", "rollback_plan"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="ads_campaign_budget_change",
        surface_key="ads",
        label="Change Google Ads campaign/budget",
        operation="campaign_change",
        target_url="https://ads.google.com/",
        risk="ad_spend_write",
        requires_approval=True,
        required_inputs=["account", "campaign", "change"],
        prepare_outputs=["spend_impact", "campaign_diff", "approval_summary"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="merchant_center_product_update",
        surface_key="merchant_center",
        label="Update Merchant Center product/feed",
        operation="product_update",
        target_url="https://merchants.google.com/",
        risk="product_listing_write",
        requires_approval=True,
        required_inputs=["account", "product_or_feed", "change"],
        prepare_outputs=["product_diff", "policy_check", "feed_validation"],
        execute_mode="api_preferred_or_browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="adsense_ad_unit_or_payment_change",
        surface_key="adsense",
        label="Change AdSense ad unit/payment setting",
        operation="change",
        target_url="https://adsense.google.com/adsense/login",
        risk="monetization_config_write",
        requires_approval=True,
        required_inputs=["account", "site", "change"],
        prepare_outputs=["monetization_diff", "payment_safety_check"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
    GoogleWorkAction(
        key="looker_studio_create_or_share_report",
        surface_key="looker_studio",
        label="Create or share Looker Studio report",
        operation="create_share",
        target_url="https://lookerstudio.google.com/",
        risk="report_data_share_write",
        requires_approval=True,
        required_inputs=["report", "data_source", "share_target"],
        prepare_outputs=["report_plan", "data_source_check", "share_plan"],
        execute_mode="browser_handoff",
        status="implemented_gated",
    ),
)


GOOGLE_WORK_ACTIONS: tuple[GoogleWorkAction, ...] = _read_actions() + WRITE_ACTIONS


def build_action_catalog(actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS) -> dict:
    surface_by_key = _surface_map()
    adapters = {adapter.action_key: asdict(adapter) for adapter in build_adapter_profiles(actions)}
    items = []
    for action in actions:
        item = asdict(action)
        item["surface"] = surface_by_key.get(action.surface_key, {})
        item["execution_adapter"] = adapters.get(action.key, {})
        items.append(item)
    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "pipeline": "discover -> plan -> prepare -> approval -> execute -> verify -> log",
            "default_execution": "blocked_until_prepared_and_approved",
            "approval_phrase": APPROVAL_PHRASE,
            "secrets": "redact; never print passwords, tokens, cookies, or secret values",
        },
        "counts": {
            "actions": len(items),
            "read_actions": sum(1 for item in items if not item["requires_approval"]),
            "approval_actions": sum(1 for item in items if item["requires_approval"]),
            "adapter_profiles": len(adapters),
        },
        "actions": items,
    }


def save_action_catalog(catalog: dict | None = None, path: Path | None = None) -> Path:
    catalog = catalog or build_action_catalog()
    ACTION_CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_ACTION_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = path or ACTION_CATALOG_DIR / f"google_work_action_catalog_{timestamp}.json"
    text = json.dumps(catalog, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_ACTION_CATALOG.write_text(text, encoding="utf-8")
    return target


def build_adapter_profiles(
    actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS,
) -> tuple[GoogleExecutionAdapter, ...]:
    profiles: list[GoogleExecutionAdapter] = []
    for action in actions:
        profiles.append(_adapter_profile_for_action(action))
    return tuple(profiles)


def build_adapter_catalog(actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS) -> dict:
    profiles = [asdict(profile) for profile in build_adapter_profiles(actions)]
    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "complete_definition": (
                "every action has an execution adapter profile, evidence "
                "requirements, verification checks, and final state policy"
            ),
            "state_change_default": "blocked_until_explicit_approval",
            "approved_execution": "open target/handoff and require final confirmation evidence",
        },
        "counts": {
            "adapter_profiles": len(profiles),
            "live_browser_capable": sum(1 for item in profiles if "browser" in item["adapter_type"]),
            "approval_handoff": sum(1 for item in profiles if item["final_state_policy"] != "read_only"),
        },
        "adapters": profiles,
    }


def save_adapter_catalog(catalog: dict | None = None, path: Path | None = None) -> Path:
    catalog = catalog or build_adapter_catalog()
    ADAPTER_CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_ADAPTER_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = path or ADAPTER_CATALOG_DIR / f"google_execution_adapter_catalog_{timestamp}.json"
    text = json.dumps(catalog, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_ADAPTER_CATALOG.write_text(text, encoding="utf-8")
    return target


def build_undeveloped_report(actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS) -> dict:
    """Separate implemented Google work from gated or missing development work."""
    action_catalog = build_action_catalog(actions)
    adapter_by_action = {
        adapter["action_key"]: adapter for adapter in build_adapter_catalog(actions)["adapters"]
    }
    from . import live_inputs

    live_coverage = live_inputs.build_live_input_coverage()
    live_supported = {item["action_key"]: item for item in live_coverage["supported"]}
    readonly_complete: list[dict] = []
    live_input_supported: list[dict] = []
    prepare_or_open_only: list[dict] = []
    production_final_blocked: list[dict] = []
    missing_adapter_profiles: list[dict] = []

    for action in action_catalog["actions"]:
        adapter = adapter_by_action.get(action["key"])
        item = {
            "action_key": action["key"],
            "surface_key": action["surface_key"],
            "operation": action["operation"],
            "label": action["label"],
            "requires_approval": action["requires_approval"],
            "required_inputs": action["required_inputs"],
            "target_url": action["target_url"],
            "adapter_key": adapter.get("adapter_key") if adapter else "",
        }
        if not adapter:
            item["development_status"] = "missing_adapter_profile"
            missing_adapter_profiles.append(item)
            continue
        if not action["requires_approval"]:
            item["development_status"] = "implemented_readonly"
            item["final_state_policy"] = "read_only"
            readonly_complete.append(item)
            continue
        item["final_state_policy"] = adapter["final_state_policy"]
        item["production_final_status"] = "not_approved_for_agent_execution"
        production_final_blocked.append(item)
        if action["key"] in live_supported:
            item["development_status"] = "implemented_live_input_no_final_submit"
            item["live_input_mode"] = live_supported[action["key"]]["live_input_mode"]
            live_input_supported.append(item)
        else:
            item["development_status"] = "prepare_or_open_only"
            item["live_input_mode"] = "not_implemented"
            prepare_or_open_only.append(item)

    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "baseline": "Google Home -> My Account -> registered subdomain -> approval URL",
            "read_surfaces": "implemented_readonly",
            "approval_actions": "prepare first, user approval required before any final external state change",
            "live_input": "supported actions may prefill non-secret values with no_final_submit",
            "final_execution": "blocked for agent unless a separate production adapter is explicitly approved",
        },
        "counts": {
            "actions": len(action_catalog["actions"]),
            "readonly_complete": len(readonly_complete),
            "approval_actions": action_catalog["counts"]["approval_actions"],
            "live_input_supported": len(live_input_supported),
            "prepare_or_open_only": len(prepare_or_open_only),
            "production_final_blocked": len(production_final_blocked),
            "missing_adapter_profiles": len(missing_adapter_profiles),
        },
        "readonly_complete": readonly_complete,
        "live_input_supported": live_input_supported,
        "prepare_or_open_only": prepare_or_open_only,
        "production_final_blocked": production_final_blocked,
        "missing_adapter_profiles": missing_adapter_profiles,
    }


def save_undeveloped_report(report: dict | None = None, path: Path | None = None) -> Path:
    report = report or build_undeveloped_report()
    UNDEVELOPED_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_UNDEVELOPED_REPORT.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = path or UNDEVELOPED_REPORT_DIR / f"google_work_undeveloped_{timestamp}.json"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_UNDEVELOPED_REPORT.write_text(text, encoding="utf-8")
    return target


def get_action(action_key: str) -> GoogleWorkAction:
    for action in GOOGLE_WORK_ACTIONS:
        if action.key == action_key:
            return action
    raise KeyError(f"unknown google work action: {action_key}")


def parse_kv_args(args: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for arg in args:
        if "=" not in arg:
            continue
        key, value = arg.split("=", 1)
        if key:
            values[key] = value
    return values


def prepare_action(action_key: str, values: dict[str, str] | None = None) -> tuple[dict, Path]:
    values = values or {}
    action = get_action(action_key)
    missing = [name for name in action.required_inputs if not values.get(name)]
    ready = not missing
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    PREPARE_DIR.mkdir(parents=True, exist_ok=True)
    path = PREPARE_DIR / f"google_prepare_{action.key}_{timestamp}.json"
    command_path = f'"{path}"' if " " in str(path) else str(path)
    plan = {
        "site_id": "google",
        "action": asdict(action),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "ready_for_approval": ready,
        "dry_run": True,
        "state_change": False,
        "provided_inputs": _redact_values(values),
        "missing_inputs": missing,
        "approval": {
            "required": action.requires_approval,
            "approved": False,
            "required_phrase": action.approval_phrase if action.requires_approval else "",
        },
        "execution_gate": {
            "status": "blocked_until_approved" if action.requires_approval else "read_only_ready",
            "execute_mode": action.execute_mode,
            "command": (
                f"python scripts\\cdp_client.py google work execute {command_path} "
                f"--approved --confirm={action.approval_phrase}"
            ),
        },
        "verify_log": {
            "required": ["result_url_or_id", "visible_confirmation", "audit_record"],
            "artifact_dir": str(EXECUTION_DIR),
        },
    }
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_PREPARE.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PREPARE.write_text(text, encoding="utf-8")
    return plan, path


def execute_prepared_action(
    plan_path: str | Path,
    *,
    approved: bool = False,
    confirm: str = "",
    live_open: bool = False,
) -> tuple[dict, Path]:
    path = Path(plan_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    action = plan["action"]
    missing = plan.get("missing_inputs", [])
    required_phrase = plan.get("approval", {}).get("required_phrase", "")
    allowed = bool(approved) and (not required_phrase or confirm == required_phrase) and not missing
    adapter = _adapter_profile_for_action(get_action(action["key"]))
    result = {
        "site_id": "google",
        "action_key": action["key"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "approved": bool(approved),
        "confirm_matched": confirm == required_phrase if required_phrase else True,
        "ready_for_approval": bool(plan.get("ready_for_approval")),
        "state_change": False,
        "status": "blocked",
        "reason": "",
        "target_url": action["target_url"],
        "execute_mode": action["execute_mode"],
        "adapter": asdict(adapter),
        "browser_navigation": {},
        "verification_required": adapter.verification_checks,
    }
    if not allowed:
        if missing:
            result["reason"] = f"missing inputs: {', '.join(missing)}"
        elif action["requires_approval"] and not approved:
            result["reason"] = "approval flag required"
        elif action["requires_approval"] and confirm != required_phrase:
            result["reason"] = "approval phrase mismatch"
        else:
            result["reason"] = "execution gate blocked"
    else:
        result["status"] = "approved_handoff_ready"
        result["reason"] = (
            "approval accepted; surface-specific adapter or manual final "
            "confirmation may now run under audit logging"
        )
        result["state_change"] = False
        result["next_step"] = action["target_url"]
        if live_open:
            result["browser_navigation"] = _open_target_readonly(action["target_url"])
    EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = EXECUTION_DIR / f"google_execute_{action['key']}_{timestamp}.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, target


def verify_execution_result(result_path: str | Path) -> tuple[dict, Path]:
    path = Path(result_path)
    result = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "has_action_key": bool(result.get("action_key")),
        "has_status": bool(result.get("status")),
        "state_change_false_until_final_confirmation": result.get("state_change") is False,
        "adapter_profile_present": bool(result.get("adapter", {}).get("adapter_key")),
        "blocked_or_handoff_state": result.get("status") in {"blocked", "approved_handoff_ready"},
    }
    verification = {
        "site_id": "google",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "result_path": str(path),
        "action_key": result.get("action_key"),
        "status": "verified" if all(checks.values()) else "failed",
        "checks": checks,
        "next_required_evidence": result.get("verification_required", []),
    }
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = VERIFICATION_DIR / f"google_verify_{result.get('action_key', 'unknown')}_{timestamp}.json"
    target.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    return verification, target


def print_action_summary(catalog: dict, path: Path) -> None:
    print("=" * 60)
    print("Google work action catalog")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_ACTION_CATALOG}")
    print(f"actions: {catalog['counts']['actions']}")
    print(f"read_actions: {catalog['counts']['read_actions']}")
    print(f"approval_actions: {catalog['counts']['approval_actions']}")
    print(f"adapter_profiles: {catalog['counts']['adapter_profiles']}")
    for item in catalog["actions"]:
        gate = "approval" if item["requires_approval"] else "read"
        print(f"- {item['key']}: {item['surface_key']} [{gate}] {item['status']}")


def print_adapter_summary(catalog: dict, path: Path) -> None:
    print("=" * 60)
    print("Google execution adapter catalog")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_ADAPTER_CATALOG}")
    print(f"adapter_profiles: {catalog['counts']['adapter_profiles']}")
    print(f"live_browser_capable: {catalog['counts']['live_browser_capable']}")
    print(f"approval_handoff: {catalog['counts']['approval_handoff']}")
    for item in catalog["adapters"]:
        print(
            f"- {item['action_key']}: {item['adapter_key']} "
            f"[{item['implementation_status']}]"
        )


def print_undeveloped_summary(report: dict, path: Path) -> None:
    print("=" * 60)
    print("Google undeveloped work report")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_UNDEVELOPED_REPORT}")
    print(f"actions: {report['counts']['actions']}")
    print(f"readonly_complete: {report['counts']['readonly_complete']}")
    print(f"approval_actions: {report['counts']['approval_actions']}")
    print(f"live_input_supported: {report['counts']['live_input_supported']}")
    print(f"prepare_or_open_only: {report['counts']['prepare_or_open_only']}")
    print(f"production_final_blocked: {report['counts']['production_final_blocked']}")
    print(f"missing_adapter_profiles: {report['counts']['missing_adapter_profiles']}")
    print("prepare_or_open_only:")
    for item in report["prepare_or_open_only"]:
        print(f"- {item['action_key']}: {item['surface_key']} {item['operation']}")


def _redact_values(values: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    secret_markers = ("password", "token", "secret", "cookie", "key")
    for key, value in values.items():
        if any(marker in key.lower() for marker in secret_markers):
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted


def _adapter_profile_for_action(action: GoogleWorkAction) -> GoogleExecutionAdapter:
    if not action.requires_approval:
        return GoogleExecutionAdapter(
            action_key=action.key,
            adapter_key="google_read_surface_adapter",
            adapter_type="browser_readonly",
            execute_mode=action.execute_mode,
            implementation_status="complete",
            final_state_policy="read_only",
            browser_target_url=action.target_url,
            evidence_required=["current_url", "page_title", "visible_surface_marker"],
            verification_checks=["target_url_reached", "no_state_change", "audit_record_saved"],
            rollback_notes=["no rollback required for read-only navigation"],
        )
    adapter_key = _adapter_key(action)
    final_policy = (
        "approval_handoff_final_click_required"
        if "browser" in action.execute_mode or "handoff" in action.execute_mode
        else "approval_required_before_cli_or_api_execution"
    )
    return GoogleExecutionAdapter(
        action_key=action.key,
        adapter_key=adapter_key,
        adapter_type=_adapter_type(action.execute_mode),
        execute_mode=action.execute_mode,
        implementation_status="complete_gated_contract",
        final_state_policy=final_policy,
        browser_target_url=action.target_url,
        evidence_required=[
            "prepared_payload",
            "approval_phrase",
            "account_or_project_context",
            "final_confirmation_marker",
            "audit_record_saved",
        ],
        verification_checks=[
            "approved_flag_present",
            "approval_phrase_matched",
            "missing_inputs_empty",
            "state_change_false_until_final_confirmation",
            "result_artifact_saved",
        ],
        rollback_notes=[
            "record target surface before final confirmation",
            "capture confirmation result after final click/API call",
            "use surface rollback plan from prepare_outputs when supported",
        ],
    )


def _adapter_key(action: GoogleWorkAction) -> str:
    explicit = {
        "gmail_send_email": "gmail_send_adapter",
        "youtube_studio_upload_video": "youtube_studio_upload_adapter",
        "youtube_studio_edit_video_metadata": "youtube_studio_metadata_adapter",
        "cloud_iam_change_role": "google_cloud_iam_adapter",
        "cloud_create_api_credential": "google_cloud_credentials_adapter",
        "play_console_prepare_release": "google_play_release_adapter",
        "search_console_submit_indexing": "search_console_indexing_adapter",
        "ai_studio_create_api_key": "ai_studio_key_adapter",
    }
    return explicit.get(action.key, f"{action.surface_key}_{action.operation}_adapter")


def _adapter_type(execute_mode: str) -> str:
    if execute_mode.startswith("cli_or_api"):
        return "cli_or_api_approval_adapter"
    if execute_mode.startswith("cli_or_browser"):
        return "cli_or_browser_approval_adapter"
    if execute_mode.startswith("api_preferred"):
        return "api_preferred_browser_handoff_adapter"
    return "browser_handoff_adapter"


def _open_target_readonly(url: str) -> dict:
    try:
        from scripts.web_connector import get_page

        page = get_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        title = ""
        try:
            title = page.title()
        except Exception:
            title = ""
        return {
            "attempted": True,
            "ok": True,
            "url": page.url,
            "title": title,
            "mode": "readonly_target_open",
        }
    except Exception as exc:
        return {
            "attempted": True,
            "ok": False,
            "error": str(exc),
            "mode": "readonly_target_open",
        }
