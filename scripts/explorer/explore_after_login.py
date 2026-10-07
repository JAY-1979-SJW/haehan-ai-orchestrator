"""로그인 보장 후 자동 사이트 탐색 — site_access 로 접속하고 auto_explorer 로 훑는다.

site_engine(접속·로그인)이 explorer(탐색)를 부르던 방향을 뒤집어, explorer → site_engine 한 방향만 남긴다.
"""

from __future__ import annotations

import os
from typing import Any

from scripts.common.logger import get_logger
from scripts.explorer.auto_explorer import explore_site
from scripts.site_engine.site_access import open_site
from scripts.site_engine.site_registry import get_site

log = get_logger(__name__)


def _dry_run() -> bool:
    return os.environ.get("SITE_DRY_RUN", "").strip() in ("1", "true", "TRUE", "yes")


def explore_after_login(
    site: str,
    path: str = "",
    *,
    depth: int = 2,
    max_pages: int = 20,
) -> dict:
    """로그인 보장 후 자동 사이트 탐색.

    Returns:
        {open: {url, ...}, explore: {host, pages, ...}}
    """
    if _dry_run():
        spec = get_site(site)
        target = (spec.base_url if spec else "https://example.com") + (path or "")
        open_site(site, path)  # 드라이런 흐름만
        print(f"  [DRY] explore_site(depth={depth}, max={max_pages})")
        print(f"  [DRY] visited 0~{max_pages} pages — (사이트맵 미생성)")
        return {
            "open": {"url": target, "site": site, "dry_run": True},
            "explore": {"host": "(dry)", "visited": 0, "elapsed_s": 0.0, "aborted_reason": "", "saved_to": ""},
        }

    page: Any = open_site(site, path)
    log.info("[site-access] %s 로그인 완료 — 자동 탐색 시작 (depth=%d max=%d)", site, depth, max_pages)
    explore = explore_site(page, depth=depth, max_pages=max_pages)
    return {
        "open": {"url": page.url, "site": site},
        "explore": {
            "host": explore["host"],
            "visited": explore["visited_count"],
            "elapsed_s": explore["elapsed_s"],
            "aborted_reason": explore.get("aborted_reason", ""),
            "saved_to": explore.get("saved_to", ""),
        },
    }
