"""Google Search Console 실측 검색어 수집 — CDP 브라우저 세션 재사용.

haehan-ai.kr 사이트로 실제 유입된 구글 검색어(클릭·노출·CTR·평균순위)를
Search Console 실적 화면에서 스크래핑해 저장한다. OpenAPI/OAuth 신규 발급
없이, 이미 로그인돼 있는 CDP 브라우저 세션(스마트스토어/네이버 자동화와
동일 프로필)을 그대로 재사용한다.

네이버 카페/검색광고 리서치(research_blog_topics.py)가 잡지 못하는
"구글 전용 실제 검색 신호"를 보완하는 용도 — 블로그 주제 선정 시
참고 소스로만 쓴다(자동 병합은 아직 하지 않음, 별도 승인 후 연결).

출력: data/gsc_queries_latest.json
      {"generated_at", "site": "sc-domain:haehan-ai.kr", "range_days": 90,
       "queries": [{"query", "clicks", "impressions", "ctr", "position"}]}

사용:
    python -m scripts.google.search.fetch_gsc_queries
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from scripts.common.logger import get_logger  # noqa: E402

logger = get_logger("scripts.google.search.fetch_gsc_queries")

CDP_URL = "http://127.0.0.1:9222"
SITE_RESOURCE = "sc-domain:haehan-ai.kr"
GSC_URL = f"https://search.google.com/search-console/performance/search-analytics?resource_id={SITE_RESOURCE}"
OUTPUT_PATH = _ROOT / "data" / "gsc_queries_latest.json"

_ROW_RE = re.compile(r"^(.+?)\t(\d+)\t([\d.]+)천?$")


def _parse_query_table(text: str) -> list[dict]:
    """'실적' 페이지 inner_text 원문에서 '인기 검색어' 표를 파싱한다.

    각 데이터 행은 "쿼리\t클릭수\t노출수" 형태로 한 줄에 탭 구분되어 나온다
    (헤더 줄만 '클릭수'/'노출'이 탭과 함께 별도 줄로 쪼개져 있음).
    """
    lines = text.splitlines()
    try:
        start = lines.index("인기 검색어") + 1
    except ValueError:
        return []
    rows: list[dict] = []
    for line in lines[start:]:
        if line.startswith("페이지당 행 수"):
            break
        if "\t" not in line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) != 3:
            continue
        query, clicks_raw, impr_raw = parts
        if not clicks_raw.isdigit() or not impr_raw.isdigit():
            continue
        rows.append({"query": query, "clicks": int(clicks_raw), "impressions": int(impr_raw)})
    return rows


def fetch_gsc_queries(range_days: int = 90) -> list[dict]:
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.goto(GSC_URL, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # 표시 행 수를 250으로 늘려 한 페이지에서 모두 수집
        try:
            page.get_by_text("총", exact=False).first.wait_for(timeout=8000)
        except Exception:  # noqa: BLE001 - Google Search Console 실적 표 읽기전용 조회 — 로딩 대기(wait_for) 타임아웃을 경고 로그로 남기고 그대로 진행, 텍스트 파싱은 이후 별도로 수행.
            logger.warning("[gsc] 실적 표 로딩 대기 실패 — 그대로 진행")

        text = page.inner_text("body")
        page.close()

    rows = _parse_query_table(text)
    logger.info(f"[gsc] 쿼리 {len(rows)}개 수집")
    return rows


def main() -> None:
    rows = fetch_gsc_queries()
    if not rows:
        logger.warning("[gsc] 수집된 쿼리 없음 — GSC 로그인/사이트 등록 상태 확인 필요")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "site": SITE_RESOURCE,
        "range_days": 90,
        "queries": rows,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {OUTPUT_PATH} ({len(rows)}개 쿼리)")
    for r in rows[:10]:
        print(f"  {r['query']:<20} 클릭 {r['clicks']:>3}  노출 {r['impressions']:>5}")


if __name__ == "__main__":
    main()
