from __future__ import annotations

from scripts.google import domain_readiness_audit as audit


def test_google_domain_readiness_covers_all_surfaces() -> None:
    report = audit.build_google_domain_readiness_audit()

    assert report["ok"] is True
    assert report["counts"]["surfaces"] == 50
    assert report["counts"]["domain_groups"] == 10
    assert report["global_policy"]["browser_fallback"] == "user_present_cdp_session_selection_required"
    assert len(report["per_domain_required_checks"]) == 9
    assert all(item["readiness_level"] == "ready" for item in report["domains"])
    assert all(not item["failed_required_checks"] for item in report["domains"])


def test_google_domain_readiness_locks_youtube_fallback() -> None:
    report = audit.build_google_domain_readiness_audit()
    by_key = {item["surface_key"]: item for item in report["domains"]}

    assert by_key["youtube"]["fallback_strategy"] == "official_api_then_visible_browser_transcript_summary"
    assert by_key["youtube"]["needs_cdp_session_selection"] is True
    assert by_key["youtube"]["secret_output_allowed"] is False
    assert by_key["youtube"]["must_report_next_step_when_blocked"] is True
    assert "youtube_like_oauth_or_browser_fallback" in by_key["youtube"]["risk_flags"]
    assert by_key["youtube"]["required_checks"]["browser_fallback_cdp_selection"]["ok"] is True


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
    assert audit.LATEST_DOC_REPORT.exists()
    markdown = audit.LATEST_DOC_REPORT.read_text(encoding="utf-8")
    assert "| `youtube` | `www.youtube.com` |" in markdown
    assert "Browser fallback must use user-present CDP session selection." in markdown


def test_google_domain_readiness_markdown_does_not_create_timestamped_doc(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "REPORT_DIR", tmp_path / "data")
    monkeypatch.setattr(audit, "LATEST_REPORT", tmp_path / "latest.json")
    monkeypatch.setattr(audit, "DOC_REPORT_DIR", tmp_path / "docs")
    monkeypatch.setattr(audit, "LATEST_DOC_REPORT", tmp_path / "docs" / "google_domain_readiness_latest.md")

    audit.save_google_domain_readiness_audit()

    docs = sorted((tmp_path / "docs").glob("*.md"))
    assert docs == [tmp_path / "docs" / "google_domain_readiness_latest.md"]
