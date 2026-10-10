"""WEBMAN470M00 테스트근로자등록 조회.

등록된 테스트용 근로자 목록을 추출한다. 단일 행/레코드 테이블.

사용:
    from scripts.eum.test_workers import fetch_test_workers
    rows = fetch_test_workers(page)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

EUM_BASE = "https://eum.cw.or.kr"
TEST_WORKERS_URL = f"{EUM_BASE}/web/man/WEBMAN470M00"

HEADERS_REFERENCE = ["NO", "업체명", "성명", "생년월일", "등록일"]

_EXTRACT_JS = """
() => {
  const table = document.querySelectorAll('table')[1];
  if (!table) return { headers: [], rows: [] };
  const thead = table.querySelector('thead');
  const headers = thead ? Array.from(thead.querySelectorAll('th')).map(th => (th.innerText || '').trim()) : [];
  const rows = [];
  table.querySelectorAll('tbody tr, tr').forEach(tr => {
    const tds = tr.querySelectorAll('td');
    if (tds.length === 0) return;
    rows.push(Array.from(tds).map(td => (td.innerText || '').trim()));
  });
  return { headers, rows };
}
"""


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


def fetch_test_workers(page) -> list[dict[str, Any]]:
    """테스트근로자등록 화면 조회 → 레코드 목록. 마지막 열(삭제 버튼)은 제외."""
    from scripts.eum.menu_actions import open_menu_page

    open_menu_page(page, "테스트근로자등록")
    page.evaluate(
        "() => { const b = Array.from(document.querySelectorAll('button'))"
        ".find(e => e.textContent.trim() === '조회'); if (b) b.click(); }"
    )
    page.wait_for_timeout(1500)

    result = page.evaluate(_EXTRACT_JS)
    headers = result.get("headers") or HEADERS_REFERENCE
    records = []
    for cells in result.get("rows", []):
        record = {h: (cells[i] if i < len(cells) else "") for i, h in enumerate(headers)}
        if len(cells) != len(headers):
            record["_raw_cells"] = cells
        records.append(record)
    return records


def save_test_workers(records: list[dict[str, Any]]) -> Path:
    out = _eum_dir() / "eum_test_workers_latest.json"
    payload = {"fetched_at": datetime.now().isoformat(), "count": len(records), "records": records}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    records = fetch_test_workers(page)
    path = save_test_workers(records)
    print(f"테스트근로자등록: {len(records)}건 조회 → {path}")


if __name__ == "__main__":
    main()
