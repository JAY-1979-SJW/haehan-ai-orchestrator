"""Google Workspace basic feature plans.

This module defines the safe automation boundary for common user workflows:
Gmail, Drive, Google Photos, Calendar, Docs, Sheets, Slides, Forms, Meet, Chat,
Contacts, Keep, Tasks, Search, YouTube, Maps, Translate, News, Shopping, and
Account Security. It is intentionally plan-first. State-changing actions are
classified before any browser execution.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from scripts.common.gates.work_mode_gate import build_google_work_mode_policy


READ_ONLY = "read_only"
DRAFT_ONLY = "draft_only_no_final_submit"
APPROVAL_REQUIRED = "approval_required"
USER_ONLY = "user_only"


@dataclass(frozen=True)
class BasicFeature:
    surface: str
    operation: str
    capability: str
    status: str
    risk: str
    required_inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BASIC_FEATURES: tuple[BasicFeature, ...] = (
    BasicFeature("gmail", "list", "read", READ_ONLY, "private_mail_metadata", outputs=("message_previews",)),
    BasicFeature("gmail", "search", "search", READ_ONLY, "private_mail_metadata", required_inputs=("query",), outputs=("message_previews",)),
    BasicFeature("gmail", "read_analyze", "read", READ_ONLY, "private_mail_body", required_inputs=("mail_index",), outputs=("redacted_summary", "action_items")),
    BasicFeature("gmail", "compose_draft", "draft", DRAFT_ONLY, "mail_send_possible", required_inputs=("to", "subject", "body"), outputs=("draft_prefill",)),
    BasicFeature("gmail", "send", "send", USER_ONLY, "mail_send", required_inputs=("draft",)),
    BasicFeature("gmail", "delete", "delete", USER_ONLY, "mail_delete", required_inputs=("mail_index",)),
    BasicFeature("drive", "list", "read", READ_ONLY, "private_file_metadata", outputs=("file_previews",)),
    BasicFeature("drive", "search", "search", READ_ONLY, "private_file_metadata", required_inputs=("query",), outputs=("file_previews",)),
    BasicFeature("drive", "file_info", "read", READ_ONLY, "private_file_metadata", required_inputs=("file_index_or_name",), outputs=("file_metadata",)),
    BasicFeature("drive", "upload_prepare", "upload", APPROVAL_REQUIRED, "file_upload", required_inputs=("local_path",), outputs=("upload_plan",)),
    BasicFeature("drive", "share_prepare", "share", APPROVAL_REQUIRED, "file_share", required_inputs=("file", "role", "target"), outputs=("share_plan",)),
    BasicFeature("drive", "delete", "delete", USER_ONLY, "file_delete", required_inputs=("file",)),
    BasicFeature("photos", "list", "read", READ_ONLY, "private_photo_metadata", outputs=("photo_previews",)),
    BasicFeature("photos", "search", "search", READ_ONLY, "private_photo_metadata", required_inputs=("query",), outputs=("photo_previews",)),
    BasicFeature("photos", "album_list", "read", READ_ONLY, "private_photo_album_metadata", outputs=("album_previews",)),
    BasicFeature("photos", "download_prepare", "download", APPROVAL_REQUIRED, "private_photo_download", required_inputs=("photo_or_album",), outputs=("download_plan",)),
    BasicFeature("photos", "share_prepare", "share", APPROVAL_REQUIRED, "private_photo_share", required_inputs=("photo_or_album", "target"), outputs=("share_plan",)),
    BasicFeature("photos", "upload_prepare", "upload", APPROVAL_REQUIRED, "private_photo_upload", required_inputs=("local_path",), outputs=("upload_plan",)),
    BasicFeature("photos", "delete", "delete", USER_ONLY, "private_photo_delete", required_inputs=("photo_or_album",)),
    BasicFeature("calendar", "today", "read", READ_ONLY, "private_calendar_metadata", outputs=("event_previews",)),
    BasicFeature("calendar", "search", "search", READ_ONLY, "private_calendar_metadata", required_inputs=("query",), outputs=("event_previews",)),
    BasicFeature("calendar", "create_prepare", "draft", APPROVAL_REQUIRED, "calendar_create", required_inputs=("title", "time", "attendees"), outputs=("event_draft",)),
    BasicFeature("docs", "recent", "read", READ_ONLY, "private_doc_metadata", outputs=("doc_previews",)),
    BasicFeature("docs", "create_prepare", "draft", APPROVAL_REQUIRED, "doc_create_or_edit", required_inputs=("title", "body"), outputs=("doc_draft_plan",)),
    BasicFeature("sheets", "recent", "read", READ_ONLY, "private_sheet_metadata", outputs=("sheet_previews",)),
    BasicFeature("sheets", "update_prepare", "draft", APPROVAL_REQUIRED, "sheet_cell_update", required_inputs=("spreadsheet", "range", "values"), outputs=("cell_update_plan",)),
    BasicFeature("slides", "recent", "read", READ_ONLY, "private_slide_metadata", outputs=("slide_previews",)),
    BasicFeature("forms", "recent", "read", READ_ONLY, "private_form_metadata", outputs=("form_previews",)),
    BasicFeature("meet", "meeting_prepare", "draft", APPROVAL_REQUIRED, "meeting_create", required_inputs=("title", "time"), outputs=("meeting_plan",)),
    BasicFeature("chat", "spaces_list", "read", READ_ONLY, "private_chat_metadata", outputs=("space_previews",)),
    BasicFeature("chat", "message_draft", "draft", DRAFT_ONLY, "chat_send_possible", required_inputs=("space", "message"), outputs=("message_draft",)),
    BasicFeature("contacts", "list", "read", READ_ONLY, "private_contact_metadata", outputs=("contact_previews",)),
    BasicFeature("contacts", "create_prepare", "draft", APPROVAL_REQUIRED, "contact_create", required_inputs=("name", "email_or_phone"), outputs=("contact_plan",)),
    BasicFeature("keep", "list", "read", READ_ONLY, "private_note_metadata", outputs=("note_previews",)),
    BasicFeature("keep", "note_draft", "draft", DRAFT_ONLY, "note_create_possible", required_inputs=("title", "body"), outputs=("note_draft",)),
    BasicFeature("tasks", "list", "read", READ_ONLY, "private_task_metadata", outputs=("task_previews",)),
    BasicFeature("tasks", "task_draft", "draft", DRAFT_ONLY, "task_create_possible", required_inputs=("title",), outputs=("task_draft",)),
    BasicFeature("search", "web_search", "search", READ_ONLY, "public_search_results", required_inputs=("query",), outputs=("result_previews", "related_queries")),
    BasicFeature("search", "related_queries", "search", READ_ONLY, "public_search_trends", required_inputs=("query",), outputs=("related_queries",)),
    BasicFeature("search", "save_result_prepare", "save", APPROVAL_REQUIRED, "saved_search_or_bookmark", required_inputs=("result_url",), outputs=("save_plan",)),
    BasicFeature("youtube", "search_videos", "search", READ_ONLY, "public_video_metadata", required_inputs=("query",), outputs=("video_previews",)),
    BasicFeature("youtube", "summarize_video_prepare", "read", READ_ONLY, "public_or_user_provided_transcript", required_inputs=("video_url_or_id",), outputs=("summary_plan",)),
    BasicFeature("youtube", "playlist_save_prepare", "save", APPROVAL_REQUIRED, "youtube_playlist_state_change", required_inputs=("video_url_or_id", "playlist"), outputs=("playlist_save_plan",)),
    BasicFeature("maps", "place_search", "search", READ_ONLY, "public_place_metadata", required_inputs=("query",), outputs=("place_previews",)),
    BasicFeature("maps", "route_check", "read", READ_ONLY, "location_route_context", required_inputs=("origin", "destination"), outputs=("route_preview",)),
    BasicFeature("maps", "save_place_prepare", "save", APPROVAL_REQUIRED, "maps_saved_place_state_change", required_inputs=("place",), outputs=("save_place_plan",)),
    BasicFeature("translate", "text_translate", "read", READ_ONLY, "text_translation", required_inputs=("text", "target_language"), outputs=("translation",)),
    BasicFeature("translate", "document_translate_prepare", "draft", APPROVAL_REQUIRED, "document_upload_translation", required_inputs=("local_path", "target_language"), outputs=("translation_plan",)),
    BasicFeature("news", "search_news", "search", READ_ONLY, "public_news_metadata", required_inputs=("query",), outputs=("news_previews",)),
    BasicFeature("news", "briefing", "read", READ_ONLY, "public_news_summary", required_inputs=("topic",), outputs=("briefing_summary",)),
    BasicFeature("alerts", "create_prepare", "draft", APPROVAL_REQUIRED, "google_alert_create", required_inputs=("query", "delivery"), outputs=("alert_plan",)),
    BasicFeature("shopping", "product_search", "search", READ_ONLY, "public_product_metadata", required_inputs=("query",), outputs=("product_previews",)),
    BasicFeature("shopping", "compare_prices", "read", READ_ONLY, "public_price_comparison", required_inputs=("query",), outputs=("comparison_summary",)),
    BasicFeature("account", "security_check", "read", READ_ONLY, "account_security_metadata", outputs=("security_check_summary",)),
    BasicFeature("account", "connected_apps_check", "read", READ_ONLY, "account_permission_metadata", outputs=("connected_apps_summary",)),
    BasicFeature("account", "revoke_access", "permission", USER_ONLY, "account_permission_revoke", required_inputs=("app_or_service",)),
    BasicFeature("chrome", "bookmarks_check", "read", READ_ONLY, "browser_bookmark_metadata", outputs=("bookmark_previews",)),
    BasicFeature("chrome", "history_search", "search", READ_ONLY, "browser_history_metadata", required_inputs=("query",), outputs=("history_previews",)),
    BasicFeature("chrome", "password_check", "read", USER_ONLY, "saved_password_sensitive", outputs=("password_check_handoff",)),
)


def build_basic_feature_catalog() -> dict[str, Any]:
    features = [feature.to_dict() for feature in BASIC_FEATURES]
    return {
        "schema_version": 1,
        "surface_count": len({item["surface"] for item in features}),
        "feature_count": len(features),
        "features": features,
        "status_counts": {
            READ_ONLY: sum(1 for item in features if item["status"] == READ_ONLY),
            DRAFT_ONLY: sum(1 for item in features if item["status"] == DRAFT_ONLY),
            APPROVAL_REQUIRED: sum(1 for item in features if item["status"] == APPROVAL_REQUIRED),
            USER_ONLY: sum(1 for item in features if item["status"] == USER_ONLY),
        },
        "global_boundaries": {
            "google_home_required": True,
            "raw_secret_output_allowed": False,
            "final_send_click_allowed": False,
            "file_delete_allowed": False,
            "photo_download_without_approval_allowed": False,
            "photo_share_without_approval_allowed": False,
            "photo_delete_allowed": False,
            "photo_face_location_exif_output_allowed": False,
            "account_permission_change_allowed": False,
            "saved_password_output_allowed": False,
            "maps_location_history_output_allowed": False,
            "youtube_playlist_change_without_approval_allowed": False,
            "google_alert_create_without_approval_allowed": False,
            "share_or_publish_without_approval_allowed": False,
        },
    }


def get_basic_feature(surface: str, operation: str) -> BasicFeature:
    for feature in BASIC_FEATURES:
        if feature.surface == surface and feature.operation == operation:
            return feature
    raise KeyError(f"unknown workspace basic feature: {surface}.{operation}")


def build_basic_work_plan(
    surface: str,
    operation: str,
    values: dict[str, str] | None = None,
    *,
    google_work_mode: str | None = None,
    background_approved: bool = False,
    final_execution_approved: bool = False,
) -> dict[str, Any]:
    values = values or {}
    work_mode_policy = build_google_work_mode_policy(
        google_work_mode,
        background_approved=background_approved,
    )
    try:
        feature = get_basic_feature(surface, operation)
    except KeyError as exc:
        return {
            "schema_version": 1,
            "status": "blocked",
            "blocked_reason": "unknown_workspace_basic_feature",
            "error": str(exc),
        }

    missing = [name for name in feature.required_inputs if not str(values.get(name, "")).strip()]
    blocked_reason = ""
    if work_mode_policy["status"] == "blocked":
        blocked_reason = work_mode_policy["blocked_reason"]
    elif feature.status == USER_ONLY:
        blocked_reason = "user_only_final_action"
    elif missing:
        blocked_reason = "missing_required_inputs"

    status = "blocked" if blocked_reason else "ready"
    if status == "ready" and feature.status in {APPROVAL_REQUIRED, DRAFT_ONLY}:
        status = "ready_for_final_execution" if final_execution_approved else "ready_until_final_approval"

    return {
        "schema_version": 1,
        "workflow": "google_workspace_basic_work_plan",
        "status": status,
        "blocked_reason": blocked_reason,
        "surface": surface,
        "operation": operation,
        "feature": feature.to_dict(),
        "google_work_mode_policy": work_mode_policy,
        "google_work_mode": work_mode_policy["mode"],
        "missing_inputs": missing,
        "provided_inputs": sorted(values.keys()),
        "agent_may_prepare_work": not bool(blocked_reason),
        "final_approval_required": feature.status in {DRAFT_ONLY, APPROVAL_REQUIRED, USER_ONLY},
        "final_execution_approved": bool(final_execution_approved),
        "state_change_allowed": bool(final_execution_approved and feature.status == APPROVAL_REQUIRED and not blocked_reason),
        "final_submit_allowed": bool(final_execution_approved and feature.status in {DRAFT_ONLY, APPROVAL_REQUIRED} and not blocked_reason),
        "agent_allowed_steps": _agent_allowed_steps(feature),
        "user_only_steps": _user_only_steps(feature),
    }


def _agent_allowed_steps(feature: BasicFeature) -> list[str]:
    if feature.status == READ_ONLY:
        return ["open through Google Home", "read visible metadata", "write redacted summary"]
    if feature.status == DRAFT_ONLY:
        return ["open through Google Home", "fill draft fields", "stop before final send/save/submit"]
    if feature.status == APPROVAL_REQUIRED:
        return ["prepare inputs", "write approval summary", "stop before final state-changing control"]
    return ["write handoff summary only"]


def _user_only_steps(feature: BasicFeature) -> list[str]:
    if feature.status == USER_ONLY:
        return ["perform this final state-changing action directly in the browser"]
    if feature.status == APPROVAL_REQUIRED:
        return ["review approval summary", "click final state-changing control if approved"]
    if feature.status == DRAFT_ONLY:
        return ["review draft", "click final send/save/submit if approved"]
    return []


__all__ = [
    "READ_ONLY",
    "DRAFT_ONLY",
    "APPROVAL_REQUIRED",
    "USER_ONLY",
    "BASIC_FEATURES",
    "build_basic_feature_catalog",
    "build_basic_work_plan",
    "get_basic_feature",
]
