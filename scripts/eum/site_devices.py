"""WEBMAN380M00 현장별단말기목록 조회.

주의: 이 화면은 헤더가 3행(14/19/9열)인데 데이터 행은 2행(24/13열) 패턴이라
헤더-데이터가 1:1로 깔끔하게 안 맞는다(단말기설치현황과 다름). 잘못된 필드명
매핑으로 데이터를 왜곡시키느니, 원본 셀 배열(row1_cells/row2_cells)을
그대로 보존해서 반환한다 — 특정 필드가 필요해지면 그때 위치를 확인해 매핑.

사용:
    from scripts.eum.site_devices import fetch_site_devices
    rows = fetch_site_devices(page)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

EUM_BASE = "https://eum.cw.or.kr"
SITE_DEVICES_URL = f"{EUM_BASE}/web/man/WEBMAN380M00"

_EXTRACT_JS = """
() => {
  const table = document.querySelectorAll('table')[1];
  if (!table) return [];
  const rows = [];
  table.querySelectorAll('tr').forEach(tr => {
    const tds = tr.querySelectorAll('td');
    if (tds.length === 0) return;
    rows.push({ td_count: tds.length, cells: Array.from(tds).map(td => (td.innerText || '').trim()) });
  });
  return rows;
}
"""


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


def fetch_site_devices(page) -> list[dict[str, Any]]:
    """현장별단말기목록 화면 조회 → 원본 셀 배열 기준 레코드 목록(필드명 미매핑)."""
    from scripts.eum.menu_actions import open_menu_page

    open_menu_page(page, "현장별단말기목록")
    page.evaluate(
        "() => { const b = Array.from(document.querySelectorAll('button'))"
        ".find(e => e.textContent.trim() === '조회'); if (b) b.click(); }"
    )
    page.wait_for_timeout(1500)

    raw_rows = page.evaluate(_EXTRACT_JS)
    records: list[dict[str, Any]] = []
    i = 0
    while i < len(raw_rows) - 1:
        r1, r2 = raw_rows[i], raw_rows[i + 1]
        if r1["td_count"] > r2["td_count"]:
            records.append({"row1_cells": r1["cells"], "row2_cells": r2["cells"]})
            i += 2
        else:
            i += 1
    return records


def save_site_devices(records: list[dict[str, Any]]) -> Path:
    out = _eum_dir() / "eum_site_devices_latest.json"
    payload = {
        "fetched_at": datetime.now().isoformat(),
        "count": len(records),
        "note": "필드명 미매핑 — row1_cells/row2_cells 원본 순서 그대로 보존",
        "records": records,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    from scripts.browser.cdp.connection import get_page
    from scripts.eum.menu_actions import fetch_save_print

    fetch_save_print(get_page(), fetch_site_devices, save_site_devices, "현장별단말기목록")


if __name__ == "__main__":
    main()
