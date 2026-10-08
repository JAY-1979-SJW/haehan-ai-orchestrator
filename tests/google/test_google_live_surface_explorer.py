from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from scripts.google import live_surface_explorer as live

ROOT = Path(__file__).resolve().parents[2]


def test_live_surface_selector_filters_by_tab_and_excludes_cloud() -> None:
    workspace = live.select_surfaces(tabs=["workspace"])
    non_cloud = live.select_surfaces(exclude_tabs=["cloud"])

    assert len(workspace) == 12
    assert {item["key"] for item in workspace} >= {"gmail", "drive", "calendar"}
    assert all(item["key"] != "cloud_console" for item in non_cloud)
    assert len(non_cloud) == 35


def test_live_surface_selector_filters_by_keys() -> None:
    selected = live.select_surfaces(keys=["gmail", "search_console"])

    assert [item["key"] for item in selected] == ["gmail", "search_console"]


def test_live_surface_report_save_writes_latest(monkeypatch) -> None:
    root = ROOT / "tmp" / "google_surface_live_tests" / uuid4().hex
    latest = root / "latest.json"
    report_dir = root / "reports"
    monkeypatch.setattr(live, "LATEST_REPORT", latest)
    monkeypatch.setattr(live, "REPORT_DIR", report_dir)

    report = {
        "site_id": "google",
        "status": "completed",
        "mode": "direct_cdp_read_only_no_click",
        "counts": {"planned": 1, "visited": 1, "failed": 0, "risk_controls_detected": 0},
        "surfaces": [],
    }
    _, path = live.save_google_surface_live_report(report)

    assert path.exists()
    assert latest.exists()
    assert "direct_cdp_read_only_no_click" in latest.read_text(encoding="utf-8")


def test_live_surface_logic_converts_report_to_app_logic() -> None:
    report = {
        "site_id": "google",
        "status": "completed",
        "generated_at": "2026-05-25T00:00:00+00:00",
        "mode": "direct_cdp_read_only_no_click",
        "counts": {"planned": 1, "visited": 1, "failed": 0, "risk_controls_detected": 1},
        "surfaces": [
            {
                "key": "search_console",
                "tab_key": "marketing",
                "status": "visited",
                "title": "Search Console",
                "headings": ["Search Console"],
                "controls": [{"text": "Request indexing"}],
                "inputs": [],
                "risk_controls": [{"text": "Request indexing", "matched_keywords": ["Request indexing"]}],
            }
        ],
    }

    logic = live.build_google_surface_live_logic(report)
    by_key = {item["surface_key"]: item for item in logic["surfaces"]}

    assert logic["surface_count"] == 50
    assert logic["live_verified_count"] == 1
    assert logic["risk_surface_count"] == 1
    assert by_key["search_console"]["tab_key"] == "marketing"
    assert by_key["search_console"]["live_verified_readonly"] is True
    assert "Prepare SEO, indexing, analytics, ads, or reporting plans." in (
        by_key["search_console"]["user_guidance"]["user_can_request"]
    )
    assert by_key["search_console"]["approval_actions"] == [
        "search_console_submit_indexing",
        "search_console_submit_sitemap",
    ]


def test_live_surface_logic_merges_cloud_latest_report(monkeypatch) -> None:
    non_cloud_report = {
        "site_id": "google",
        "status": "completed",
        "generated_at": "2026-05-25T00:00:00+00:00",
        "mode": "direct_cdp_read_only_no_click",
        "counts": {"planned": 1, "visited": 1, "failed": 0, "risk_controls_detected": 0},
        "surfaces": [{"key": "gmail", "status": "visited", "controls": [], "inputs": [], "risk_controls": []}],
    }
    cloud_report = {
        "site_id": "google",
        "tab_key": "cloud",
        "status": "completed",
        "generated_at": "2026-05-25T00:10:00+00:00",
        "mode": "direct_cdp_read_only_no_click",
        "counts": {"planned": 1, "visited": 1, "failed": 0, "risk_controls_detected": 0},
        "surfaces": [{"key": "cloud_console", "status": "visited", "controls": [], "inputs": [], "risk_controls": []}],
    }
    monkeypatch.setattr(live, "load_latest_google_surface_live_report", lambda: non_cloud_report)
    monkeypatch.setattr(live, "load_latest_cloud_console_live_report", lambda: cloud_report)

    logic = live.build_google_surface_live_logic()
    by_key = {item["surface_key"]: item for item in logic["surfaces"]}

    assert logic["source_report_status"] == "completed"
    assert logic["source_reports"][0]["tab_key"] == "all_surfaces"
    assert logic["source_reports"][1]["tab_key"] == "cloud"
    assert by_key["gmail"]["live_verified_readonly"] is True
    assert by_key["cloud_console"]["live_verified_readonly"] is True
