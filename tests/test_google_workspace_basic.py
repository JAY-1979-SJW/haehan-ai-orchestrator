from __future__ import annotations

from scripts.google import workspace_basic


def test_workspace_basic_catalog_covers_common_user_surfaces() -> None:
    catalog = workspace_basic.build_basic_feature_catalog()
    surfaces = {item["surface"] for item in catalog["features"]}

    assert catalog["surface_count"] >= 20
    for surface in {
        "gmail",
        "drive",
        "photos",
        "calendar",
        "docs",
        "sheets",
        "meet",
        "chat",
        "contacts",
        "keep",
        "tasks",
        "search",
        "youtube",
        "maps",
        "translate",
        "news",
        "alerts",
        "shopping",
        "account",
        "chrome",
    }:
        assert surface in surfaces
    assert catalog["global_boundaries"]["google_home_required"] is True
    assert catalog["global_boundaries"]["final_send_click_allowed"] is False
    assert catalog["global_boundaries"]["share_or_publish_without_approval_allowed"] is False
    assert catalog["global_boundaries"]["photo_face_location_exif_output_allowed"] is False
    assert catalog["global_boundaries"]["saved_password_output_allowed"] is False
    assert catalog["global_boundaries"]["account_permission_change_allowed"] is False


def test_gmail_read_analyze_is_read_only_with_redacted_outputs() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "gmail",
        "read_analyze",
        {"mail_index": "0"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready"
    assert plan["feature"]["status"] == "read_only"
    assert "redacted_summary" in plan["feature"]["outputs"]
    assert plan["state_change_allowed"] is False


def test_gmail_send_is_user_only_final_action() -> None:
    plan = workspace_basic.build_basic_work_plan("gmail", "send", {"draft": "draft-1"}, google_work_mode="main")

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "user_only_final_action"
    assert plan["final_submit_allowed"] is False


def test_gmail_compose_is_draft_only() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "gmail",
        "compose_draft",
        {"to": "user@example.com", "subject": "hello", "body": "body"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready_until_final_approval"
    assert plan["feature"]["status"] == "draft_only_no_final_submit"
    assert "stop before final send/save/submit" in plan["agent_allowed_steps"]
    assert plan["agent_may_prepare_work"] is True
    assert plan["final_approval_required"] is True
    assert plan["final_submit_allowed"] is False


def test_gmail_compose_after_final_approval_allows_final_submit_boundary() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "gmail",
        "compose_draft",
        {"to": "user@example.com", "subject": "hello", "body": "body"},
        google_work_mode="main",
        final_execution_approved=True,
    )

    assert plan["status"] == "ready_for_final_execution"
    assert plan["final_execution_approved"] is True
    assert plan["final_submit_allowed"] is True


def test_drive_share_requires_approval_and_final_submit_is_blocked() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "drive",
        "share_prepare",
        {"file": "proposal.pdf", "role": "viewer", "target": "client@example.com"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready_until_final_approval"
    assert plan["feature"]["status"] == "approval_required"
    assert plan["state_change_allowed"] is False
    assert plan["final_submit_allowed"] is False


def test_drive_share_after_final_approval_allows_execution_boundary() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "drive",
        "share_prepare",
        {"file": "proposal.pdf", "role": "viewer", "target": "client@example.com"},
        google_work_mode="main",
        final_execution_approved=True,
    )

    assert plan["status"] == "ready_for_final_execution"
    assert plan["state_change_allowed"] is True
    assert plan["final_submit_allowed"] is True


def test_drive_delete_is_user_only() -> None:
    plan = workspace_basic.build_basic_work_plan("drive", "delete", {"file": "old.pdf"}, google_work_mode="main")

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "user_only_final_action"


def test_drive_upload_prepare_requires_approval() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "drive",
        "upload_prepare",
        {"local_path": "C:/Users/user/Documents/report.pdf"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready_until_final_approval"
    assert plan["feature"]["risk"] == "file_upload"
    assert plan["final_submit_allowed"] is False


def test_sheets_recent_is_read_only() -> None:
    plan = workspace_basic.build_basic_work_plan("sheets", "recent", google_work_mode="main")

    assert plan["status"] == "ready"
    assert plan["feature"]["status"] == "read_only"
    assert plan["state_change_allowed"] is False


def test_photos_list_is_read_only_and_sensitive_metadata_is_blocked() -> None:
    catalog = workspace_basic.build_basic_feature_catalog()
    plan = workspace_basic.build_basic_work_plan("photos", "list", google_work_mode="main")

    assert plan["status"] == "ready"
    assert plan["feature"]["status"] == "read_only"
    assert plan["feature"]["risk"] == "private_photo_metadata"
    assert catalog["global_boundaries"]["photo_face_location_exif_output_allowed"] is False


def test_photos_download_requires_approval() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "photos",
        "download_prepare",
        {"photo_or_album": "summer-trip"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready_until_final_approval"
    assert plan["feature"]["risk"] == "private_photo_download"
    assert plan["state_change_allowed"] is False
    assert plan["final_submit_allowed"] is False


def test_photos_share_requires_approval() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "photos",
        "share_prepare",
        {"photo_or_album": "summer-trip", "target": "family@example.com"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready_until_final_approval"
    assert plan["feature"]["risk"] == "private_photo_share"


def test_photos_delete_is_user_only() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "photos",
        "delete",
        {"photo_or_album": "summer-trip"},
        google_work_mode="main",
    )

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "user_only_final_action"


def test_search_web_search_is_read_only() -> None:
    plan = workspace_basic.build_basic_work_plan(
        "search",
        "web_search",
        {"query": "AI 업무 자동화"},
        google_work_mode="main",
    )

    assert plan["status"] == "ready"
    assert plan["feature"]["risk"] == "public_search_results"
    assert "related_queries" in plan["feature"]["outputs"]


def test_youtube_search_is_read_only_but_playlist_save_needs_approval() -> None:
    search_plan = workspace_basic.build_basic_work_plan(
        "youtube",
        "search_videos",
        {"query": "AI browser automation"},
        google_work_mode="main",
    )
    save_plan = workspace_basic.build_basic_work_plan(
        "youtube",
        "playlist_save_prepare",
        {"video_url_or_id": "abc123", "playlist": "watch later"},
        google_work_mode="main",
    )

    assert search_plan["status"] == "ready"
    assert save_plan["status"] == "ready_until_final_approval"
    assert save_plan["final_submit_allowed"] is False


def test_maps_place_search_read_only_and_save_requires_approval() -> None:
    read_plan = workspace_basic.build_basic_work_plan(
        "maps",
        "place_search",
        {"query": "서울역 카페"},
        google_work_mode="main",
    )
    save_plan = workspace_basic.build_basic_work_plan(
        "maps",
        "save_place_prepare",
        {"place": "서울역"},
        google_work_mode="main",
    )

    assert read_plan["status"] == "ready"
    assert save_plan["status"] == "ready_until_final_approval"
    assert save_plan["feature"]["risk"] == "maps_saved_place_state_change"


def test_translate_text_is_read_only_document_translate_requires_approval() -> None:
    text_plan = workspace_basic.build_basic_work_plan(
        "translate",
        "text_translate",
        {"text": "hello", "target_language": "ko"},
        google_work_mode="main",
    )
    doc_plan = workspace_basic.build_basic_work_plan(
        "translate",
        "document_translate_prepare",
        {"local_path": "C:/Users/user/Documents/report.pdf", "target_language": "ko"},
        google_work_mode="main",
    )

    assert text_plan["status"] == "ready"
    assert doc_plan["status"] == "ready_until_final_approval"


def test_news_and_shopping_are_read_only() -> None:
    news_plan = workspace_basic.build_basic_work_plan(
        "news",
        "briefing",
        {"topic": "AI"},
        google_work_mode="main",
    )
    shopping_plan = workspace_basic.build_basic_work_plan(
        "shopping",
        "compare_prices",
        {"query": "노트북"},
        google_work_mode="main",
    )

    assert news_plan["status"] == "ready"
    assert shopping_plan["status"] == "ready"


def test_account_security_read_only_and_revoke_user_only() -> None:
    check_plan = workspace_basic.build_basic_work_plan("account", "security_check", google_work_mode="main")
    revoke_plan = workspace_basic.build_basic_work_plan(
        "account",
        "revoke_access",
        {"app_or_service": "example app"},
        google_work_mode="main",
    )

    assert check_plan["status"] == "ready"
    assert revoke_plan["status"] == "blocked"
    assert revoke_plan["blocked_reason"] == "user_only_final_action"


def test_chrome_password_check_is_user_only() -> None:
    plan = workspace_basic.build_basic_work_plan("chrome", "password_check", google_work_mode="main")

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "user_only_final_action"
    assert workspace_basic.build_basic_feature_catalog()["global_boundaries"]["saved_password_output_allowed"] is False


def test_missing_inputs_block_plan() -> None:
    plan = workspace_basic.build_basic_work_plan("sheets", "update_prepare", {"spreadsheet": "Budget"}, google_work_mode="main")

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "missing_required_inputs"
    assert plan["missing_inputs"] == ["range", "values"]


def test_google_work_mode_is_still_required() -> None:
    plan = workspace_basic.build_basic_work_plan("drive", "list")

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "google_work_mode_required"
