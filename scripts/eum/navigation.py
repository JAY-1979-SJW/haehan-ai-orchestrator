"""EUM live menu/capability helpers."""
from __future__ import annotations

from typing import Any


def extract_live_menu(page) -> list[dict[str, Any]]:
    """Return the current account's live EUM menu from the Vue header."""
    try:
        rows = page.evaluate(
            """() => {
                if (typeof header === 'undefined' || !header.shared || !header.shared.menuList) return [];
                return header.shared.menuList.map(m => ({
                    menuId: m.menuId || '',
                    upMenuId: m.upMenuId || '',
                    menuNm: m.menuNm || '',
                    menuLvVl: m.menuLvVl || null,
                    urlAddr: m.urlAddr || ''
                }));
            }"""
        )
    except Exception:
        return []
    return [row for row in rows if isinstance(row, dict)]


def find_menu_by_code(menu: list[dict[str, Any]], code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    code = code.upper()
    for row in menu:
        if code in str(row.get("urlAddr") or "").upper():
            return row
    return None


def available_webman_codes(menu: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for row in menu:
        url = str(row.get("urlAddr") or "").upper()
        marker = "WEBMAN"
        idx = url.find(marker)
        if idx >= 0:
            codes.add(url[idx : idx + 12])
    return codes
