import json
from pathlib import Path
from uuid import uuid4

from scripts.google import live_inputs, workflows


def _test_dir() -> Path:
    path = Path("tmp") / "google_tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_google_work_action_catalog_covers_business_surfaces():
    catalog = workflows.build_action_catalog()
    keys = {item["key"] for item in catalog["actions"]}

    assert "gmail_send_email" in keys
    assert "youtube_studio_upload_video" in keys
    assert "cloud_create_api_credential" in keys
    assert "cloud_iam_change_role" in keys
    assert "vertex_ai_start_job_or_deploy" in keys
    assert "play_console_prepare_release" in keys
    assert "search_console_submit_indexing" in keys
    assert "business_profile_post_or_update" in keys
    assert catalog["counts"]["approval_actions"] >= 40
    assert catalog["counts"]["adapter_profiles"] == catalog["counts"]["actions"]
    assert catalog["policy"]["approval_phrase"] == workflows.APPROVAL_PHRASE
    assert all(item["execution_adapter"] for item in catalog["actions"])


def test_google_work_prepare_saves_approval_plan(monkeypatch):
    root = _test_dir()
    latest = root / "latest.json"
    prepare_dir = root / "prepares"
    monkeypatch.setattr(workflows, "LATEST_PREPARE", latest)
    monkeypatch.setattr(workflows, "PREPARE_DIR", prepare_dir)

    plan, path = workflows.prepare_action(
        "youtube_studio_upload_video",
        {
            "video_path": "C:/tmp/video.mp4",
            "title": "demo",
            "description": "draft",
            "visibility": "private",
        },
    )

    assert path.exists()
    assert latest.exists()
    assert plan["ready_for_approval"] is True
    assert plan["dry_run"] is True
    assert plan["state_change"] is False
    assert plan["approval"]["required"] is True
    assert plan["approval"]["required_phrase"] == workflows.APPROVAL_PHRASE


def test_google_work_execute_blocks_without_approval(monkeypatch):
    root = _test_dir()
    prepare_dir = root / "prepares"
    execution_dir = root / "executions"
    monkeypatch.setattr(workflows, "PREPARE_DIR", prepare_dir)
    monkeypatch.setattr(workflows, "LATEST_PREPARE", root / "latest.json")
    monkeypatch.setattr(workflows, "EXECUTION_DIR", execution_dir)
    _, plan_path = workflows.prepare_action(
        "gmail_send_email",
        {"to": "a@example.com", "subject": "s", "body": "b"},
    )

    result, result_path = workflows.execute_prepared_action(plan_path)

    assert result["status"] == "blocked"
    assert result["state_change"] is False
    assert "approval" in result["reason"]
    assert result_path.exists()


def test_google_work_execute_approved_handoff_has_adapter_and_verifies(monkeypatch):
    root = _test_dir()
    prepare_dir = root / "prepares"
    execution_dir = root / "executions"
    verification_dir = root / "verifications"
    monkeypatch.setattr(workflows, "PREPARE_DIR", prepare_dir)
    monkeypatch.setattr(workflows, "LATEST_PREPARE", root / "latest.json")
    monkeypatch.setattr(workflows, "EXECUTION_DIR", execution_dir)
    monkeypatch.setattr(workflows, "VERIFICATION_DIR", verification_dir)
    _, plan_path = workflows.prepare_action(
        "cloud_iam_change_role",
        {
            "project": "haehan-ai",
            "principal": "user@example.com",
            "role": "roles/viewer",
            "change": "grant",
        },
    )

    result, result_path = workflows.execute_prepared_action(
        plan_path,
        approved=True,
        confirm=workflows.APPROVAL_PHRASE,
    )
    verification, verification_path = workflows.verify_execution_result(result_path)

    assert result["status"] == "approved_handoff_ready"
    assert result["state_change"] is False
    assert result["adapter"]["adapter_key"] == "google_cloud_iam_adapter"
    assert verification["status"] == "verified"
    assert verification_path.exists()


def test_google_adapter_catalog_has_profile_for_every_action(monkeypatch):
    root = _test_dir()
    latest = root / "latest.json"
    report_dir = root / "reports"
    monkeypatch.setattr(workflows, "LATEST_ADAPTER_CATALOG", latest)
    monkeypatch.setattr(workflows, "ADAPTER_CATALOG_DIR", report_dir)

    catalog = workflows.build_adapter_catalog()
    path = workflows.save_adapter_catalog(catalog)

    action_keys = {action.key for action in workflows.GOOGLE_WORK_ACTIONS}
    adapter_keys = {item["action_key"] for item in catalog["adapters"]}
    assert action_keys == adapter_keys
    assert catalog["counts"]["adapter_profiles"] == len(action_keys)
    assert path.exists()
    assert latest.exists()


