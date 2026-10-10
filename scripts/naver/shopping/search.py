"""네이버 쇼핑 검색 — 비로그인 OpenAPI 래퍼 + 게이트.

주의(2026-08-14 실측): 이 프로젝트 앱에는 **쇼핑 검색 API가 등록되어 있지 않다.**
    /v1/search/blog.json  → OK
    /v1/search/news.json  → OK
    /v1/search/shop.json  → 404 SE05 "존재하지 않는 검색 api 입니다"
따라서 현재 이 모듈은 status="error"(SE05)를 반환한다. 경쟁사 가격 조사는
crawl.py(공개 검색결과 CDP 수집)를 사용할 것. 앱에 쇼핑 검색 API가 추가
등록되면 별도 수정 없이 정상 동작한다.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (2026-08-14: [4]는 저장소 밖 C:\work 를 가리켰음)
sys.path.insert(0, str(ROOT))

# .env 미로드 시 config 가 조용히 dry_run=True 로 빠져 mock 1건을 실제
# 결과인 것처럼 반환하는 사고가 있었다(2026-08-14). 진입점에서 명시 로드한다.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", encoding="utf-8")
except Exception:  # noqa: BLE001 - .env 로드 실패 무시(선택적 설정 로딩), API 오류 응답 바디 JSON 파싱 실패시 빈 dict로 폴백 후 오류 로깅
    pass

from .gate import gate_search  # noqa: E402  (sys.path 설정 후 import)
from .policy import SEARCH_DAILY_LIMIT  # noqa: E402  (sys.path 설정 후 import)

_log = logging.getLogger(__name__)


def search_shopping(
    query: str,
    display: int = 10,
    sort: str = "sim",
    *,
    max_pages: int = 1,
) -> dict:
    """네이버 쇼핑 검색 — 게이트 통과 후 OpenAPI 호출.

    display: 1페이지당 건수(네이버 상한 100). max_pages 와 곱한 만큼 수집.
    start 상한이 1000 이라 실제 수집 가능한 최대치는 1000건.
    """
    gate_search(query)

    import json
    import urllib.error
    import urllib.request

    from scripts.naver.shopping.naver_openapi_config import load_config
    from scripts.naver.shopping.naver_search_jobs import run_naver_shopping_search_job
    from scripts.naver.shopping.naver_search_client import NaverSearchClient

    def _transport(method, url, headers, params):
        # url 은 client.build_url() 이 params 를 이미 쿼리스트링으로 붙여서 넘긴다.
        # params 를 여기서 또 붙이면 중복되므로 그대로 두되, 계약상 인자는 받는다.
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            # 예외로 던지면 client 가 TRANSPORT_EXCEPTION 으로 뭉개서 원인이 사라진다.
            # 네이버가 주는 errorCode(예: SE05 = 앱에 해당 검색 API 미등록)를 살린다.
            try:
                body = json.loads(e.read().decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001 - .env 로드 실패 무시(선택적 설정 로딩), API 오류 응답 바디 JSON 파싱 실패시 빈 dict로 폴백 후 오류 로깅
                body = {}
            _log.warning(
                "[SHOPPING-SEARCH-HTTP-%s] errorCode=%s message=%s",
                e.code,
                body.get("errorCode"),
                body.get("errorMessage"),
            )
            return e.code, body

    cfg = load_config()
    if cfg.dry_run:
        _log.warning(
            "[SHOPPING-SEARCH-DRY-RUN] 자격증명 미설정 또는 DRY_RUN=true — 반환값은 실제 검색 결과가 아닌 mock 이다."
        )

    client = NaverSearchClient(config=cfg, transport=_transport)

    outcome = run_naver_shopping_search_job(
        query=query,
        display=display,
        sort=sort,
        max_pages=max_pages,
        client=client,
    )
    return {
        "status": outcome.status,
        "is_live": outcome.status == "ok",
        "query": query,
        "requested_display": display,
        "requested_max_pages": max_pages,
        "item_count": outcome.item_count,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
        "db_status": outcome.db_status,
        "inserted": outcome.inserted_count,
        "daily_limit": SEARCH_DAILY_LIMIT,
    }
