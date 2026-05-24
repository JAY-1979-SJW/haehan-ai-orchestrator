from __future__ import annotations

from importlib import import_module

from scripts.google.cloud import registry, router


def test_cloud_registry_preserves_locked_counts() -> None:
    summary = registry.cloud_summary()

    assert summary["surface_count"] == 15
    assert summary["action_count"] == 29
    assert summary["read_action_count"] == 15
    assert summary["approval_action_count"] == 14
    assert summary["hosts"] == ["console.cloud.google.com"]
    assert summary["live_input_supported_actions"] == [
        "cloud_create_api_credential",
        "cloud_iam_change_role",
    ]
    assert len(summary["prepare_or_open_only_approval_actions"]) == 12


def test_cloud_registry_surfaces_are_expected() -> None:
    assert [surface["key"] for surface in registry.list_surfaces()] == [
        "cloud_console",
        "maps_platform",
        "cloud_apis_credentials",
        "cloud_iam",
        "cloud_billing",
        "cloud_run",
        "compute_engine",
        "cloud_storage",
        "bigquery",
        "gke",
        "cloud_sql",
        "pubsub",
        "secret_manager",
        "cloud_logging",
        "cloud_monitoring",
    ]


def test_cloud_registry_approval_actions_are_expected() -> None:
    approval_actions = [
        action["key"]
        for action in registry.list_actions()
        if action["requires_approval"]
    ]

    assert approval_actions == [
        "maps_platform_change_key_or_quota",
        "cloud_create_api_credential",
        "cloud_iam_change_role",
        "cloud_billing_budget_or_link",
        "cloud_run_deploy_service",
        "compute_engine_create_vm",
        "cloud_storage_create_bucket",
        "bigquery_run_query_or_export",
        "gke_apply_change",
        "cloud_sql_change_instance",
        "pubsub_create_or_publish",
        "secret_manager_create_update",
        "cloud_logging_create_sink",
        "cloud_monitoring_create_alert",
    ]


def test_cloud_router_summary_returns_registry() -> None:
    summary = router.run_cloud("summary")

    assert isinstance(summary, dict)
    assert summary["key"] == "cloud"
    assert summary["surface_count"] == 15


def test_cloud_router_rejects_unknown_service() -> None:
    result = router.run_cloud("unknown", "open", [])

    assert result == {
        "ok": False,
        "reason": "unknown_cloud_service",
        "service": "unknown",
    }


def test_cloud_wrappers_are_catalog_only_and_do_not_execute() -> None:
    wrappers = {
        "console": "cloud_console",
        "maps_platform": "maps_platform",
        "api_credentials": "cloud_apis_credentials",
        "iam": "cloud_iam",
        "billing": "cloud_billing",
        "run": "cloud_run",
        "compute": "compute_engine",
        "storage": "cloud_storage",
        "bigquery": "bigquery",
        "gke": "gke",
        "sql": "cloud_sql",
        "pubsub": "pubsub",
        "secret_manager": "secret_manager",
        "logging": "cloud_logging",
        "monitoring": "cloud_monitoring",
    }

    for service, surface_key in wrappers.items():
        module = import_module(f"scripts.google.cloud.{service}")
        result = module.run("dangerous-change", ["private-value"])
        assert result["ok"] is False
        assert result["mode"] == "catalog_only"
        assert result["state_change"] is False
        assert result["execution_allowed"] is False
        assert result["surface"]["key"] == surface_key
        assert "gcloud" in result["forbidden_execution"]
        assert "google_cloud_api" in result["forbidden_execution"]
        assert "browser_final_click" in result["forbidden_execution"]


def test_cloud_wrappers_execute_read_only_open_contracts() -> None:
    wrappers = {
        "console": ("cloud_console", "cloud_console_open"),
        "maps_platform": ("maps_platform", "maps_platform_open"),
        "api_credentials": ("cloud_apis_credentials", "cloud_apis_credentials_open"),
        "iam": ("cloud_iam", "cloud_iam_open"),
        "billing": ("cloud_billing", "cloud_billing_open"),
        "run": ("cloud_run", "cloud_run_open"),
        "compute": ("compute_engine", "compute_engine_open"),
        "storage": ("cloud_storage", "cloud_storage_open"),
        "bigquery": ("bigquery", "bigquery_open"),
        "gke": ("gke", "gke_open"),
        "sql": ("cloud_sql", "cloud_sql_open"),
        "pubsub": ("pubsub", "pubsub_open"),
        "secret_manager": ("secret_manager", "secret_manager_open"),
        "logging": ("cloud_logging", "cloud_logging_open"),
        "monitoring": ("cloud_monitoring", "cloud_monitoring_open"),
    }

    for service, (surface_key, action_key) in wrappers.items():
        result = router.run_cloud(service, "open", [])
        assert result["ok"] is True
        assert result["mode"] == "read_only_open"
        assert result["state_change"] is False
        assert result["execution_allowed"] is True
        assert result["requires_approval"] is False
        assert result["surface"]["key"] == surface_key
        assert result["action_key"] == action_key
        assert result["target_url"].startswith("https://console.cloud.google.com")
        assert result["browser_navigation"]["live_open"] is False
        assert result["browser_navigation"]["final_click_allowed"] is False

        action_result = router.run_cloud(service, action_key, [])
        assert action_result["ok"] is True
        assert action_result["action_key"] == action_key


def test_vertex_ai_is_not_cloud_owned() -> None:
    assert "vertex_ai" not in [surface["key"] for surface in registry.list_surfaces()]
