"""Browser tab status and cleanup through the Chrome DevTools HTTP API.

This module intentionally avoids Playwright for tab listing/closing. The CDP
browser can be reachable over HTTP even when Playwright's driver process is
blocked by Windows permissions or a stale connection.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.common.config import CDP_HOST, CDP_PORT  # noqa: E402 - sys.path 부트스트랩 뒤 import
from scripts.common.logger import get_logger  # noqa: E402 - sys.path 부트스트랩 뒤 import

log = get_logger(__name__)


def _cdp_json(path: str) -> Any:
    with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}{path}", timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _close_target(target_id: str) -> bool:
    try:
        quoted = urllib.parse.quote(target_id, safe="")
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/close/{quoted}", timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return "Target is closing" in body or body.strip().lower() in {"ok", ""}
    except Exception as exc:  # noqa: BLE001 - 브라우저 탭 모니터 -- CDP 탭 닫기/조회 실패 시 False/빈 리스트 반환(읽기 전용 모니터링)
        log.debug("[tab-monitor] close failed target=%s err=%s", target_id, exc)
        return False


def get_active_tabs() -> list[dict[str, Any]]:
    """Return active page targets from the running CDP browser."""
    try:
        rows = _cdp_json("/json/list")
    except Exception as exc:  # noqa: BLE001 - 브라우저 탭 모니터 -- CDP 탭 닫기/조회 실패 시 False/빈 리스트 반환(읽기 전용 모니터링)
        log.debug("[tab-monitor] tab query failed: %s", exc)
        return []

    tabs: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else rows.get("value", []):
        if row.get("type") != "page":
            continue
        tabs.append(
            {
                "index": len(tabs) + 1,
                "id": row.get("id", ""),
                "url": row.get("url", ""),
                "title": row.get("title", ""),
                "page_obj": None,
            }
        )
    return tabs


def get_tab_count() -> int:
    """Return current page-target count."""
    return len(get_active_tabs())


def close_extra_tabs(keep_count: int = 1, target_domain: str | None = None) -> int:
    """Close excess tabs, optionally restricted to a domain substring."""
    tabs = get_active_tabs()
    if target_domain:
        target_tabs = [tab for tab in tabs if target_domain in tab.get("url", "")]
    else:
        target_tabs = tabs[max(0, keep_count) :]

    closed = 0
    for tab in target_tabs:
        target_id = str(tab.get("id") or "")
        if not target_id:
            continue
        if _close_target(target_id):
            closed += 1
            log.info("[tab-monitor] closed tab: %s", tab.get("url", ""))
            time.sleep(0.2)
    return closed


def close_tabs_by_domain(domain: str) -> int:
    """Close every tab whose URL contains ``domain``."""
    return close_extra_tabs(keep_count=0, target_domain=domain)


def log_tab_status() -> None:
    """Log current tab status."""
    tabs = get_active_tabs()
    log.info("[tab-monitor] active tabs: %d", len(tabs))
    for tab in tabs:
        log.info("  [%s] %s", tab["index"], tab["url"])


def print_tab_list(filter_domain: str | None = None) -> None:
    """Print a compact tab list."""
    tabs = get_active_tabs()
    filtered = [tab for tab in tabs if not filter_domain or filter_domain in tab.get("url", "")]

    print("\n" + "=" * 80)
    print(f"  브라우저 탭 목록 ({len(tabs)}개)")
    print("=" * 80)
    if filter_domain:
        print(f"  필터: {filter_domain} ({len(filtered)}개)")
    if not filtered:
        print("  (탭 없음)")
        print("=" * 80 + "\n")
        return

    for tab in filtered:
        url = tab.get("url", "")
        title = tab.get("title", "")
        url_display = url[:67] + "..." if len(url) > 70 else url
        title_display = f" - {title[:40]}" if title else ""
        print(f"  [{tab['index']:2d}] {url_display}{title_display}")
    print("=" * 80 + "\n")


def cleanup_idle_tabs(target_count: int = 5) -> int:
    """Trim tab count to ``target_count``."""
    count = get_tab_count()
    if count > target_count:
        log.warning("[tab-monitor] too many tabs: %d -> %d", count, target_count)
        return close_extra_tabs(keep_count=target_count)
    return 0


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "list":
        print_tab_list(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "count":
        print(f"현재 활성 탭: {get_tab_count()}개")
    elif cmd == "cleanup":
        target = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        print(f"\n탭 정리 (목표: {target}개)...")
        print(f"✓ {cleanup_idle_tabs(target_count=target)}개 탭 닫음")
        print_tab_list()
    elif cmd == "close-domain":
        domain = sys.argv[2] if len(sys.argv) > 2 else "naver.com"
        print(f"\n{domain} 탭 닫기...")
        print(f"✓ {close_tabs_by_domain(domain)}개 탭 닫음")
        print_tab_list()
    elif cmd == "test":
        log_tab_status()
        print(f"\n총 {get_tab_count()}개 탭")
    else:
        print("""탭 관리 CLI

사용법:
  python scripts/browser/cdp/browser_tab_monitor.py list
  python scripts/browser/cdp/browser_tab_monitor.py list eum.cw
  python scripts/browser/cdp/browser_tab_monitor.py count
  python scripts/browser/cdp/browser_tab_monitor.py cleanup 5
  python scripts/browser/cdp/browser_tab_monitor.py close-domain naver.com
""")
