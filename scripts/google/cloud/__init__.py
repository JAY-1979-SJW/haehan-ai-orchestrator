"""Google Cloud sub-tab package."""
from __future__ import annotations

from scripts.google.common.tab_logic import build_tab_logic_catalog, classify_tab_operation, get_tab_summary
from scripts.google.cloud import live_console_explorer

TAB_KEY = "cloud"


def summary() -> dict:
    return get_tab_summary(TAB_KEY)


def catalog() -> dict:
    return build_tab_logic_catalog(TAB_KEY)


def classify_operation(key_or_host: str = "console.cloud.google.com", operation: str = "read") -> dict:
    return classify_tab_operation(TAB_KEY, key_or_host, operation)


def live_logic() -> dict:
    return live_console_explorer.build_cloud_console_live_logic()
