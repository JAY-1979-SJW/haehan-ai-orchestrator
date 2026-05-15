"""scripts.site_engine.adapters — browser/file/local-agent adapter 기반."""
from scripts.site_engine.adapters.browser import (
    BrowserActionKind,
    BrowserActionPlan,
    BrowserActionResult,
    build_readonly_navigation_plan,
    build_click_plan,
    build_input_plan,
    build_download_plan,
    build_upload_plan,
    build_submit_plan,
)

__all__ = [
    "BrowserActionKind",
    "BrowserActionPlan",
    "BrowserActionResult",
    "build_readonly_navigation_plan",
    "build_click_plan",
    "build_input_plan",
    "build_download_plan",
    "build_upload_plan",
    "build_submit_plan",
]
