"""Explore pages available in the current EUM account menu."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root
from scripts.eum.report_io import save_json

ROOT = repo_root()


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()
EUM_BASE = "https://eum.cw.or.kr"


_PAGE_JS = """
() => {
  const textOf = (el) => (el.innerText || el.textContent || el.value || '').replace(/\\s+/g, ' ').trim();
  return {
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    bodyTextSample: ((document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 800),
    inputs: Array.from(document.querySelectorAll('input, select, textarea')).map((el, idx) => ({
      index: idx,
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      name: el.name || '',
      id: el.id || '',
      placeholder: el.placeholder || '',
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    })).slice(0, 120),
    buttons: Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a[href]')).map((el, idx) => ({
      index: idx,
      tag: el.tagName.toLowerCase(),
      text: textOf(el).slice(0, 120),
      href: el.href || el.getAttribute('href') || '',
      onclick: el.getAttribute('onclick') || '',
      id: el.id || '',
      className: String(el.className || '').slice(0, 120),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    })).filter(x => x.text || x.href || x.onclick).slice(0, 160),
    tables: Array.from(document.querySelectorAll('table')).map((table, idx) => ({
      index: idx,
      rows: table.querySelectorAll('tr').length,
      headers: Array.from(table.querySelectorAll('th')).map(textOf).filter(Boolean).slice(0, 80)
    })).slice(0, 80)
  };
}
"""


def _absolute_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return EUM_BASE + path


def explore_accessible_pages(page, *, max_pages: int | None = None, partial_path: Path | None = None) -> dict[str, Any]:
    from scripts.eum.navigation import extract_live_menu

    menu = extract_live_menu(page)
    pages = [row for row in menu if str(row.get("urlAddr") or "").startswith("/web/")]
    if max_pages:
        pages = pages[:max_pages]

    result: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": EUM_BASE,
        "menu_count": len(menu),
        "explored_count": 0,
        "pages": [],
    }
    for idx, row in enumerate(pages, 1):
        url = _absolute_url(str(row.get("urlAddr")))
        item = {
            "menuId": row.get("menuId"),
            "menuNm": row.get("menuNm"),
            "menuLvVl": row.get("menuLvVl"),
            "url": url,
            "ok": False,
            "error": "",
        }
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            time.sleep(0.5)
            item.update(page.evaluate(_PAGE_JS))
            item["ok"] = True
        except Exception as exc:  # noqa: BLE001 - EUM 사이트 페이지 탐색(page.evaluate) 실패를 item['error']에 기록하고 다음 페이지 계속 탐색 - 읽기전용 탐색, 실패 페이지는 에러로 표시될 뿐 위험 조작 없음
            item["error"] = str(exc)
        result["pages"].append(item)
        result["explored_count"] = len(result["pages"])
        if partial_path:
            save_accessible_pages(result, partial_path)
        time.sleep(0.2)

    return result


def save_accessible_pages(result: dict[str, Any], path: Path | None = None) -> Path:
    return save_json(result, DATA_DIR, "eum_accessible_pages.json", path)


def print_summary(result: dict[str, Any], path: Path | None = None) -> None:
    pages = result.get("pages", [])
    ok = [p for p in pages if p.get("ok")]
    form_pages = [p for p in ok if p.get("inputs")]
    print("=" * 60)
    print("EUM accessible page exploration")
    print("=" * 60)
    print(f"menu items: {result.get('menu_count', 0)}")
    print(f"explored pages: {len(pages)}")
    print(f"ok pages: {len(ok)}")
    print(f"pages with inputs: {len(form_pages)}")
    if path:
        print(f"saved: {path}")
    for page in ok:
        print(
            f"  - {page.get('menuNm')}: inputs={len(page.get('inputs', []))} buttons={len(page.get('buttons', []))} tables={len(page.get('tables', []))}"
        )
