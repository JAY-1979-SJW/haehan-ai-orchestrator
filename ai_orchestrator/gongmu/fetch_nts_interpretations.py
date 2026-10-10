"""국세청 국세법령정보시스템(taxlaw.nts.go.kr) 통합검색에서 "세법해석례"
(질의회신·사전답변·과세기준자문·고시서면질의)만 골라 수집한다.

이 사이트는 handlebars.js로 클라이언트 렌더링해서 requests로는 검색이 안 되고
(form 태그 자체가 없음, 확인 완료) CDP 브라우저로 렌더링된 DOM을 캡처해야 한다.
URL 파라미터 schVcb=<검색어>로 통합검색 결과 페이지가 뜨는 걸 확인했다 —
클릭 조작 없이 goto 한 번으로 충분하다.

board_box 안에 "내용 더보기"를 눌러야 보이는 숨김 span까지 이미 DOM에 렌더링돼
있어(display:none) 별도 클릭 없이 전문을 긁을 수 있다.

사용법:
  python -m ai_orchestrator.gongmu.fetch_nts_interpretations <검색어1> <검색어2> ...  (저장소 루트에서)
출력: data/nts_interpretations/<검색어>.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

from ai_orchestrator.paths import repo_root

ROOT = repo_root()
VISITS_DIR = ROOT / "data" / "manual_visits" / "taxlaw.nts.go.kr"
OUT_DIR = ROOT / "data" / "nts_interpretations"

# 세법해석례로 취급할 legislation_list 카테고리 title 값
INTERP_CATEGORIES = {"질의회신", "사전답변", "과세기준자문", "고시서면질의"}


def run_in_repo(cmd: list[str]) -> str:
    """저장소 루트에서 명령 실행(CDP 클라이언트 호출용) — stdout+stderr 를 돌려준다."""
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=60)
    return r.stdout + r.stderr


def latest_html_after(marker_files: set[str]) -> str | None:
    """marker_files 이후 새로 생긴 CDP 스냅샷 HTML 중 가장 최근 것(없으면 None). fetch_tax_precedent_summary 도 쓴다."""
    files = {str(p) for p in VISITS_DIR.glob("*.html")}
    new = files - marker_files
    if not new:
        return None
    return max(new, key=os.path.getmtime)


def _extract_interpretations(html_path: str) -> list[dict]:
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")
    results = []
    for box in soup.select("div.board_box"):
        cats = [li.get("title", "").strip() for li in box.select(".legislation_list li")]
        if not any(c in INTERP_CATEGORIES for c in cats):
            continue  # 법령/판례/서식/전자도서관/상담사례 등은 다른 수집기 담당
        title_el = box.select_one(".subs_title strong")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        detail_lis = box.select(".subs_detail li")
        doc_no, registered_at, produced_at = "", "", ""
        for li in detail_lis:
            label = li.get_text(" ", strip=True)
            if "등록일자" in label:
                registered_at = li.select_one(".num").get_text(strip=True) if li.select_one(".num") else ""
            elif "생산일자" in label:
                produced_at = li.select_one(".num").get_text(strip=True) if li.select_one(".num") else ""
            elif not doc_no:
                doc_no = li.get_text(" ", strip=True)
        body_el = box.select_one(".subs_text p")
        body = body_el.get_text(" ", strip=True) if body_el else ""
        results.append(
            {
                "category": next((c for c in cats if c in INTERP_CATEGORIES), ""),
                "tax_label": next((c for c in cats if c not in INTERP_CATEGORIES), ""),
                "doc_no": doc_no,
                "title": title,
                "registered_at_raw": registered_at,
                "produced_at_raw": produced_at,
                "body": body,
            }
        )
    return results


def fetch_keyword(keyword: str) -> list[dict]:
    before = {str(p) for p in VISITS_DIR.glob("*.html")}
    q = urllib.parse.quote(keyword)
    run_in_repo(
        ["python", "scripts/entry/cdp_cli.py", "goto", f"https://taxlaw.nts.go.kr/is/USEISA001M.do?schVcb={q}&searchType="]
    )
    run_in_repo(["python", "scripts/entry/cdp_cli.py", "snapshot"])
    html_path = latest_html_after(before)
    if not html_path:
        return []
    return _extract_interpretations(html_path)


def main() -> None:
    keywords = sys.argv[1:] or ["부가가치세"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    all_items = []
    for kw in keywords:
        print(f"검색: {kw}")
        items = fetch_keyword(kw)
        added = 0
        for it in items:
            key = it["doc_no"]
            if not key or key in seen:
                continue
            seen.add(key)
            it["matched_keyword"] = kw
            all_items.append(it)
            added += 1
        print(f"  세법해석례 {added}건 추가(누적 {len(all_items)})")
        time.sleep(1.0)

    out_path = OUT_DIR / "nts_interpretations_index.json"
    out_path.write_text(
        json.dumps({"unique_count": len(all_items), "items": all_items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장: {out_path} (unique={len(all_items)})")


if __name__ == "__main__":
    main()
