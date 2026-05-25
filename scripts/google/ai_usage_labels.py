"""Google AI usage and cost labels for app UI.

The values here are policy labels, not billing enforcement. Pricing and rate
limits can change, so source URLs and verification dates are part of the
contract.
"""
from __future__ import annotations

from datetime import date
from typing import Any

VERIFIED_ON = "2026-05-25"

SOURCE_URLS = {
    "gemini_pricing": "https://ai.google.dev/gemini-api/docs/pricing",
    "gemini_rate_limits": "https://ai.google.dev/gemini-api/docs/rate-limits",
    "vertex_quotas": "https://cloud.google.com/vertex-ai/generative-ai/docs/quotas",
    "vertex_pricing": "https://cloud.google.com/vertex-ai/generative-ai/pricing",
}

GOOGLE_AI_USAGE_LABELS: dict[str, dict[str, Any]] = {
    "ai_studio": {
        "surface_key": "ai_studio",
        "host": "aistudio.google.com",
        "service": "Google AI Studio",
        "billing_label": "free_ui_usage_with_api_tier_limits",
        "free_summary": "AI Studio access is included in the Gemini API free tier. API calls use project rate limits.",
        "usage_limit_summary": "Rate limits are project and model dependent; check active limits in AI Studio.",
        "paid_summary": "Paid tier gives higher limits, advanced features, and different data handling.",
        "user_data_label": "free_tier_content_may_be_used_to_improve_products",
        "safe_ui_label": "read_only_or_prepare_until_approval",
        "approval_required_for": ["API key creation", "prompt submission", "model calls that may incur cost"],
        "source_keys": ["gemini_pricing", "gemini_rate_limits"],
    },
    "gemini_api": {
        "surface_key": "ai_studio",
        "host": "aistudio.google.com",
        "service": "Gemini Developer API",
        "billing_label": "free_tier_available_paid_for_production",
        "free_summary": "Free tier provides free input/output tokens for supported models with lower limits.",
        "usage_limit_summary": "Limits are measured by RPM, input TPM, and RPD; RPD resets at midnight Pacific time.",
        "paid_summary": "Paid tier has higher rate limits, context caching, Batch API discount, and production use controls.",
        "included_free_usage": ["Free input and output tokens on supported free-tier models", "Google AI Studio access"],
        "known_free_allowances": ["Gemini 3 paid grounding includes 5,000 prompts or requests per month shared across Gemini 3 before paid search-query charges."],
        "approval_required_for": ["Billing upgrade", "API key creation", "production quota/rate-limit increase"],
        "source_keys": ["gemini_pricing", "gemini_rate_limits"],
    },
    "vertex_ai_gemini": {
        "surface_key": "vertex_ai",
        "host": "console.cloud.google.com",
        "service": "Vertex AI Gemini / Gemini Enterprise Agent Platform",
        "billing_label": "cloud_billing_project_required_for_production",
        "free_summary": "Some Google Cloud/Vertex features include free tiers or credits; generative model use is generally billed by usage after free allowances.",
        "usage_limit_summary": "Newer Gemini models can use Dynamic Shared Quota for PayGo, while other models use standard quotas by project and region.",
        "paid_summary": "PayGo and provisioned throughput are production options; prices vary by model, modality, region, and feature.",
        "known_free_allowances": ["Agent Engine runtime free tier: 50 vCPU hours and 100 GiB hours per month per project."],
        "approval_required_for": ["Model endpoint deployment", "training job", "agent deployment", "billing or quota change"],
        "source_keys": ["vertex_quotas", "vertex_pricing"],
    },
}


def build_google_ai_usage_labels() -> dict[str, Any]:
    return {
        "site_id": "google",
        "tab_key": "ai",
        "verified_on": VERIFIED_ON,
        "generated_on": date.today().isoformat(),
        "source_urls": SOURCE_URLS,
        "labels": GOOGLE_AI_USAGE_LABELS,
        "ui_policy": {
            "show_cost_badge": True,
            "show_free_limit_badge": True,
            "show_source_link": True,
            "state_change": "approval_required",
            "secret_export": "blocked",
        },
    }


def label_for_surface(surface_key: str) -> dict[str, Any]:
    for item in GOOGLE_AI_USAGE_LABELS.values():
        if item["surface_key"] == surface_key:
            return item
    return {
        "surface_key": surface_key,
        "billing_label": "not_ai_pricing_surface",
        "free_summary": "",
        "usage_limit_summary": "",
        "paid_summary": "",
        "source_keys": [],
    }


__all__ = ["GOOGLE_AI_USAGE_LABELS", "SOURCE_URLS", "build_google_ai_usage_labels", "label_for_surface"]
