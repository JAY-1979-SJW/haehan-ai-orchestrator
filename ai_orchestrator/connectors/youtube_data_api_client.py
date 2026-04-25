"""YouTube Data API v3 클라이언트 (F-4S-3, read-only PoC).

지원 기능 (read-only 한정):
- search_videos: search.list (type=video) — quota cost 100
- get_video_details: videos.list (snippet, statistics, contentDetails) — quota cost 1

설계 원칙:
- GET 전용. 업로드 / 수정 / 삭제 / 댓글 작성 흐름 절대 추가 금지.
- OAuth 미사용. API key (server key) 만 사용.
- live=False 또는 키 없음이면 mock_or_disabled 반환 (실제 호출 없음).
- requests 의존 금지 — stdlib urllib 사용.
- transport 주입(DI) — 테스트에서 실제 네트워크 미사용.
- API key 는 query string으로 전달되지만, 로그/응답 어디에도 원문 노출 금지 (key=*** 마스킹).
- 브라우저 / Playwright import 금지.
- YouTube Studio / 로그인 자동화 절대 금지.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode

from . import youtube_data_api_config as cfg_mod

logger = logging.getLogger(__name__)


SEARCH_ORDERS: Tuple[str, ...] = (
    "relevance",
    "date",
    "viewCount",
    "rating",
    "title",
    "videoCount",
)

MAX_RESULTS_MIN, MAX_RESULTS_MAX = 1, 50
VIDEO_IDS_MAX = 50

QUOTA_COST_SEARCH = 100
QUOTA_COST_VIDEOS = 1

# RFC3339: e.g. 2026-04-26T00:00:00Z 또는 2026-04-26 (날짜만 — 내부에서 보강)
_RFC3339_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RFC3339_FULL = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


class YoutubeDataApiError(Exception):
    """YouTube Data API 호출 단계에서 발생한 오류."""


# Transport: takes (url, headers, timeout) → (status, body_text). 테스트는 fake transport 주입.
Transport = Callable[[str, Dict[str, str], float], Tuple[int, str]]


def _normalize_published_after(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("published_after must be a string (RFC3339 or YYYY-MM-DD)")
    stripped = value.strip()
    if not stripped:
        return None
    if _RFC3339_FULL.match(stripped):
        return stripped
    if _RFC3339_DATE_ONLY.match(stripped):
        return f"{stripped}T00:00:00Z"
    raise ValueError(
        f"published_after must match RFC3339 or YYYY-MM-DD, got {stripped!r}"
    )


def validate_search_params(
    query: Optional[str],
    max_results: int = 5,
    order: str = "relevance",
    published_after: Optional[str] = None,
) -> Dict[str, Any]:
    if not query or not isinstance(query, str) or not query.strip():
        raise ValueError("query is required and must be non-empty string")

    try:
        max_results_int = int(max_results)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_results must be an integer") from exc
    if not (MAX_RESULTS_MIN <= max_results_int <= MAX_RESULTS_MAX):
        raise ValueError(
            f"max_results out of range: {max_results_int} "
            f"(allowed {MAX_RESULTS_MIN}..{MAX_RESULTS_MAX})"
        )

    if order is None or not isinstance(order, str) or not order.strip():
        raise ValueError("order is required")
    order_normalized = order.strip()
    if order_normalized not in SEARCH_ORDERS:
        raise ValueError(
            f"order {order_normalized!r} not in allowed {SEARCH_ORDERS}"
        )

    published_after_norm = _normalize_published_after(published_after)

    return {
        "query": query.strip(),
        "max_results": max_results_int,
        "order": order_normalized,
        "published_after": published_after_norm,
    }


def validate_video_ids(video_ids: Optional[Iterable[str]]) -> List[str]:
    if video_ids is None:
        raise ValueError("video_ids is required")
    if isinstance(video_ids, str):
        # 문자열 단일/콤마 분리 둘 다 허용
        candidates = [v.strip() for v in video_ids.split(",")]
    else:
        try:
            candidates = [str(v).strip() for v in video_ids]
        except TypeError as exc:
            raise ValueError("video_ids must be iterable of strings") from exc
    cleaned = [c for c in candidates if c]
    if not cleaned:
        raise ValueError("video_ids must contain at least one non-empty id")
    if len(cleaned) > VIDEO_IDS_MAX:
        raise ValueError(
            f"video_ids length {len(cleaned)} exceeds max {VIDEO_IDS_MAX}"
        )
    # 단순 형식 검증: 영숫자/하이픈/언더스코어 (YouTube id 11자가 일반적이나 엄격히 11자 강제하지 않음)
    pattern = re.compile(r"^[A-Za-z0-9_\-]+$")
    for v in cleaned:
        if not pattern.match(v):
            raise ValueError(f"video_id contains invalid chars: {v!r}")
    return cleaned


def _mask_url_secret(url: str) -> str:
    masked = url
    for key_name in ("key", "access_token"):
        marker = f"{key_name}="
        if marker not in masked:
            continue
        head, _, rest = masked.partition(marker)
        if "&" in rest:
            _, _, tail = rest.partition("&")
            masked = f"{head}{marker}***&{tail}"
        else:
            masked = f"{head}{marker}***"
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


def _build_search_url(base_url: str, params: Dict[str, Any], api_key: str) -> str:
    qs: Dict[str, Any] = {
        "part": "snippet",
        "type": "video",
        "q": params["query"],
        "maxResults": params["max_results"],
        "order": params["order"],
        "key": api_key,
    }
    if params.get("published_after"):
        qs["publishedAfter"] = params["published_after"]
    return f"{base_url}/search?{urlencode(qs, encoding='utf-8')}"


def _build_videos_url(base_url: str, ids: List[str], api_key: str) -> str:
    qs = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(ids),
        "key": api_key,
    }
    return f"{base_url}/videos?{urlencode(qs, encoding='utf-8')}"


def _summarize_search_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet") or {}
        id_obj = item.get("id") or {}
        if isinstance(id_obj, dict):
            video_id = id_obj.get("videoId")
        else:
            video_id = None
        summaries.append(
            {
                "videoId": video_id,
                "title": snippet.get("title"),
                "channelTitle": snippet.get("channelTitle"),
                "publishedAt": snippet.get("publishedAt"),
                "description": snippet.get("description"),
            }
        )
    return summaries


def _summarize_video_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet") or {}
        statistics = item.get("statistics") or {}
        content_details = item.get("contentDetails") or {}
        summaries.append(
            {
                "videoId": item.get("id"),
                "title": snippet.get("title"),
                "channelTitle": snippet.get("channelTitle"),
                "publishedAt": snippet.get("publishedAt"),
                "viewCount": statistics.get("viewCount"),
                "likeCount": statistics.get("likeCount"),
                "commentCount": statistics.get("commentCount"),
                "duration": content_details.get("duration"),
            }
        )
    return summaries


def _disabled_payload(
    kind: str,
    extra: Dict[str, Any],
    warnings: List[str],
    quota_cost: int,
) -> Dict[str, Any]:
    payload = {
        "success": True,
        "mode": "mock_or_disabled",
        "kind": kind,
        "quota_cost": 0,  # 호출 안 했으므로 실제 사용량 0
        "quota_cost_estimate": quota_cost,
        "items": [],
        "warnings": warnings,
    }
    payload.update(extra)
    return payload


def search_videos(
    query: str,
    max_results: int = 5,
    order: str = "relevance",
    published_after: Optional[str] = None,
    live: bool = False,
    config: Optional[cfg_mod.YoutubeDataApiConfig] = None,
    transport: Optional[Transport] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    cfg = config if config is not None else cfg_mod.load_youtube_data_api_config()

    params = validate_search_params(
        query=query,
        max_results=max_results,
        order=order,
        published_after=published_after,
    )

    base_extra = {
        "query": params["query"],
        "max_results": params["max_results"],
        "order": params["order"],
        "published_after": params["published_after"],
    }

    if not live:
        return _disabled_payload(
            kind="search",
            extra=base_extra,
            warnings=["live=False — no API call performed"],
            quota_cost=QUOTA_COST_SEARCH,
        )

    if not cfg.live_enabled:
        warnings.append(
            "live=True requested but YOUTUBE_DATA_API_KEY missing"
        )
        return _disabled_payload(
            kind="search",
            extra=base_extra,
            warnings=warnings,
            quota_cost=QUOTA_COST_SEARCH,
        )

    api_key = cfg.api_key or ""
    url = _build_search_url(cfg.base_url, params, api_key)
    headers = {
        "User-Agent": "haehan-ai-orchestrator/youtube-data-api-poc",
        "Accept": "application/json",
    }

    masked_url = _mask_url_secret(url)
    logger.info("youtube_data_api search url=%s", masked_url)

    tx = transport if transport is not None else _default_transport
    try:
        status, body = tx(url, headers, cfg.timeout_seconds)
    except Exception as exc:  # network / DNS / timeout
        return {
            "success": False,
            "mode": "live",
            "kind": "search",
            "quota_cost": QUOTA_COST_SEARCH,
            "items": [],
            "error": f"transport_error: {type(exc).__name__}",
            "warnings": warnings,
            **base_extra,
        }

    if status != 200:
        return {
            "success": False,
            "mode": "live",
            "kind": "search",
            "quota_cost": QUOTA_COST_SEARCH,
            "items": [],
            "error": f"http_{status}",
            "body_length": len(body or ""),
            "warnings": warnings,
            **base_extra,
        }

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {
            "success": False,
            "mode": "live",
            "kind": "search",
            "quota_cost": QUOTA_COST_SEARCH,
            "items": [],
            "error": "invalid_json",
            "body_length": len(body or ""),
            "warnings": warnings,
            **base_extra,
        }

    items_raw = payload.get("items") or []
    items = _summarize_search_items(items_raw if isinstance(items_raw, list) else [])

    return {
        "success": True,
        "mode": "live",
        "kind": "search",
        "quota_cost": QUOTA_COST_SEARCH,
        "items": items,
        "warnings": warnings,
        **base_extra,
    }


def get_video_details(
    video_ids: Iterable[str],
    live: bool = False,
    config: Optional[cfg_mod.YoutubeDataApiConfig] = None,
    transport: Optional[Transport] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    cfg = config if config is not None else cfg_mod.load_youtube_data_api_config()

    ids = validate_video_ids(video_ids)
    base_extra = {"video_ids": ids}

    if not live:
        return _disabled_payload(
            kind="videos",
            extra=base_extra,
            warnings=["live=False — no API call performed"],
            quota_cost=QUOTA_COST_VIDEOS,
        )

    if not cfg.live_enabled:
        warnings.append(
            "live=True requested but YOUTUBE_DATA_API_KEY missing"
        )
        return _disabled_payload(
            kind="videos",
            extra=base_extra,
            warnings=warnings,
            quota_cost=QUOTA_COST_VIDEOS,
        )

    api_key = cfg.api_key or ""
    url = _build_videos_url(cfg.base_url, ids, api_key)
    headers = {
        "User-Agent": "haehan-ai-orchestrator/youtube-data-api-poc",
        "Accept": "application/json",
    }

    masked_url = _mask_url_secret(url)
    logger.info("youtube_data_api videos url=%s", masked_url)

    tx = transport if transport is not None else _default_transport
    try:
        status, body = tx(url, headers, cfg.timeout_seconds)
    except Exception as exc:
        return {
            "success": False,
            "mode": "live",
            "kind": "videos",
            "quota_cost": QUOTA_COST_VIDEOS,
            "items": [],
            "error": f"transport_error: {type(exc).__name__}",
            "warnings": warnings,
            **base_extra,
        }

    if status != 200:
        return {
            "success": False,
            "mode": "live",
            "kind": "videos",
            "quota_cost": QUOTA_COST_VIDEOS,
            "items": [],
            "error": f"http_{status}",
            "body_length": len(body or ""),
            "warnings": warnings,
            **base_extra,
        }

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {
            "success": False,
            "mode": "live",
            "kind": "videos",
            "quota_cost": QUOTA_COST_VIDEOS,
            "items": [],
            "error": "invalid_json",
            "body_length": len(body or ""),
            "warnings": warnings,
            **base_extra,
        }

    items_raw = payload.get("items") or []
    items = _summarize_video_items(items_raw if isinstance(items_raw, list) else [])

    return {
        "success": True,
        "mode": "live",
        "kind": "videos",
        "quota_cost": QUOTA_COST_VIDEOS,
        "items": items,
        "warnings": warnings,
        **base_extra,
    }
