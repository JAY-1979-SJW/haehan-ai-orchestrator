"""WEBMAN460M00 근로내역테스트 조회.

전자카드 태그 출퇴근 테스트 기록을 추출한다. 단일 행/레코드 테이블이라
단말기설치현황(WEBMAN390M00)과 달리 2행 결합 로직이 필요 없다.

사용:
    from scripts.eum.labor_test import fetch_labor_test
    rows = fetch_labor_test(page)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

EUM_BASE = "https://eum.cw.or.kr"
LABOR_TEST_URL = f"{EUM_BASE}/web/man/WEBMAN460M00"

# 참고용 기본 헤더(2026-08-16 실측, 12열). 실제 매핑은 매 조회 시 thead에서
# 동적으로 읽는다 — 사이트가 열을 추가/제거해도 값이 밀리지 않게 하기 위함.
HEADERS_REFERENCE = [
    "NO",
    "일자",
    "공사번호",
    "현장명",
    "단말기ID",
    "카드번호",
    "공제가입번호",
    "성명",
    "태그내역",
    "인증방식",
    "출근시간",
    "퇴근시간",
]

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


def fetch_labor_test(page) -> list[dict[str, Any]]:
    """근로내역테스트 화면 조회 → 레코드 목록."""
    from scripts.eum.menu_actions import open_menu_page

    open_menu_page(page, "근로내역테스트")
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
            record["_raw_cells"] = cells  # 열 개수 불일치 시 원본 보존(안전장치)
        records.append(record)
    return records


def save_labor_test(records: list[dict[str, Any]]) -> Path:
    out = _eum_dir() / "eum_labor_test_latest.json"
    payload = {"fetched_at": datetime.now().isoformat(), "count": len(records), "records": records}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    from scripts.browser.cdp.connection import get_page
    from scripts.eum.menu_actions import fetch_save_print

    fetch_save_print(get_page(), fetch_labor_test, save_labor_test, "근로내역테스트")


if __name__ == "__main__":
    main()
