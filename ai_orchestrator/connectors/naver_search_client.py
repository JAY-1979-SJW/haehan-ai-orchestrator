"""네이버 검색 OpenAPI 공통 클라이언트 (blog / shop).

설계 원칙:
- GET 전용. POST/PUT/DELETE 호출은 차단.
- 비로그인 공개 검색만 사용. 사용자 자격증명 / 세션 / 쿠키 의존 없음.
- transport 주입(DI) — 테스트에서 실제 네트워크 미사용.
- dry_run 모드는 외부 호출을 발생시키지 않고 mock 응답을 반환.
- 응답은 ``SearchResult`` 로 표준화.
- 헤더의 client_id/secret 은 절대 로그에 남기지 않는다 (키 목록만).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from . import naver_openapi_config as cfg_mod

logger = logging.getLogger(__name__)


def _requests_transport(method: str, url: str, headers: dict, params: dict) -> tuple:
    """기본 HTTP transport — requests 라이브러리 사용."""
    import requests

    resp = requests.request(method, url, headers=headers, timeout=10)
    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("네이버 검색 응답 JSON 파싱 실패(무시): %s", type(exc).__name__)
        body = {}
    return resp.status_code, body


SOURCE_BLOG = "naver_blog"
SOURCE_SHOP = "naver_shop"

PATH_BLOG = "/v1/search/blog.json"
PATH_SHOP = "/v1/search/shop.json"

ALLOWED_SORT = {"sim", "date"}
DISPLAY_MIN, DISPLAY_MAX = 1, 100
START_MIN, START_MAX = 1, 1000


@dataclass
class SearchResult:
    source: str  # SOURCE_BLOG / SOURCE_SHOP
    status: str  # "ok" | "dry_run" | "unconfigured" | "error"
    items: list = field(default_factory=list)
    item_count: int = 0
    raw: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    request_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "status": self.status,
            "items": self.items,
            "item_count": self.item_count,
            "raw": self.raw,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "request_summary": self.request_summary,
        }


# ── dry_run mock (네이버 응답 포맷에 맞춘 placeholder, PII 미포함) ──
_BLOG_MOCK_BODY = {
    "lastBuildDate": "<mock-date>",
    "total": 1,
    "start": 1,
    "display": 1,
    "items": [
        {
            "title": "<b>mock</b> blog title",
            "link": "https://blog.example.invalid/mock/1",
            "description": "mock <b>desc</b>",
            "bloggername": "mock-blogger",
            "bloggerlink": "https://blog.example.invalid/mock",
            "postdate": "20260423",
        }
    ],
}

_SHOP_MOCK_BODY = {
    "lastBuildDate": "<mock-date>",
    "total": 1,
    "start": 1,
    "display": 1,
    "items": [
        {
            "title": "<b>mock</b> product",
            "link": "https://shop.example.invalid/p/1",
            "image": "https://shop.example.invalid/p/1.jpg",
            "lprice": "10000",
            "hprice": "12000",
            "mallName": "mock-mall",
            "productId": "mock-pid-1",
            "productType": "1",
            "brand": "mock-brand",
            "maker": "mock-maker",
            "category1": "c1",
            "category2": "c2",
            "category3": "c3",
            "category4": "c4",
        }
    ],
}


class NaverSearchClient:
    """네이버 검색 OpenAPI 얇은 래퍼.

    transport 시그니처:
        ``transport(method, url, headers, params) -> (status:int, body:dict)``
    """

    def __init__(
        self,
        config: cfg_mod.NaverOpenApiConfig | None = None,
        transport: Any | None = None,
    ):
        self._config = config or cfg_mod.load_config()
        self._transport = transport if transport is not None else _requests_transport

    @property
    def config(self) -> cfg_mod.NaverOpenApiConfig:
        return self._config

    # ── 헤더 / URL ──────────────────────────────────────────────
    def build_headers(self) -> dict:
        return {
            "X-Naver-Client-Id": self._config.client_id,
            "X-Naver-Client-Secret": self._config.client_secret,
            "Accept": "application/json",
            "User-Agent": "haehan-ai-orchestrator/naver-search (read-only)",
        }

    def build_url(self, path: str, params: dict) -> str:
        base = self._config.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        qs = urlencode(params, doseq=False)
        return f"{base}{path}?{qs}" if qs else f"{base}{path}"

    # ── 파라미터 정규화 ─────────────────────────────────────────
    @staticmethod
    def _normalize_params(query: str, display: int, start: int, sort: str) -> dict:
        if not query or not query.strip():
            raise ValueError("query 가 비어 있다")
        d = max(DISPLAY_MIN, min(int(display), DISPLAY_MAX))
        s = max(START_MIN, min(int(start), START_MAX))
        srt = sort if sort in ALLOWED_SORT else "sim"
        return {"query": query.strip(), "display": d, "start": s, "sort": srt}

    # ── 공통 GET ────────────────────────────────────────────────
    def _request(
        self,
        *,
        source: str,
        path: str,
        params: dict,
        method: str = "GET",
        dry_run: bool | None = None,
        mock_body: dict | None = None,
    ) -> SearchResult:
        method_u = method.upper()
        if method_u != "GET":
            return SearchResult(
                source=source,
                status="error",
                error_code="METHOD_NOT_ALLOWED",
                error_message=f"method={method_u} 는 비허용 (GET only)",
                request_summary={"method": method_u, "path": path, "param_keys": sorted(params.keys())},
            )

        url = self.build_url(path, params)
        # 토큰/시크릿 없이 요청 요약만 남긴다.
        summary = {
            "method": method_u,
            "path": path,
            "header_keys": sorted(self.build_headers().keys()),
            "param_keys": sorted(params.keys()),
        }

        effective_dry_run = self._config.dry_run if dry_run is None else dry_run
        if effective_dry_run:
            logger.info(
                "[NAVER-SEARCH-DRY-RUN] source=%s path=%s param_keys=%s",
                source,
                path,
                summary["param_keys"],
            )
            body = dict(mock_body or {})
            items = list(body.get("items", []))
            return SearchResult(
                source=source,
                status="dry_run",
                items=items,
                item_count=len(items),
                raw={"note": "dry_run mock", "url": url, "body": body},
                request_summary=summary,
            )

        try:
            cfg_mod.require_live(self._config)
        except cfg_mod.NaverOpenApiConfigError as e:
            logger.warning("[NAVER-SEARCH-UNCONFIGURED] %s", str(e))
            return SearchResult(
                source=source,
                status="unconfigured",
                error_code="MISSING_CREDENTIALS",
                error_message=str(e),
                request_summary=summary,
            )

        if self._transport is None:
            return SearchResult(
                source=source,
                status="error",
                error_code="TRANSPORT_NOT_WIRED",
                error_message="HTTP 전송 계층 미연결",
                request_summary=summary,
            )

        try:
            http_status, body = self._transport(
                method=method_u,
                url=url,
                headers=self.build_headers(),
                params=params,
            )
        except Exception as e:
            logger.exception("[NAVER-SEARCH-TRANSPORT-ERR] type=%s", type(e).__name__)
            return SearchResult(
                source=source,
                status="error",
                error_code="TRANSPORT_EXCEPTION",
                error_message=type(e).__name__,
                request_summary=summary,
            )

        if 200 <= int(http_status) < 300 and isinstance(body, dict):
            items = list(body.get("items", []))
            return SearchResult(
                source=source,
                status="ok",
                items=items,
                item_count=len(items),
                raw={
                    "http_status": int(http_status),
                    "lastBuildDate": body.get("lastBuildDate"),
                    "total": body.get("total"),
                    "start": body.get("start"),
                    "display": body.get("display"),
                },
                request_summary=summary,
            )

        return SearchResult(
            source=source,
            status="error",
            error_code=f"HTTP_{http_status}",
            error_message="non-2xx response",
            raw={"http_status": int(http_status) if isinstance(http_status, int) else None},
            request_summary=summary,
        )

    # ── public ──────────────────────────────────────────────────
    def search_blog(
        self,
        query: str,
        *,
        display: int = 10,
        start: int = 1,
        sort: str = "sim",
        dry_run: bool | None = None,
    ) -> SearchResult:
        params = self._normalize_params(query, display, start, sort)
        return self._request(
            source=SOURCE_BLOG,
            path=PATH_BLOG,
            params=params,
            dry_run=dry_run,
            mock_body=_BLOG_MOCK_BODY,
        )

    def search_shop(
        self,
        query: str,
        *,
        display: int = 10,
        start: int = 1,
        sort: str = "sim",
        dry_run: bool | None = None,
    ) -> SearchResult:
        params = self._normalize_params(query, display, start, sort)
        return self._request(
            source=SOURCE_SHOP,
            path=PATH_SHOP,
            params=params,
            dry_run=dry_run,
            mock_body=_SHOP_MOCK_BODY,
        )


__all__ = [
    "PATH_BLOG",
    "PATH_SHOP",
    "SOURCE_BLOG",
    "SOURCE_SHOP",
    "NaverSearchClient",
    "SearchResult",
]
