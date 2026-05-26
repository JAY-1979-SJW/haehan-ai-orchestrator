"""Google YouTube sub-tab package."""
from __future__ import annotations

from scripts.google.domain_taxonomy import build_google_domain_taxonomy
from scripts.google.tab_logic import build_tab_logic_catalog, classify_tab_operation, get_tab_summary
from scripts.google.youtube_upload import build_youtube_upload_plan

TAB_KEY = "youtube"


def summary() -> dict:
    return get_tab_summary(TAB_KEY)


def catalog() -> dict:
    return build_tab_logic_catalog(TAB_KEY)


def classify_operation(key_or_host: str = "www.youtube.com", operation: str = "read") -> dict:
    return classify_tab_operation(TAB_KEY, key_or_host, operation)


def page_tabs() -> dict:
    taxonomy = build_google_domain_taxonomy()
    surfaces = [
        item
        for item in taxonomy["domains"]
        if item["surface_key"] in {"youtube", "youtube_studio"}
    ]
    return {
        "site_id": "google",
        "tab_key": TAB_KEY,
        "surface_count": len(surfaces),
        "page_tab_count": sum(len(item["page_tabs"]) for item in surfaces),
        "surfaces": surfaces,
    }


def upload_plan(values: dict[str, str]) -> dict:
    return build_youtube_upload_plan(values)
