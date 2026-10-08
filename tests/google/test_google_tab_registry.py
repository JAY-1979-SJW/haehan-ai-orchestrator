from __future__ import annotations

from importlib import import_module

from scripts.google.common import tab_registry


def test_google_tab_registry_preserves_catalog_totals() -> None:
    summary = tab_registry.build_google_tab_summary()

    assert summary["counts"]["tabs"] == 9
    assert summary["counts"]["surfaces"] == 50
    assert summary["counts"]["actions"] == 96
    assert summary["counts"]["read_actions"] == 50
    assert summary["counts"]["approval_actions"] == 46


def test_google_tab_registry_assigns_every_surface_once() -> None:
    summary = tab_registry.build_google_tab_summary()
    assigned = [
        surface["key"]
        for tab in summary["tabs"]
        for surface in tab["surfaces"]
    ]

    assert len(assigned) == 50
    assert len(set(assigned)) == 50


def test_google_tab_registry_assigns_every_action_once() -> None:
    summary = tab_registry.build_google_tab_summary()
    assigned = [
        action["key"]
        for tab in summary["tabs"]
        for action in tab["actions"]
    ]

    assert len(assigned) == 96
    assert len(set(assigned)) == 96


def test_google_tab_registry_keeps_high_risk_cloud_under_cloud_or_ai() -> None:
    summary = tab_registry.build_google_tab_summary()
    by_key = {tab["key"]: tab for tab in summary["tabs"]}
    cloud_surfaces = {surface["key"] for surface in by_key["cloud"]["surfaces"]}
    ai_surfaces = {surface["key"] for surface in by_key["ai"]["surfaces"]}

    assert "cloud_iam" in cloud_surfaces
    assert "cloud_billing" in cloud_surfaces
    assert "secret_manager" in cloud_surfaces
    assert "vertex_ai" in ai_surfaces


def test_google_tab_registry_has_no_host_normalization_warnings() -> None:
    summary = tab_registry.build_google_tab_summary()

    assert summary["host_warnings"] == []


def test_google_tab_owner_packages_exist() -> None:
    for tab in tab_registry.GOOGLE_TABS:
        import_module(tab.owner_package)
