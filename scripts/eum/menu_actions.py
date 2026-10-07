"""Generic safe actions for EUM menu pages."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()
EUM_BASE = "https://eum.cw.or.kr"

_SUMMARY_JS = """
() => {
  const textOf = (el) => (el.innerText || el.textContent || el.value || '').replace(/\\s+/g, ' ').trim();
  return {
    url: location.href,
    title: document.title,
    captured_at: new Date().toISOString(),
    headings: Array.from(document.querySelectorAll('h1,h2,h3,h4,.tit,.title')).map(textOf).filter(Boolean).slice(0, 40),
    inputs: Array.from(document.querySelectorAll('input, select, textarea')).map((el, idx) => ({
      index: idx,
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      name: el.name || '',
      id: el.id || '',
      placeholder: el.placeholder || '',
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    })).slice(0, 160),
    buttons: Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a[href]')).map((el, idx) => ({
      index: idx,
      tag: el.tagName.toLowerCase(),
      text: textOf(el).slice(0, 120),
      href: el.href || el.getAttribute('href') || '',
      onclick: el.getAttribute('onclick') || '',
      id: el.id || '',
      className: String(el.className || '').slice(0, 120),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    })).filter(x => x.text || x.href || x.onclick).slice(0, 200),
    tables: Array.from(document.querySelectorAll('table')).map((table, idx) => ({
      index: idx,
      rows: table.querySelectorAll('tr').length,
      headers: Array.from(table.querySelectorAll('th')).map(textOf).filter(Boolean).slice(0, 80)
    })).slice(0, 100)
  };
}
"""


def _abs_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return EUM_BASE + path


def resolve_menu(menu: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    q = query.strip().lower()
    if not q:
        return None
    exact = []
    partial = []
    for row in menu:
        values = [
            str(row.get("menuId") or ""),
            str(row.get("menuNm") or ""),
            str(row.get("urlAddr") or ""),
        ]
        lowered = [v.lower() for v in values]
        if q in lowered or any(v.endswith(q) for v in lowered):
            exact.append(row)
        elif any(q in v for v in lowered):
            partial.append(row)
    return (exact or partial or [None])[0]


def page_summary(page) -> dict[str, Any]:
    return page.evaluate(_SUMMARY_JS)


def open_menu_page(page, query: str) -> dict[str, Any]:
    from scripts.eum.navigation import extract_live_menu

    menu = extract_live_menu(page)
    row = resolve_menu(menu, query)
    if not row:
        return {
            "ok": False,
            "query": query,
            "error": "menu not found in current account",
            "available": [{"menuNm": m.get("menuNm"), "urlAddr": m.get("urlAddr")} for m in menu if m.get("urlAddr")],
        }
    url_addr = str(row.get("urlAddr") or "")
    if not url_addr:
        return {"ok": False, "query": query, "menu": row, "error": "menu has no urlAddr"}
    page.goto(_abs_url(url_addr), wait_until="domcontentloaded", timeout=15000)
    summary = page_summary(page)
    return {"ok": True, "query": query, "menu": row, "summary": summary}


def save_menu_result(result: dict[str, Any], path: Path | None = None) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = path or DATA_DIR / f"eum_menu_page_{stamp}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def fetch_save_print(
    page,
    fetch: Callable[[Any], list[dict[str, Any]]],
    save: Callable[[list[dict[str, Any]]], Path],
    label: str,
) -> Path:
    """조회 화면 공통 실행: fetch(page) → save(records) → '<label>: N건 조회 → 경로' 출력."""
    records = fetch(page)
    path = save(records)
    print(f"{label}: {len(records)}건 조회 → {path}")
    return path


def print_menu_result(result: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("EUM menu page")
    print("=" * 60)
    print(f"query: {result.get('query')}")
    print(f"ok: {result.get('ok')}")
    if result.get("menu"):
        menu = result["menu"]
        print(f"menu: {menu.get('menuNm')} {menu.get('urlAddr')}")
    if result.get("summary"):
        summary = result["summary"]
        print(f"url: {summary.get('url')}")
        print(f"inputs: {len(summary.get('inputs', []))}")
        print(f"buttons: {len(summary.get('buttons', []))}")
        print(f"tables: {len(summary.get('tables', []))}")
    if result.get("error"):
        print(f"error: {result.get('error')}")
    if path:
        print(f"saved: {path}")
