"""YouTube video search and comment collection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.common.youtube_search_cache import cache_get as _cache_get
from scripts.common.youtube_search_cache import cache_key as _cache_key

# cache_set: 이 파일은 캐시를 조회만 하고 직접 쓰지 않는다(정리 전부터 그랬음 —
# scripts/google/youtube 쪽 검색 경로가 같은 DB에 써주는 걸 읽기만 함, 2026-09-29 확인).
from scripts.common.youtube_comments import (  # noqa: F401 - research.py 가 이 이름들을 다시 내보낸다
    _append_thread_comments,
    _comment_row,
    classify_comments,
    collect_comments,
)
from scripts.common.youtube_api_common import (
    LATEST_SEARCH,
    ROOT,
    YOUTUBE_SEARCH_URL,
    YOUTUBE_VIDEOS_URL,
    _api_key,
    _get_json,
    _get_json_oauth,
    _now,
    _oauth_token,
    _write_report,
)
from ai_orchestrator.core.security_utils import safe_preview

def search_videos(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    query: str,
    *,
    max_results: int = 5,
    api_key: str | None = None,
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
    captions_only: bool = False,
    order: str = "relevance",
    published_after: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Search public YouTube videos through the official Data API.

    캐시: 동일 쿼리는 24시간 내 결과를 재사용해 API 유닛 소모를 절약한다.
    If no API key is configured, the result is blocked instead of falling back
    to scraping YouTube search pages.

    order: "relevance"(기본) 또는 "date"(최신 등록일순). 정렬을 바꿔도 API
    비용(unit)과 일일 검색 한도는 그대로다.
    published_after: ISO 8601 UTC 문자열(예: "2026-08-01T00:00:00Z"). 이 시각
    이후 등록된 영상만 반환한다.
    """
    key = _api_key(api_key)
    token = _oauth_token(oauth_token, token_file)
    max_results = max(1, min(int(max_results), 10))
    order = order if order in {"relevance", "date"} else "relevance"

    # ── 캐시 조회 (API 유닛 절약) ──────────────────────────────────────────
    # order/published_after 가 다르면 결과가 달라지므로 캐시 키에 포함한다.
    ck = _cache_key(f"{query}|{order}|{published_after or ''}", max_results, captions_only)
    cached = _cache_get(ck)
    if cached:
        cached["cache_hit"] = True
        return cached, _write_report(cached, LATEST_SEARCH, "youtube_research_search")

    if not key and not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_research_search",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_or_oauth_token_required",
            "query": safe_preview(query, limit=120),
            "state_change": False,
            "secret_values_read": False,
            "results": [],
            "next_step": "Set YOUTUBE_API_KEY or provide approved official OAuth credentials.",
            "captions_only": captions_only,
        }
        return payload, _write_report(payload, LATEST_SEARCH, "youtube_research_search")

    search_params: dict[str, str | int] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "safeSearch": "moderate",
        "order": order,
    }
    if key:
        search_params["key"] = key
    if captions_only:
        search_params["videoCaption"] = "closedCaption"
    if published_after:
        search_params["publishedAfter"] = published_after

    search_data = (
        _get_json(YOUTUBE_SEARCH_URL, search_params)
        if key
        else _get_json_oauth(YOUTUBE_SEARCH_URL, search_params, token)
    )
    video_ids = [
        item.get("id", {}).get("videoId", "")
        for item in search_data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    details: dict[str, Any] = {"items": []}
    if video_ids:
        detail_params: dict[str, str | int] = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
        }
        if key:
            detail_params["key"] = key
            details = _get_json(YOUTUBE_VIDEOS_URL, detail_params)
        else:
            details = _get_json_oauth(YOUTUBE_VIDEOS_URL, detail_params, token)

    detail_by_id = {item.get("id"): item for item in details.get("items", [])}
    rows: list[dict[str, Any]] = []
    for item in search_data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        detail = detail_by_id.get(video_id, {})
        caption_hint = detail.get("contentDetails", {}).get("caption", "")
        if captions_only and caption_hint != "true":
            continue
        rows.append(
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": safe_preview(snippet.get("title", ""), limit=180),
                "channel_title": safe_preview(snippet.get("channelTitle", ""), limit=120),
                "published_at": snippet.get("publishedAt", ""),
                "description": safe_preview(snippet.get("description", ""), limit=500),
                "caption_available_hint": caption_hint,
                "script_collection_status": "caption_candidate" if caption_hint == "true" else "metadata_only",
                "script_collection_next_step": (
                    "collect transcript through owner/OAuth captions API or user-provided transcript file"
                    if caption_hint == "true"
                    else "skip for transcript workflow"
                ),
                "duration": detail.get("contentDetails", {}).get("duration", ""),
                "statistics": {
                    "view_count": detail.get("statistics", {}).get("viewCount", ""),
                    "like_count": detail.get("statistics", {}).get("likeCount", ""),
                    "comment_count": detail.get("statistics", {}).get("commentCount", ""),
                },
            }
        )

    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_research_search",
        "ok": True,
        "status": "ok",
        "query": safe_preview(query, limit=120),
        "state_change": False,
        "secret_values_read": False,
        "api_key_output": "redacted",
        "oauth_token_output": "redacted",
        "credential_source": "api_key" if key else "oauth",
        "captions_only": captions_only,
        "order": order,
        "published_after": published_after or "",
        "result_count": len(rows),
        "results": rows,
    }
    return payload, _write_report(payload, LATEST_SEARCH, "youtube_research_search")


