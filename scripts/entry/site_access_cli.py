"""사이트 접속 직접 실행 — `python -m scripts.entry.site_access_cli <site> [path]` (site_access.main 이 옮겨 온 곳)."""

from __future__ import annotations

import sys
from typing import Any

from scripts.entry import site_login_registry
from scripts.site_engine.site_access import LoginError, list_sites, open_site


def main() -> None:
    site_login_registry.install()
    if len(sys.argv) < 2:
        print("사용법: python -m scripts.entry.site_access_cli <site> [path]")
        print(f"  지원 사이트: {list_sites()}")
        return
    site = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        page: Any = open_site(site, path)
        if isinstance(page, dict):
            print(f"✔ {site} 접속 드라이런 완료 — {page.get('url', '')}")
        else:
            print(f"✔ {site} 접속 완료 — {page.url}")
    except LoginError as e:
        print(f"✘ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