def test_google_undeveloped_report_separates_live_input_from_prepare_only(monkeypatch):
    root = _test_dir()
    monkeypatch.setattr(workflows, "LATEST_UNDEVELOPED_REPORT", root / "latest_undeveloped.json")
    monkeypatch.setattr(workflows, "UNDEVELOPED_REPORT_DIR", root / "undeveloped")

    report = workflows.build_undeveloped_report()
    path = workflows.save_undeveloped_report(report)
    readonly = {item["action_key"] for item in report["readonly_complete"]}
    supported = {item["action_key"] for item in report["live_input_supported"]}
    prepare_only = {item["action_key"] for item in report["prepare_or_open_only"]}

    assert "google_home_open" in readonly
    assert "gmail_send_email" in supported
    assert "youtube_studio_upload_video" in supported
    assert "ads_campaign_budget_change" in supported
    assert "gmail_send_email" not in prepare_only
    assert prepare_only == set()
    assert report["counts"]["approval_actions"] == (
        report["counts"]["live_input_supported"] + report["counts"]["prepare_or_open_only"]
    )
    assert report["counts"]["production_final_blocked"] == report["counts"]["approval_actions"]
    assert report["counts"]["missing_adapter_profiles"] == 0
    assert path.exists()
    assert workflows.LATEST_UNDEVELOPED_REPORT.exists()


def test_google_work_action_catalog_save_writes_latest(monkeypatch):
    root = _test_dir()
    latest = root / "latest.json"
    report_dir = root / "reports"
    monkeypatch.setattr(workflows, "LATEST_ACTION_CATALOG", latest)
    monkeypatch.setattr(workflows, "ACTION_CATALOG_DIR", report_dir)

    path = workflows.save_action_catalog()

    assert path.exists()
    assert latest.exists()
    saved = json.loads(latest.read_text(encoding="utf-8"))
    assert saved["site_id"] == "google"
    assert saved["counts"]["actions"] >= 80


def test_google_live_input_manifest_requires_no_final_submit(monkeypatch):
    root = _test_dir()
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(live_inputs, "LIVE_INPUT_MANIFEST_DIR", root / "manifest_results")
    monkeypatch.setattr(live_inputs, "LATEST_LIVE_INPUT_MANIFEST", root / "latest_manifest.json")

    summary, path = live_inputs.run_live_input_manifest(manifest_path, no_final_submit=False)

    assert summary["status"] == "blocked"
    assert summary["state_change_final_button_clicked"] is False
    assert path.exists()


def test_google_live_input_manifest_records_blocked_missing_inputs(monkeypatch):
    root = _test_dir()
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({"items": [{"action_key": "gmail_send_email", "values": {}}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(workflows, "PREPARE_DIR", root / "prepares")
    monkeypatch.setattr(workflows, "LATEST_PREPARE", root / "latest_prepare.json")
    monkeypatch.setattr(live_inputs, "LIVE_INPUT_DIR", root / "live_inputs")
    monkeypatch.setattr(live_inputs, "LATEST_LIVE_INPUT", root / "latest_live.json")
    monkeypatch.setattr(live_inputs, "LIVE_INPUT_MANIFEST_DIR", root / "manifest_results")
    monkeypatch.setattr(live_inputs, "LATEST_LIVE_INPUT_MANIFEST", root / "latest_manifest.json")

    summary, path = live_inputs.run_live_input_manifest(manifest_path, no_final_submit=True)

    assert summary["status"] == "completed"
    assert summary["counts"]["total"] == 1
    assert summary["counts"]["blocked"] == 1
    assert summary["items"][0]["status"] == "blocked_missing_inputs"
    assert path.exists()
    assert live_inputs.LATEST_LIVE_INPUT_MANIFEST.exists()


def test_google_live_input_final_control_policy_lists_required_blocks():
    labels = set(live_inputs.FINAL_CONTROL_LABELS)

    assert "Send" in labels
    assert "Publish" in labels
    assert "Request indexing" in labels
    assert "Release" in labels


def test_google_live_input_timeout_can_be_extended(monkeypatch):
    monkeypatch.setenv("HAEHAN_GOOGLE_LIVE_INPUT_TIMEOUT_MS", "300000")
    monkeypatch.setenv("HAEHAN_GOOGLE_LIVE_INPUT_LOCATOR_TIMEOUT_MS", "30000")

    assert live_inputs._page_timeout(45000) == 300000
    assert live_inputs._locator_timeout(5000) == 30000


def test_youtube_upload_retry_requires_verified_video_input():
    action = {"key": "youtube_studio_upload_video"}

    assert (
        live_inputs._needs_direct_cdp_retry(action, {"filled_fields": [], "skipped_fields": ["video_path"]})
        is True
    )
    assert (
        live_inputs._needs_direct_cdp_retry(action, {"filled_fields": ["video_path"], "skipped_fields": []})
        is False
    )


def test_google_live_input_coverage_tracks_supported_and_remaining(monkeypatch):
    root = _test_dir()
    monkeypatch.setattr(live_inputs, "LIVE_INPUT_COVERAGE_DIR", root / "coverage")
    monkeypatch.setattr(live_inputs, "LATEST_LIVE_INPUT_COVERAGE", root / "latest_coverage.json")

    coverage = live_inputs.build_live_input_coverage()
    path = live_inputs.save_live_input_coverage(coverage)
    supported = {item["action_key"] for item in coverage["supported"]}
    remaining = {item["action_key"] for item in coverage["prepare_or_open_only"]}

    assert "gmail_send_email" in supported
    assert "youtube_studio_upload_video" in supported
    assert "search_console_submit_sitemap" in supported
    assert "cloud_create_api_credential" in supported
    assert "play_console_prepare_release" in supported
    assert "ads_campaign_budget_change" in supported
    assert remaining == set()
    assert coverage["counts"]["approval_actions"] == (
        coverage["counts"]["live_input_supported"] + coverage["counts"]["prepare_or_open_only"]
    )
    assert path.exists()
    assert live_inputs.LATEST_LIVE_INPUT_COVERAGE.exists()
