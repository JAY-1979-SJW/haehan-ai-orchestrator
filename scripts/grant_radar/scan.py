"""scan.py — 정부 포털 지원사업 공고 스캔 (별도 헤드리스 브라우저).

메인 Chrome(9222)과 무관한 headless Chromium을 띄워 여러 포털의 공고 목록을 추출한다.
로그인 불필요한 공개 페이지만 대상. 결과를 data/grant_radar/scan_latest.json 에 저장.

포털별 추출 모드:
  - "anchor": 상세 링크(href)가 있는 포털 → 링크+행텍스트 추출 (NIPA·기업마당·중기부)
  - "rows"  : 상세가 javascript 호출인 포털 → 행 텍스트만 추출, 링크는 목록 URL (CCEI)

실행:
    python -m scripts.grant_radar.scan
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 영속 데이터 경로 — HAEHAN_DATA_DIR(번들/Electron) 우선, 없으면 소스 레이아웃(dev)
_ENV_DATA = os.environ.get("HAEHAN_DATA_DIR")
OUT_DIR = (
    (Path(_ENV_DATA) / "grant_radar") if _ENV_DATA else (Path(__file__).resolve().parents[2] / "data" / "grant_radar")
)
OUT_FILE = OUT_DIR / "scan_latest.json"

PER_PORTAL_CAP = 40

# 스캔 대상 포털 (공개 목록 페이지)
PORTALS = [
    {
        "key": "NIPA",
        "name": "정보통신산업진흥원",
        "url": "https://www.nipa.kr/home/2-2",
        "mode": "anchor",
        "detail_pattern": "/home/2-2/",
    },
    {
        "key": "BIZINFO",
        "name": "기업마당(중앙·지자체 통합)",
        "url": "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do",
        "mode": "anchor",
        "detail_pattern": "/sii/siia/selectSIIA",
    },
    {
        "key": "MSS",
        "name": "중소벤처기업부",
        "url": "https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=310",
        "mode": "anchor",
        "detail_pattern": "/site/smba/contents/view.do",
    },
    {
        "key": "CCEI",
        "name": "서울창조경제혁신센터",
        "url": "https://ccei.creativekorea.or.kr/seoul/custom/notice_list.do",
        "mode": "rows",
    },
    {
        "key": "SMES",
        "name": "중소벤처24(소상공인·중소기업 통합)",
        "url": "https://www.smes.go.kr/main/sportsBsnsPolicy?progress=ok&cntPerPage=30",
        "mode": "rows",
    },
    {
        "key": "SBA",
        "name": "서울경제진흥원",
        "url": "https://www.sba.seoul.kr/kr/sbcu31l1",
        "mode": "rows",
    },
]

# ── anchor 모드: 상세 링크 + 행 텍스트 ────────────────────────────────────────
_ANCHOR_JS = """
(pattern) => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.href || '';
    if (!href.includes(pattern)) return;
    let row = a.closest('li,tr,article,.item,.board-item,.list-item') || a.parentElement;
    const raw = ((row && row.innerText) || a.innerText || '').trim().replace(/\\s+/g, ' ');
    const title = (a.innerText || '').trim().replace(/\\s+/g, ' ');
    const key = href + '|' + title;
    if (seen.has(key) || raw.length < 10 || !title) return;
    seen.add(key);
    out.push({ title, url: href, raw });
  });
  return out;
}
"""

# ── rows 모드: 날짜 포함 행 텍스트(상세가 JS 호출인 포털) ──────────────────────
_ROWS_JS = """
() => {
  const out = [];
  const seen = new Set();
  const dateRe = /(20\\d\\d[.\\-]\\d{1,2}[.\\-]\\d{1,2})|(\\d{2}-\\d{2}-\\d{2})|(D-\\d+)/;
  document.querySelectorAll('tr, li').forEach(e => {
    const t = (e.innerText || '').trim().replace(/\\s+/g, ' ');
    if (t.length < 15 || t.length > 200) return;
    if (!dateRe.test(t)) return;
    // 네비게이션/메뉴 행 제외 (포털 범용)
    if (/센터소개|알림마당 사업공고 입찰|로그인 창조경제|전체 사업 접수중|전체메뉴|사업소개 사업공고/.test(t)) return;
    if (seen.has(t)) return;
    seen.add(t);
    out.push({ title: t.slice(0, 80), url: location.href, raw: t });
  });
  return out;
}
"""


logger = logging.getLogger(__name__)


def _extract(page, portal: dict, errors: list | None = None) -> list[dict]:
    try:
        if portal["mode"] == "anchor":
            rows = page.evaluate(_ANCHOR_JS, portal["detail_pattern"])
        else:
            rows = page.evaluate(_ROWS_JS)
        return rows[:PER_PORTAL_CAP]
    except Exception as e:
        logger.warning("%s 추출 오류: %s", portal["key"], e, exc_info=True)
        print(f"[scan] {portal['key']} 추출 오류: {e}")
        if errors is not None:
            errors.append(f"{portal['key']} 추출 오류: {e}")
        return []


def scan_all() -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"ok": False, "error": f"playwright 미설치: {e}", "items": []}

    items: list[dict] = []
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)  # 메인 Chrome과 분리된 별도 인스턴스
        page = browser.new_page()
        for portal in PORTALS:
            try:
                page.goto(portal["url"], wait_until="networkidle", timeout=40000)
                page.wait_for_timeout(1800)
                rows = _extract(page, portal, errors)
                for r in rows:
                    r["portal"] = portal["key"]
                    r["portal_name"] = portal["name"]
                items.extend(rows)
                print(f"[scan] {portal['key']}: {len(rows)}건")
            except Exception as e:
                msg = f"{portal['key']} 스캔 실패: {e}"
                errors.append(msg)
                logger.warning(msg, exc_info=True)
                print(f"[scan] {msg}")
        browser.close()

    return {
        "ok": True,
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "portals": [p["key"] for p in PORTALS],
        "count": len(items),
        "errors": errors,
        "items": items,
    }


def main() -> int:
    result = scan_all()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[scan] 저장: {OUT_FILE} (count={result.get('count', 0)})")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
