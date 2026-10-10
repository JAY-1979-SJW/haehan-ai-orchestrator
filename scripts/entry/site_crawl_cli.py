"""사이트 전체 크롤 직접 실행 — `python -m scripts.entry.site_crawl_cli <site> [depth] [max_pages]` (site_crawler.main 이 옮겨 온 곳)."""

from __future__ import annotations

import sys

from scripts.entry import site_login_registry
from scripts.explorer.site_crawler import crawl_site
from scripts.site_engine.site_access import open_site


def main() -> None:
    site_login_registry.install()
    if len(sys.argv) < 2:
        print("사용법: python -m scripts.entry.site_crawl_cli <site> [depth] [max_pages]")
        return
    site = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    page = open_site(site)
    result = crawl_site(page, depth=depth, max_pages=max_pages)
    print("\n✓ 크롤 완료")
    print(f"  방문: {result['visited_count']} / 미설계 반영: {result['discovered_count']}")
    print(f"  타입 분포: {result['type_counts']}")
    if result.get("saved_to"):
        print(f"  사이트맵: {result['saved_to']}")
    if result.get("aborted_reason"):
        print(f"  중단: {result['aborted_reason']}")


if __name__ == "__main__":
    main()
