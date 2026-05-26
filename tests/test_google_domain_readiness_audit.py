from __future__ import annotations

from scripts.google import domain_readiness_audit as audit


def test_google_domain_readiness_covers_all_surfaces() -> None:
    report = audit.build_google_domain_readiness_audit()

    assert report["ok"] is True
    assert report["counts"]["surfaces"] == 50
    assert report["counts"]["domain_groups"] == 10
    assert report["global_policy"]["browser_fallback"] == "user_present_cdp_session_selection_required"


def test_google_domain_readiness_locks_youtube_fallback() -> None:
    report = audit.build_google_domain_readiness_audit()
    by_key = {item["surface_key"]: item for item in report["domains"]}

    assert by_key["youtube"]["fallback_strategy"] == "official_api_then_visible_browser_transcript_summary"
    assert by_key["youtube"]["needs_cdp_session_selection"] is True
    assert by_key["youtube"]["secret_output_allowed"] is False
    assert by_key["youtube"]["must_report_next_step_when_blocked"] is True


def test_google_domain_readiness_locks_cloud_credentials_secret_boundary() -> None:
    report = audit.build_google_domain_readiness_audit()
    by_key = {item["surface_key"]: item for item in report["domains"]}

    credentials = by_key["cloud_apis_credentials"]
    assert credentials["data_classification"] == "secret_sensitive"
    assert credentials["credential_replay_allowed"] is False
    assert credentials["final_submit_without_approval_allowed"] is False


def test_google_domain_readiness_report_can_be_saved() -> None:
    report, path = audit.save_google_domain_readiness_audit()

    assert path.exists()
    assert report["status"] == "ok"
