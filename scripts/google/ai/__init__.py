"""Google AI sub-tab package."""
from __future__ import annotations

from scripts.google.common.tab_logic import build_tab_logic_catalog, classify_tab_operation, get_tab_summary
from scripts.google.ai_usage_labels import build_google_ai_usage_labels

TAB_KEY = "ai"


def summary() -> dict:
    return get_tab_summary(TAB_KEY)


def catalog() -> dict:
    base = build_tab_logic_catalog(TAB_KEY)
    base["usage_labels"] = build_google_ai_usage_labels()
    return base


def classify_operation(key_or_host: str = "aistudio.google.com", operation: str = "read") -> dict:
    return classify_tab_operation(TAB_KEY, key_or_host, operation)


def usage_labels() -> dict:
    return build_google_ai_usage_labels()
