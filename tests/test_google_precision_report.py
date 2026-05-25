from __future__ import annotations

from scripts.google import precision_report


def test_google_precision_report_builds_domain_page_summary() -> None:
    report = precision_report.build_google_precision_report()

    assert report["site_id"] == "google"
    assert report["scope"]["surfaces"] == 50
    assert report["scope"]["hosts"] >= 30
    assert report["counts"]["final_clicked_count"] == 0
    assert report["counts"]["live_fill_total"] >= 9
    assert "aistudio.google.com" in report["hosts"]
    assert report["ai_usage_labels"]["labels"]["ai_studio"]["safe_ui_label"] == "read_only_or_prepare_until_approval"


def test_google_precision_report_markdown_mentions_ai_labels() -> None:
    report = precision_report.build_google_precision_report()
    markdown = precision_report._render_markdown(report)

    assert "Google AI Usage Labels" in markdown
    assert "Google AI Studio" in markdown
    assert "Host Summary" in markdown
