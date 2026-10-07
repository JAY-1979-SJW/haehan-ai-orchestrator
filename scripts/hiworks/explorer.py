"""Read-only Hiworks dashboard and mail exploration helpers."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from scripts.hiworks.schemas import DATA_DIR, HIWORKS_DASHBOARD_URL, HIWORKS_DOMAIN_HINT


def open_hiworks(path: str = ""):
    from scripts.browser.page.web_connector import get_page_by_url

    page = get_page_by_url(HIWORKS_DOMAIN_HINT, create_url=HIWORKS_DASHBOARD_URL)
    if path and path != page.url:
        page.goto(path, timeout=30000)
        # 페이지 로드 대기 best-effort - 타임아웃 나도 이후 로직 계속 진행(읽기전용 탐색)
        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=15000)
    return page


def extract_dashboard_apps(page) -> list[dict[str, str]]:
    """Extract visible Hiworks app links from the dashboard."""
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]')).map((a) => {
          const text = (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim();
          return {text, href: a.href || ''};
        }).filter((x) => x.text && x.href && x.href.includes('office.hiworks.com'))"""
    )


def extract_visible_mail_actions(page) -> list[dict[str, str]]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href],button')).map((el) => ({
          text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
          href: el.href || ''
        })).filter((x) => x.text).slice(0, 120)"""
    )


def save_apps(apps: list[dict[str, str]], url: str, path: str | Path | None = None) -> Path:
    out = Path(path) if path else DATA_DIR / "hiworks_apps_latest.json"
    out.write_text(json.dumps({"url": url, "apps": apps}, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def print_apps(apps: list[dict[str, str]]) -> None:
    print("=" * 60)
    print("Hiworks apps")
    print("=" * 60)
    for idx, app in enumerate(apps, start=1):
        print(f"{idx:>2}. {app['text']} -> {app['href']}")
