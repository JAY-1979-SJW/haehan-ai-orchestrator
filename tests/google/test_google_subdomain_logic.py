from __future__ import annotations

from scripts.google.common import subdomain_logic


def test_google_subdomain_logic_catalog_groups_surfaces_and_actions_by_host() -> None:
    catalog = subdomain_logic.build_google_subdomain_logic_catalog()
    by_host = {item["host"]: item for item in catalog["subdomains"]}
    sequence = catalog["connection_sequence_lock"]

    assert catalog["site_id"] == "google"
    assert catalog["login_policy"] == "user_present_sso_profile"
    assert catalog["auto_login"] is False
    assert catalog["credential_replay_allowed"] is False
    assert catalog["same_profile_subdomain_navigation"] is True
    assert catalog["browser_runtime"] == "managed_local_agent_cdp_profile"
    assert catalog["default_browser_allowed"] is False
    assert [step["stage"] for step in sequence] == [
        "google_home",
        "account_state",
        "target_subdomain",
        "approval_url",
    ]
    assert sequence[0]["url"] == "https://www.google.com/"
    assert sequence[1]["url"] == "https://myaccount.google.com/"
    assert "mail.google.com" in by_host
    assert "gmail" in by_host["mail.google.com"]["surface_keys"]
    assert "gmail_send_email" in by_host["mail.google.com"]["approval_actions"]
    assert by_host["mail.google.com"]["risk_boundary"] == "approval_required_for_state_change"


def test_google_subdomain_read_operation_builds_local_agent_readonly_task() -> None:
    result = subdomain_logic.classify_google_subdomain_operation("gmail", "read")
    task = result["local_agent_task"]

    assert result["ok"] is True
    assert result["state_change"] is False
    assert result["approval_required"] is False
    assert task["action"] == "web_open_url_readonly"
    assert task["execution_location"] == "local_agent"
    assert task["risk_level"] == "read"
    assert task["params"]["target_url_host"] == "mail.google.com"
    assert task["metadata"]["auto_login"] is False
    assert task["metadata"]["user_present_required"] is True
    assert task["metadata"]["secret_export_allowed"] is False


def test_google_subdomain_login_is_user_present_only() -> None:
    result = subdomain_logic.classify_google_subdomain_operation("google", "login")
    task = result["local_agent_task"]

    assert result["ok"] is True
    assert result["operation"] == "login_entry"
    assert result["auto_login"] is False
    assert result["credential_replay_allowed"] is False
    assert result["user_present_required"] is True
    assert result["connection_sequence_lock"][0]["stage"] == "google_home"
    assert task["metadata"]["auto_login"] is False
    assert task["metadata"]["user_present_required"] is True


def test_google_subdomain_state_change_requires_approval_without_task() -> None:
    result = subdomain_logic.classify_google_subdomain_operation("mail.google.com", "send")

    assert result["ok"] is False
    assert result["reason"] == "google_subdomain_operation_requires_approval_gate"
    assert result["state_change"] is True
    assert result["approval_required"] is True
    assert result["approval_phrase"] == "GOOGLE_APPROVED_EXECUTE"
    assert result["candidate_actions"] == ["gmail_send_email"]
    assert result["local_agent_task"] is None


def test_google_subdomain_credentials_and_unknown_hosts_fail_closed() -> None:
    credential = subdomain_logic.classify_google_subdomain_operation("accounts.google.com", "password")
    unknown = subdomain_logic.classify_google_subdomain_operation("unknown.google.example", "read")

    assert credential["ok"] is False
    assert credential["reason"] == "google_login_requires_user_present_no_credential_replay"
    assert credential["local_agent_task"] is None
    assert unknown["ok"] is False
    assert unknown["reason"] == "unknown_google_subdomain_fail_closed"
    assert unknown["local_agent_task"] is None
