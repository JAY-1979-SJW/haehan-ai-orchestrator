from __future__ import annotations

from scripts.sites.readonly_check import build_provider_readonly_check_plan
from scripts.sites.sso_runtime import build_blocked_operation_result, build_login_entry_task, build_subdomain_readonly_task
from scripts.sites.subdomain_registry import get_provider, validate_registry


def test_sso_registry_has_google_and_naver() -> None:
    assert validate_registry() == []
    assert get_provider("google").login_policy == "user_present_sso_profile"
    assert get_provider("naver").login_policy == "user_present_sso_profile"
    assert len(get_provider("google").services) == 12
    assert len(get_provider("naver").services) == 11


def test_login_entry_task_requires_user_present_without_auto_login() -> None:
    task = build_login_entry_task("google")

    assert task["action"] == "web_open_url_readonly"
    assert task["execution_location"] == "local_agent"
    assert task["risk_level"] == "read"
    assert task["metadata"]["auto_login"] is False
    assert task["metadata"]["user_present_required"] is True
    assert task["metadata"]["shared_profile_required"] is True
    assert task["metadata"]["secret_export_allowed"] is False


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

