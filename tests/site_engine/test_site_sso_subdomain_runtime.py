from __future__ import annotations

from pathlib import Path

from scripts.site_engine.readonly_check import build_provider_readonly_check_plan
from scripts.site_engine.sso_runtime import (
    build_blocked_operation_result,
    build_login_entry_task,
    build_occasional_site_login_task,
    build_raw_credential_handoff_rejection,
    build_subdomain_readonly_task,
    dry_run_occasional_site_login_task,
)
from scripts.site_engine.subdomain_registry import get_provider, validate_registry


def test_sso_registry_has_google_and_naver() -> None:
    assert validate_registry() == []
    assert get_provider("google").login_policy == "user_present_sso_profile"
    assert get_provider("naver").login_policy == "user_present_sso_profile"
    assert len(get_provider("google").services) == 12
    assert len(get_provider("naver").services) == 11


def test_login_entry_task_requires_user_present_without_auto_login() -> None:
    task = build_login_entry_task("google")
    metadata = task["metadata"]

    assert task["action"] == "web_open_url_readonly"
    assert task["execution_location"] == "local_agent"
    assert task["risk_level"] == "read"
    assert metadata["auto_login"] is False
    assert metadata["user_present_required"] is True
    assert metadata["shared_profile_required"] is True
    assert metadata["secret_export_allowed"] is False
    assert metadata["sso_connection_policy"]["direct_oauth_entry_allowed"] is False
    assert metadata["oauth_client_policy"]["web_app_client_for_local_cli_allowed"] is False
    assert metadata["oauth_client_policy"]["local_cli_preferred_client_type"] == "desktop_app"
    assert metadata["oauth_client_policy"]["agent_non_secret_prefill_allowed"] is True
    assert metadata["oauth_client_policy"]["final_external_create_requires_user"] is True
    assert metadata["oauth_client_policy"]["request_user_input_when_prefill_blocked"] is True


def test_occasional_site_login_handoff_requires_user_present_without_development() -> None:
    task = build_occasional_site_login_task("https://example.com/", site_label="example")
    metadata = task["metadata"]
    policy = metadata["occasional_site_login_policy"]

    assert task["action"] == "web_open_url_readonly"
    assert task["execution_location"] == "local_agent"
    assert task["risk_level"] == "read"
    assert task["requires_approval"] is False
    assert task["params"]["target_url_host"] == "example.com"
    assert metadata["auto_login"] is False
    assert metadata["user_present_required"] is True
    assert metadata["developed_site_required"] is False
    assert metadata["tool_development_required"] is False
    assert metadata["secret_export_allowed"] is False
    assert policy["user_enters_credentials"] is True
    assert policy["agent_password_or_otp_entry_allowed"] is False
    assert policy["raw_credential_handoff_allowed"] is False
    assert policy["credential_capture_allowed_even_with_user_request"] is False
    assert policy["allowed_agent_login_role"] == "open_login_surface_detect_completion_save_session_only"
    assert policy["readonly_session_check_only"] is True
    assert policy["state_change_allowed"] is False


def test_raw_credential_handoff_is_blocked_even_when_user_requests() -> None:
    result = build_raw_credential_handoff_rejection(site_label="smartstore")

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["agent_may_receive_raw_credentials"] is False
    assert result["agent_may_type_password_or_otp"] is False
    assert result["secret_values_output"] is False
    assert result["allowed_next_step"] == "user_present_login_then_agent_detects_completion_and_saves_domain_session"


def test_occasional_site_login_dry_run_has_no_forbidden_fields() -> None:
    result = dry_run_occasional_site_login_task("https://example.com/login", site_label="example")

    assert result["ok"] is True
    assert result["state_change"] is False
    assert result["contains_forbidden_field"] is False
    assert result["local_agent_task"]["metadata"]["occasional_site_login_policy"]["auto_login"] is False


def test_google_and_naver_subdomain_tasks_share_contract() -> None:
    google = build_subdomain_readonly_task("google", "gmail")
    naver = build_subdomain_readonly_task("naver", "naver_mail")

    for task in (google, naver):
        assert task["action"] == "web_open_url_readonly"
        assert task["execution_location"] == "local_agent"
        assert task["risk_level"] == "read"
        assert task["requires_approval"] is False
        assert task["metadata"]["auto_login"] is False
        assert task["metadata"]["user_present_required"] is True
        assert task["metadata"]["same_profile_subdomain_navigation"] is True
        assert task["metadata"]["sso_connection_policy"]["entry_first"] is True
        assert task["metadata"]["oauth_client_policy"]["redirect_uri_must_match_client_registration"] is True

    assert google["params"]["target_url_host"] == "mail.google.com"
    assert naver["params"]["target_url_host"] == "mail.naver.com"


def test_provider_readonly_check_plan_dry_runs_all_registered_services() -> None:
    google = build_provider_readonly_check_plan("google")
    naver = build_provider_readonly_check_plan("naver")

    assert google["ok"] is True
    assert google["service_count"] == 12
    assert naver["ok"] is True
    assert naver["service_count"] == 11
    assert all(service["contains_forbidden_field"] is False for service in google["services"])
    assert all(service["contains_forbidden_field"] is False for service in naver["services"])


def test_blocked_operation_does_not_create_local_agent_task() -> None:
    blocked = build_blocked_operation_result("naver", "naver_pay", "purchase")

    assert blocked["ok"] is False
    assert blocked["state_change"] is False
    assert blocked["local_agent_task"] is None
    assert blocked["reason"] == "sso_subdomain_operation_requires_separate_approval_gate"
    assert blocked["sso_connection_policy"]["error_code_for_direct_oauth"] == "SSO_DIRECT_OAUTH_ENTRY_BLOCKED"
    assert blocked["oauth_client_policy"]["error_code_for_mismatch"] == "OAUTH_CLIENT_REDIRECT_SCOPE_MISMATCH"


def test_sso_baseline_documents_common_oauth_client_policy() -> None:
    baseline = (Path(__file__).resolve().parents[2] / "docs/baseline/SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE.md").read_text(
        encoding="utf-8"
    )

    assert "direct OAuth URL entry is forbidden" in baseline
    assert "Desktop app OAuth client" in baseline
    assert "agent may prefill non-secret fields" in baseline
    assert "final external create" in baseline
    assert "OAUTH_CLIENT_REDIRECT_SCOPE_MISMATCH" in baseline


def test_sso_baseline_documents_occasional_site_login_handoff() -> None:
    baseline = (Path(__file__).resolve().parents[2] / "docs/baseline/SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE.md").read_text(
        encoding="utf-8"
    )

    assert "Occasional Site Login Handoff" in baseline
    assert "developed site module is not required" in baseline
    assert "user enters credentials directly" in baseline
    assert "read-only session check" in baseline
