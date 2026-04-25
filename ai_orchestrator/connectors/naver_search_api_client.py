"""Naver Search Open API 클라이언트 (F-4S-2).

지원 검색 종류: blog / news / cafearticle / shop / webkr.

설계 원칙:
- GET 전용. 카페 가입/글쓰기/댓글 등 쓰기 흐름 절대 추가 금지.
- 비로그인 공개 검색 API 한정. 사용자 자격증명 / 쿠키 / storage_state 의존 없음.
- live=False 또는 키 없음이면 mock_or_disabled 반환 (실제 호출 없음).
- requests 의존 금지 — stdlib urllib 사용.
- transport 주입(DI) — 테스트에서 실제 네트워크 미사용.
- client_id / client_secret 은 헤더로만 전달하고, 로그/응답 어디에도 원문 노출 금지.
- 브라우저/Playwright import 금지.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode

from . import naver_search_api_config as cfg_mod

logger = logging.getLogger(__name__)


SUPPORTED_TYPES: Tuple[str, ...] = (
    "blog",
    "news",
    "cafearticle",
    "shop",
    "webkr",
)

ENDPOINT_BY_TYPE: Dict[str, str] = {
    "blog": "/blog.json",
    "news": "/news.json",
    "cafearticle": "/cafearticle.json",
    "shop": "/shop.json",
    "webkr": "/webkr.json",
}

ALLOWED_SORT_BY_TYPE: Dict[str, Tuple[str, ...]] = {
    "blog": ("sim", "date"),
    "news": ("sim", "date"),
    "cafearticle": ("sim", "date"),
    "shop": ("sim", "date", "asc", "dsc"),
    "webkr": (),
}

DISPLAY_MIN, DISPLAY_MAX = 1, 100
START_MIN, START_MAX = 1, 1000


class NaverSearchApiError(Exception):
    """검색 API 호출 단계에서 발생한 오류."""


# Transport: takes (url, headers, timeout) → (status, body_text). 테스트는 fake transport 주입.
Transport = Callable[[str, Dict[str, str], float], Tuple[int, str]]


def normalize_search_type(search_type: Optional[str]) -> str:
    if not search_type or not isinstance(search_type, str):
        raise ValueError("search_type is required")
    normalized = search_type.strip().lower()
    aliases = {
        "cafe": "cafearticle",
        "cafe_article": "cafearticle",
        "shopping": "shop",
        "web": "webkr",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_TYPES:
        raise ValueError(
            f"unsupported search_type: {search_type!r}. supported={SUPPORTED_TYPES}"
        )
    return normalized


def validate_search_params(
    query: Optional[str],
    display: int = 10,
    start: int = 1,
    sort: Optional[str] = None,
    search_type: Optional[str] = None,
) -> Dict[str, Any]:
    if not query or not isinstance(query, str) or not query.strip():
        raise ValueError("query is required and must be non-empty string")

    try:
        display_int = int(display)
    except (TypeError, ValueError) as exc:
        raise ValueError("display must be an integer") from exc
    if not (DISPLAY_MIN <= display_int <= DISPLAY_MAX):
        raise ValueError(
            f"display out of range: {display_int} (allowed {DISPLAY_MIN}..{DISPLAY_MAX})"
        )

    try:
        start_int = int(start)
    except (TypeError, ValueError) as exc:
        raise ValueError("start must be an integer") from exc
    if not (START_MIN <= start_int <= START_MAX):
        raise ValueError(
            f"start out of range: {start_int} (allowed {START_MIN}..{START_MAX})"
        )

    sort_value: Optional[str] = None
    if sort is not None and str(sort).strip():
        sort_normalized = str(sort).strip().lower()
        if search_type is not None:
            allowed = ALLOWED_SORT_BY_TYPE.get(search_type, ())
            if not allowed:
                raise ValueError(
                    f"sort is not supported for search_type={search_type!r}"
                )
            if sort_normalized not in allowed:
                raise ValueError(
                    f"sort {sort_normalized!r} not in allowed {allowed} for {search_type!r}"
                )
        sort_value = sort_normalized

    return {
        "query": query.strip(),
        "display": display_int,
        "start": start_int,
        "sort": sort_value,
    }


def _mask_url_secret(url: str) -> str:
    # 검색 API는 secret을 query string으로 보내지 않지만, 방어적으로 client_id/secret 유사 키를 마스킹.
    masked = url
    for key in ("client_id", "client_secret", "X-Naver-Client-Id", "X-Naver-Client-Secret"):
        marker = f"{key}="
        if marker in masked:
            head, _, rest = masked.partition(marker)
            tail_sep = "&" if "&" in rest else ""
            _, _, tail = rest.partition("&") if tail_sep else (rest, "", "")
            masked = f"{head}{marker}***{('&' + tail) if tail else ''}"
    return masked


def _default_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
    req = urllib_request.Request(url, headers=headers, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (read-only public API)
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
            return resp.status, body
    except urllib_error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return exc.code, body


def _build_url(base_url: str, search_type: str, params: Dict[str, Any]) -> str:
    endpoint = ENDPOINT_BY_TYPE[search_type]
    qs_params: Dict[str, Any] = {
        "query": params["query"],
        "display": params["display"],
        "start": params["start"],
    }
    if params.get("sort"):
        qs_params["sort"] = params["sort"]
    return f"{base_url}{endpoint}?{urlencode(qs_params, encoding='utf-8')}"


def _summarize_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summaries.append(
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "description": item.get("description"),
                "postdate": item.get("postdate"),
                "pubDate": item.get("pubDate"),
                "bloggername": item.get("bloggername"),
                "cafename": item.get("cafename"),
                "mallName": item.get("mallName"),
            }
        )
    return summaries


def search_naver(
    search_type: str,
    query: str,
    display: int = 10,
    start: int = 1,
    sort: Optional[str] = None,
    live: bool = False,
    config: Optional[cfg_mod.NaverSearchApiConfig] = None,
    transport: Optional[Transport] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    cfg = config if config is not None else cfg_mod.load_naver_search_api_config()

    normalized_type = normalize_search_type(search_type)
    params = validate_search_params(
        query=query,
        display=display,
        start=start,
        sort=sort,
        search_type=normalized_type,
    )

    if not live:
        return {
            "success": True,
            "mode": "mock_or_disabled",
            "search_type": normalized_type,
            "query": params["query"],
            "total": 0,
            "start": params["start"],
            "display": params["display"],
            "items": [],
            "warnings": ["live=False — no API call performed"],
        }

    if not cfg.live_enabled:
        warnings.append(
            "live=True requested but NAVER_CLIENT_ID / NAVER_CLIENT_SECRET missing"
        )
        return {
            "success": True,
            "mode": "mock_or_disabled",
            "search_type": normalized_type,
            "query": params["query"],
            "total": 0,
            "start": params["start"],
            "display": params["display"],
            "items": [],
            "warnings": warnings,
        }

    url = _build_url(cfg.base_url, normalized_type, params)
    headers = {
        "X-Naver-Client-Id": cfg.client_id or "",
        "X-Naver-Client-Secret": cfg.client_secret or "",
        "User-Agent": "haehan-ai-orchestrator/naver-search-api-poc",
        "Accept": "application/json",
    }

    masked_url = _mask_url_secret(url)
    logger.info("naver_search_api request type=%s url=%s", normalized_type, masked_url)

    tx = transport if transport is not None else _default_transport
    try:
        status, body = tx(url, headers, cfg.timeout_seconds)
    except Exception as exc:  # network / DNS / timeout
        return {
            "success": False,
            "mode": "live",
            "search_type": normalized_type,
            "query": params["query"],
            "total": 0,
            "start": params["start"],
            "display": params["display"],
            "items": [],
            "error": f"transport_error: {type(exc).__name__}",
            "warnings": warnings,
        }

    if status != 200:
        # 응답 본문에 키가 노출될 가능성은 낮지만, 본문 길이만 알린다.
        return {
            "success": False,
            "mode": "live",
            "search_type": normalized_type,
            "query": params["query"],
            "total": 0,
            "start": params["start"],
            "display": params["display"],
            "items": [],
            "error": f"http_{status}",
            "body_length": len(body or ""),
            "warnings": warnings,
        }

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {
            "success": False,
            "mode": "live",
            "search_type": normalized_type,
            "query": params["query"],
            "total": 0,
            "start": params["start"],
            "display": params["display"],
            "items": [],
            "error": "invalid_json",
            "body_length": len(body or ""),
            "warnings": warnings,
        }

    items_raw = payload.get("items") or []
    items = _summarize_items(items_raw if isinstance(items_raw, list) else [])

    return {
        "success": True,
        "mode": "live",
        "search_type": normalized_type,
        "query": params["query"],
        "total": int(payload.get("total", 0) or 0),
        "start": int(payload.get("start", params["start"]) or params["start"]),
        "display": int(payload.get("display", params["display"]) or params["display"]),
        "items": items,
        "warnings": warnings,
    }
