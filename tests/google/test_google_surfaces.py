import json
from pathlib import Path
from uuid import uuid4

from scripts.google.common import surface_explorer, surfaces


def _test_dir() -> Path:
    path = Path("tmp") / "google_tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_google_surface_catalog_contains_required_work_surfaces():
    catalog = surfaces.build_surface_catalog()
    keys = {item["key"] for item in catalog["surfaces"]}

    assert "cloud_console" in keys
    assert "ai_studio" in keys
    assert "android_developers" in keys
    assert "play_console" in keys
    assert "youtube" in keys
    assert "youtube_studio" in keys
    assert "cloud_apis_credentials" in keys
    assert "cloud_iam" in keys
    assert "vertex_ai" in keys
    assert "business_profile" in keys
    assert "ads" in keys
    assert catalog["policy"]["writes"] == "dry_run_and_explicit_approval_required"


def test_google_surface_catalog_marks_sensitive_workflows_gated():
    catalog = surfaces.build_surface_catalog()
    by_key = {item["key"]: item for item in catalog["surfaces"]}

    assert by_key["google_account"]["access_mode"] == "manual_or_oauth_only"
    assert by_key["youtube_studio"]["risk"] == "channel_publish_monetization_write_possible"
    assert "approval" in " ".join(by_key["play_console"]["completion_criteria"])
    assert catalog["counts"]["surfaces"] == len(catalog["surfaces"])


def test_google_surface_catalog_save_writes_latest(monkeypatch):
    root = _test_dir()
    latest = root / "latest.json"
    report_dir = root / "reports"
    monkeypatch.setattr(surfaces, "LATEST_CATALOG", latest)
    monkeypatch.setattr(surfaces, "REPORT_DIR", report_dir)

    path = surfaces.save_surface_catalog()

    assert path.exists()
    assert latest.exists()
    saved = json.loads(latest.read_text(encoding="utf-8"))
    assert saved["site_id"] == "google"
    assert saved["counts"]["surfaces"] >= 45


def test_google_surface_explorer_detects_login_and_risk_controls():
    assert surface_explorer.detect_login_required(
        "https://accounts.google.com/",
        "Sign in - Google Accounts",
        ["Use your Google Account"],
    )
    assert not surface_explorer.detect_login_required(
        "https://www.google.com/",
        "Google",
        ["Google Account: user@example.com", "https://accounts.google.com/SignOutOptions"],
    )
    controls = surface_explorer.classify_risk_controls(
        [
            {"text": "Publish", "aria": "", "title": "", "role": "button"},
            {"text": "Learn more", "aria": "", "title": "", "role": "link"},
        ]
    )

    assert len(controls) == 1
    assert controls[0]["matched_keywords"] == ["Publish"]


def test_google_surface_exploration_save_writes_latest(monkeypatch):
    root = _test_dir()
    latest = root / "latest.json"
    report_dir = root / "reports"
    monkeypatch.setattr(surface_explorer, "LATEST_EXPLORATION", latest)
    monkeypatch.setattr(surface_explorer, "EXPLORATION_DIR", report_dir)
    report = {
        "site_id": "google",
        "status": "completed",
        "mode": "read_only_no_click",
        "counts": {
            "planned": 0,
            "visited": 0,
            "accessible": 0,
            "login_required": 0,
            "failed": 0,
            "risk_controls_detected": 0,
        },
        "surfaces": [],
        "account": "user@example.com",
    }

    _, path = surface_explorer.save_surface_exploration(report)

    assert path.exists()
    assert latest.exists()
    saved = json.loads(latest.read_text(encoding="utf-8"))
    assert saved["mode"] == "read_only_no_click"
    assert saved["account"] == "[email-redacted]"
