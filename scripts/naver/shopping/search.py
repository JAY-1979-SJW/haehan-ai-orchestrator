"""네이버 쇼핑 검색 — 비로그인 OpenAPI 래퍼 + 게이트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from .gate import gate_search
from .policy import SEARCH_DAILY_LIMIT


def search_shopping(query: str, display: int = 10, sort: str = "sim") -> dict:
    """네이버 쇼핑 검색 — 게이트 통과 후 OpenAPI 호출."""
    gate_search(query)

    from ai_orchestrator.connectors.naver_search_jobs import run_naver_shopping_search_job
    import json
    import urllib.request

    def _transport(method, url, headers, params):
        req = urllib.request.Request(url, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())

    from ai_orchestrator.connectors.naver_search_client import NaverSearchClient
    from ai_orchestrator.connectors.naver_openapi_config import load_config
    cfg = load_config()
    client = NaverSearchClient(config=cfg, transport=_transport)

    outcome = run_naver_shopping_search_job(
        query=query, max_pages=1, client=client
    )
    return {
        "status": outcome.status,
        "query": query,
        "item_count": outcome.item_count,
        "db_status": outcome.db_status,
        "inserted": outcome.inserted_count,
        "daily_limit": SEARCH_DAILY_LIMIT,
    }
