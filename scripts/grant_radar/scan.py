"""scan.py — 정부 포털 지원사업 공고 스캔 (별도 헤드리스 브라우저).

메인 Chrome(9222)과 무관한 headless Chromium을 띄워 공고 목록을 추출한다.
로그인 불필요한 공개 페이지만 대상. 결과를 data/grant_radar/scan_latest.json 에 저장.

실행:
    python -m scripts.grant_radar.scan
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "grant_radar"
OUT_FILE = OUT_DIR / "scan_latest.json"

# 스캔 대상 포털 (공개 목록 페이지)
PORTALS = [
    {
        "key": "NIPA",
        "name": "정보통신산업진흥원",
        "url": "https://www.nipa.kr/home/2-2",
        # 상세 링크 패턴: /home/2-2/<번호>
        "detail_pattern": "/home/2-2/",
    },
]


def _extract_rows(page, detail_pattern: str) -> list[dict]:
    """상세 링크를 가진 목록 행에서 (제목·원문텍스트·링크)를 추출."""
    js = """
    (pattern) => {
      const out = [];
      const seen = new Set();
      document.querySelectorAll('a').forEach(a => {
        const href = a.href || '';
        if (!href.includes(pattern)) return;
        if (!/\\/(\\d+)(\\?|$|#)/.test(href)) return;  // 상세 번호 링크만
        // 행 컨테이너로 올라가 원문 텍스트 확보(날짜·담당자 포함)
        let row = a.closest('li,tr,article,.item,.board-item') || a.parentElement;
        const raw = ((row && row.innerText) || a.innerText || '').trim().replace(/\\s+/g, ' ');
        const title = (a.innerText || '').trim().replace(/\\s+/g, ' ');
        const key = href + '|' + title;
        if (seen.has(key) || raw.length < 8) return;
        seen.add(key);
        out.push({ title, url: href, raw });
      });
      return out;
    }
    """
    try:
        return page.evaluate(js, detail_pattern)
    except Exception as e:
        print(f"[scan] 추출 오류: {e}")
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
                page.goto(portal["url"], wait_until="networkidle", timeout=35000)
                page.wait_for_timeout(1500)
                rows = _extract_rows(page, portal["detail_pattern"])
                for r in rows:
                    r["portal"] = portal["key"]
                    r["portal_name"] = portal["name"]
                items.extend(rows)
                print(f"[scan] {portal['key']}: {len(rows)}건")
            except Exception as e:
                msg = f"{portal['key']} 스캔 실패: {e}"
                errors.append(msg)
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
