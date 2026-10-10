from __future__ import annotations

from importlib import import_module

from scripts.google.common import tab_logic, tab_registry


def test_google_tab_logic_catalog_exposes_all_locked_tabs() -> None:
    catalog = tab_logic.build_all_tab_logic_catalog()

    assert catalog["site_id"] == "google"
    assert catalog["tab_count"] == 9
    assert [tab["tab_key"] for tab in catalog["tabs"]] == [tab.key for tab in tab_registry.GOOGLE_TABS]
    assert all(tab["execution_policy"]["unknown_host"] == "fail_closed" for tab in catalog["tabs"])
    assert all(tab["execution_policy"]["secret_export"] == "blocked" for tab in catalog["tabs"])
    assert all(tab["user_guidance"]["user_can_request"] for tab in catalog["tabs"])


def test_each_google_tab_package_exposes_common_logic_api() -> None:
    for tab in tab_registry.GOOGLE_TABS:
        module = import_module(tab.owner_package)

        assert module.TAB_KEY == tab.key
        assert module.summary()["key"] == tab.key
        assert module.catalog()["tab_key"] == tab.key
        assert callable(module.classify_operation)


def test_workspace_tab_read_and_write_boundaries() -> None:
    read = tab_logic.classify_tab_operation("workspace", "gmail", "read")
    write = tab_logic.classify_tab_operation("workspace", "mail.google.com", "send")

    assert read["ok"] is True
    assert read["tab_key"] == "workspace"
    assert read["local_agent_task"]["action"] == "web_open_url_readonly"
    assert write["ok"] is False
    assert write["approval_required"] is True
    assert write["candidate_actions"] == ["gmail_send_email"]
    assert write["local_agent_task"] is None


def test_google_tabs_explain_user_request_scope() -> None:
    cloud = tab_logic.build_tab_logic_catalog("cloud")
    marketing = tab_logic.build_tab_logic_catalog("marketing")

    assert "Open Google Cloud Console surfaces read-only." in cloud["user_guidance"]["user_can_request"]
    assert "API key creation" in cloud["user_guidance"]["approval_required_for"]
    assert "Prepare SEO, indexing, analytics, ads, or reporting plans." in marketing["user_guidance"]["user_can_request"]
    assert "Indexing request" in marketing["user_guidance"]["approval_required_for"]


def test_tab_logic_blocks_host_outside_requested_tab() -> None:
    result = tab_logic.classify_tab_operation("search", "mail.google.com", "read")

    assert result["ok"] is False
    assert result["reason"] == "google_subdomain_not_in_tab_fail_closed"
    assert result["tab_key"] == "search"
    assert result["local_agent_task"] is None


def test_tab_logic_supports_global_user_present_login_boundary() -> None:
    result = tab_logic.classify_tab_operation("identity", "google", "login")

    assert result["ok"] is True
    assert result["operation"] == "login_entry"
    assert result["tab_key"] == "identity"
    assert result["auto_login"] is False
    assert result["credential_replay_allowed"] is False
    assert result["user_present_required"] is True
