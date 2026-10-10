from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from scripts.google.cloud import live_console_explorer as live

ROOT = Path(__file__).resolve().parents[2]


def test_cloud_live_explorer_redacts_urls_and_sensitive_text() -> None:
    assert live._redact_text("owner user@example.com id 123456789") == "owner [email-redacted] id [number-redacted]"
    assert live._redact_url("https://console.cloud.google.com/apis?project=secret-project#frag") == (
        "https://console.cloud.google.com/apis?[query-redacted]"
    )


def test_cloud_live_explorer_selects_cloud_surfaces_only() -> None:
    keys = [item["key"] for item in live._cloud_surfaces()]

    assert "cloud_console" in keys
    assert "cloud_iam" in keys
    assert "secret_manager" in keys
    assert "gmail" not in keys


def test_cloud_live_report_save_writes_latest(monkeypatch) -> None:
    root = ROOT / "tmp" / "google_cloud_live_tests" / uuid4().hex
    latest = root / "latest.json"
    report_dir = root / "reports"
    monkeypatch.setattr(live, "LATEST_REPORT", latest)
    monkeypatch.setattr(live, "REPORT_DIR", report_dir)

    report = {
        "site_id": "google",
        "tab_key": "cloud",
        "status": "completed",
        "mode": "direct_cdp_read_only_no_click",
        "counts": {"planned": 1, "visited": 1, "failed": 0, "risk_controls_detected": 0},
        "surfaces": [],
    }
    _, path = live.save_cloud_console_live_report(report)

    assert path.exists()
    assert latest.exists()
    assert "direct_cdp_read_only_no_click" in latest.read_text(encoding="utf-8")


def test_cloud_live_risk_control_classifier() -> None:
    controls = [
        {"tag": "button", "text": "Create API key", "aria": "", "title": ""},
        {"tag": "a", "text": "Documentation", "aria": "", "title": ""},
    ]

    risks = live._risk_controls(controls)

    assert len(risks) == 1
    assert risks[0]["matched_keywords"] == ["Create", "API key"]


def test_cloud_live_logic_converts_report_to_surface_logic() -> None:
    report = {
        "site_id": "google",
        "tab_key": "cloud",
        "status": "completed",
        "generated_at": "2026-05-25T00:00:00+00:00",
        "mode": "direct_cdp_read_only_no_click",
        "counts": {"planned": 15, "visited": 15, "failed": 0, "risk_controls_detected": 1},
        "surfaces": [
            {
                "key": "cloud_console",
                "status": "visited",
                "title": "Google Cloud Console",
                "headings": ["Getting started"],
                "controls": [{"text": "Create VM"}],
                "inputs": [],
                "risk_controls": [{"text": "Create VM", "matched_keywords": ["Create"]}],
            }
        ],
    }

    logic = live.build_cloud_console_live_logic(report)
    by_key = {item["surface_key"]: item for item in logic["surfaces"]}

    assert logic["surface_count"] == 15
    assert logic["live_verified_count"] == 1
    assert logic["risk_surface_count"] == 1
    assert by_key["cloud_console"]["live_verified_readonly"] is True
    assert by_key["cloud_console"]["observed_risk_controls"] == [
        {"text": "Create VM", "matched_keywords": ["Create"]}
    ]
    assert "Check project console overview." in by_key["cloud_console"]["user_guidance"]["user_can_request"]
    assert "create VM" in by_key["cloud_console"]["user_guidance"]["approval_required_for"]
    assert by_key["cloud_console"]["read_actions"] == ["cloud_console_open"]
    assert by_key["cloud_console"]["approval_actions"] == []


def test_cloud_surface_guidance_covers_console_seo_related_surfaces() -> None:
    assert "Check visible API/key/quota navigation." in live.CLOUD_SURFACE_USER_GUIDANCE["maps_platform"]["user_can_request"]
    assert "Open Logging read-only." in live.CLOUD_SURFACE_USER_GUIDANCE["cloud_logging"]["user_can_request"]
    assert "Open Monitoring read-only." in live.CLOUD_SURFACE_USER_GUIDANCE["cloud_monitoring"]["user_can_request"]


def test_cloud_package_exposes_live_logic(monkeypatch) -> None:
    from scripts.google import cloud

    monkeypatch.setattr(
        "scripts.google.cloud.live_console_explorer.build_cloud_console_live_logic",
        lambda: {"tab_key": "cloud"},
    )

    assert cloud.live_logic()["tab_key"] == "cloud"