def collect_video_info(
    video_id: str,
    *,
    api_key: str | None = None,
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Collect public video metadata through the official YouTube Data API."""
    key = _api_key(api_key)
    token = _oauth_token(oauth_token, token_file)
    video_id = video_id.strip()
    if not key and not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_video_info",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_or_oauth_token_required",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
            "api_key_output": "redacted",
            "oauth_token_output": "redacted",
        }
        return payload, _write_report(payload, ROOT / "data" / "youtube_video_info_latest.json", "youtube_video_info")

    params: dict[str, str | int] = {
        "part": "snippet,contentDetails,statistics",
        "id": video_id,
    }
    if key:
        params["key"] = key
        data = _get_json(YOUTUBE_VIDEOS_URL, params)
    else:
        data = _get_json_oauth(YOUTUBE_VIDEOS_URL, params, token)
    items = data.get("items", [])
    if not items:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_video_info",
            "ok": False,
            "status": "not_found",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
        }
        return payload, _write_report(payload, ROOT / "data" / "youtube_video_info_latest.json", "youtube_video_info")

    item = items[0]
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})
    stats = item.get("statistics", {})
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_video_info",
        "ok": True,
        "status": "ok",
        "video_id": safe_preview(video_id, limit=80),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "state_change": False,
        "secret_values_read": False,
        "api_key_output": "redacted",
        "oauth_token_output": "redacted",
        "credential_source": "api_key" if key else "oauth",
        "video": {
            "title": safe_preview(snippet.get("title", ""), limit=180),
            "channel_title": safe_preview(snippet.get("channelTitle", ""), limit=120),
            "published_at": snippet.get("publishedAt", ""),
            "description": safe_preview(snippet.get("description", ""), limit=800),
            "tags": [safe_preview(tag, limit=80) for tag in snippet.get("tags", [])[:25]],
            "category_id": snippet.get("categoryId", ""),
            "default_language": snippet.get("defaultLanguage", ""),
            "default_audio_language": snippet.get("defaultAudioLanguage", ""),
            "duration": content.get("duration", ""),
            "caption_available_hint": content.get("caption", ""),
            "definition": content.get("definition", ""),
            "licensed_content": content.get("licensedContent", ""),
            "statistics": {
                "view_count": stats.get("viewCount", ""),
                "like_count": stats.get("likeCount", ""),
                "comment_count": stats.get("commentCount", ""),
            },
        },
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_video_info_latest.json", "youtube_video_info")
