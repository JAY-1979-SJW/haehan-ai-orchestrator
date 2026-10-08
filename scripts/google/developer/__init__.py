"""Google developer tools sub-tab package."""
from __future__ import annotations

from scripts.google.android_app_dev_labels import build_android_app_dev_labels
from scripts.google.android_app_dev_report import build_android_app_dev_report
from scripts.google.common.tab_logic import build_tab_logic_catalog, classify_tab_operation, get_tab_summary

TAB_KEY = "developer"


def summary() -> dict:
    return get_tab_summary(TAB_KEY)


def catalog() -> dict:
    return build_tab_logic_catalog(TAB_KEY)


def classify_operation(key_or_host: str = "developer.android.com", operation: str = "read") -> dict:
    return classify_tab_operation(TAB_KEY, key_or_host, operation)


def android_app_labels() -> dict:
    return build_android_app_dev_labels()


def android_app_report() -> dict:
    return build_android_app_dev_report()
