from tools.audits.google import audit_google_live_input_representative as audit


def test_representative_live_input_preflight_passes():
    report = audit.build_report()

    assert report["status"] == "passed"
    assert report["coverage_counts"]["approval_actions"] == 46
    assert report["coverage_counts"]["live_input_supported"] == 46
    assert report["coverage_counts"]["prepare_or_open_only"] == 0
    assert {item["action_key"] for item in report["representatives"]} == {
        "gmail_send_email",
        "search_console_submit_sitemap",
        "cloud_create_api_credential",
        "cloud_iam_change_role",
    }
    assert all(item["ready_for_approval"] for item in report["representatives"])
    assert all(item["state_change"] is False for item in report["representatives"])
    assert all("--no-final-submit" in item["no_final_submit_command"] for item in report["representatives"])


def test_representative_live_input_markdown_names_policy():
    report = audit.build_report()
    markdown = audit.render_markdown(report)

    assert "External state change: False" in markdown
    assert "Live input supported: 46" in markdown
    assert "--no-final-submit" in markdown
