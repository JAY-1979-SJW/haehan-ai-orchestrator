from __future__ import annotations

from scripts.google import ai
from scripts.google.ai_usage_labels import build_google_ai_usage_labels, label_for_surface


def test_google_ai_usage_labels_cover_ai_surfaces() -> None:
    labels = build_google_ai_usage_labels()

    assert labels["tab_key"] == "ai"
    assert "ai_studio" in labels["labels"]
    assert "gemini_api" in labels["labels"]
    assert "vertex_ai_gemini" in labels["labels"]
    assert labels["labels"]["ai_studio"]["billing_label"] == "free_ui_usage_with_api_tier_limits"
    assert "gemini_pricing" in labels["source_urls"]


def test_ai_package_catalog_exposes_usage_labels() -> None:
    catalog = ai.catalog()

    assert catalog["tab_key"] == "ai"
    assert catalog["usage_labels"]["labels"]["gemini_api"]["billing_label"] == "free_tier_available_paid_for_production"


def test_label_for_surface_maps_vertex_ai() -> None:
    label = label_for_surface("vertex_ai")

    assert label["host"] == "console.cloud.google.com"
    assert "Dynamic Shared Quota" in label["usage_limit_summary"]
