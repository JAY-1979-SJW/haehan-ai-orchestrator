"""경쟁 채널 분석 — 신규 채널 기획을 위해 기존 채널의 성공 패턴을 파악한다.

목적: 신규 채널(구독자 적음)이 "획기적인 영상"을 기획하려면, 이미 자리잡은
채널들이 어떤 제목·형식·조회수 패턴으로 반응을 얻는지 알아야 한다. 채널
ID로 업로드 영상 전체(또는 최근 N개)를 조회수순으로 뽑아 공통 패턴을 뽑는다.

공식 YouTube Data API만 사용(channels.list, search.list). 조회 전용.

사용:
    from scripts.youtube.channel_analysis import analyze_channels
    result, path = analyze_channels(["UCxxxx", "@handle"], videos_per_channel=15)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.youtube.research_common import (
    ROOT,
    _api_key,
    _get_json,
    _int_value,
    _now,
    _top_keywords,
    _write_report,
)
from security_utils import safe_preview

YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
LATEST_CHANNEL_ANALYSIS = ROOT / "data" / "youtube_channel_analysis_latest.json"

# 조회수를 끌어올리는 데 자주 쓰이는 제목 후킹 표현(국내 유튜브 관행 기준).
HOOK_PATTERNS = {
    "충격/경고형": ["큰일", "충격", "경고", "위험", "망함", "끝났", "죽었", "위기"],
    "결과공개형": ["해봤더니", "써봤더니", "따라했더니", "결과", "후기"],
    "쉬움강조형": ["초보", "쉽게", "10분", "5분", "이거 하나로", "이것만"],
    "권위/전문형": ["1%", "전문가", "실전", "완벽", "제대로"],
    "질문/공감형": ["아직도", "왜", "몰랐다면", "안쓰시나요"],
    "숫자강조형": ["단계", "가지", "배", "%"],
}


def _resolve_channel_id(page_or_none: Any, handle_or_id: str, key: str) -> str:
    """@handle 또는 채널명을 channelId 로 변환. 이미 UC로 시작하면 그대로 반환."""
    value = handle_or_id.strip()
    if value.startswith("UC") and len(value) == 24:
        return value
    params: dict[str, str | int] = {"part": "id"}
    if value.startswith("@"):
        params["forHandle"] = value
    else:
        params["forHandle"] = f"@{value}"
    if key:
        params["key"] = key
    try:
        data = _get_json(YOUTUBE_CHANNELS_URL, params)
        items = data.get("items", [])
        if items:
            return items[0]["id"]
    except Exception:
        pass
    # 핸들 조회 실패 시 검색으로 폴백
    search_params: dict[str, str | int] = {"part": "snippet", "q": value, "type": "channel", "maxResults": 1}
    if key:
        search_params["key"] = key
    try:
        data = _get_json(YOUTUBE_SEARCH_URL, search_params)
        items = data.get("items", [])
        if items:
            return items[0]["id"]["channelId"]
    except Exception:
        pass
    return ""


def _fetch_channel_meta(channel_id: str, key: str) -> dict[str, Any]:
    params: dict[str, str | int] = {"part": "snippet,statistics", "id": channel_id}
    if key:
        params["key"] = key
    data = _get_json(YOUTUBE_CHANNELS_URL, params)
    items = data.get("items", [])
    if not items:
        return {}
    item = items[0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    return {
        "channel_id": channel_id,
        "title": safe_preview(snippet.get("title", ""), limit=80),
        "subscriber_count": _int_value(stats.get("subscriberCount")),
        "video_count": _int_value(stats.get("videoCount")),
        "view_count_total": _int_value(stats.get("viewCount")),
    }


def _fetch_channel_top_videos(channel_id: str, key: str, *, max_results: int) -> list[dict[str, Any]]:
    """채널의 영상을 조회수순으로 최대 max_results개 조회."""
    params: dict[str, str | int] = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "viewCount",
        "maxResults": max(1, min(max_results, 50)),
    }
    if key:
        params["key"] = key
    search_data = _get_json(YOUTUBE_SEARCH_URL, params)
    video_ids = [
        item.get("id", {}).get("videoId", "")
        for item in search_data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    if not video_ids:
        return []

    from scripts.youtube.research_common import YOUTUBE_VIDEOS_URL

    detail_params: dict[str, str | int] = {"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids)}
    if key:
        detail_params["key"] = key
    detail_data = _get_json(YOUTUBE_VIDEOS_URL, detail_params)

    videos = []
    for item in detail_data.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        title = safe_preview(snippet.get("title", ""), limit=200)
        matched_hooks = [label for label, words in HOOK_PATTERNS.items() if any(w in title for w in words)]
        videos.append(
            {
                "video_id": item.get("id", ""),
                "url": f"https://www.youtube.com/watch?v={item.get('id', '')}",
                "title": title,
                "published_at": snippet.get("publishedAt", ""),
                "view_count": _int_value(stats.get("viewCount")),
                "like_count": _int_value(stats.get("likeCount")),
                "comment_count": _int_value(stats.get("commentCount")),
                "duration": item.get("contentDetails", {}).get("duration", ""),
                "hook_patterns": matched_hooks,
            }
        )
    videos.sort(key=lambda v: v["view_count"], reverse=True)
    return videos


def analyze_channels(
    channels: list[str],
    *,
    videos_per_channel: int = 15,
    api_key: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """채널 목록(채널ID/@핸들/채널명 혼용 가능) → 채널별 상위 영상 + 공통 패턴 분석."""
    key = _api_key(api_key)
    if not key:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_channel_analysis",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_required",
            "channels": [],
        }
        path = _write_report(payload, LATEST_CHANNEL_ANALYSIS, "youtube_channel_analysis")
        return payload, path

    channel_reports: list[dict[str, Any]] = []
    all_hook_counts: dict[str, int] = {}
    all_titles: list[str] = []

    for raw in channels:
        channel_id = _resolve_channel_id(None, raw, key)
        if not channel_id:
            channel_reports.append({"input": raw, "ok": False, "reason": "channel_not_found"})
            continue
        meta = _fetch_channel_meta(channel_id, key)
        videos = _fetch_channel_top_videos(channel_id, key, max_results=videos_per_channel)
        for v in videos:
            all_titles.append(v["title"])
            for hook in v["hook_patterns"]:
                all_hook_counts[hook] = all_hook_counts.get(hook, 0) + 1
        avg_views = round(sum(v["view_count"] for v in videos) / len(videos), 0) if videos else 0
        channel_reports.append(
            {
                "input": raw,
                "ok": True,
                **meta,
                "top_videos": videos,
                "avg_view_count_of_sample": avg_views,
            }
        )

    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_channel_analysis",
        "ok": True,
        "status": "ok",
        "state_change": False,
        "channel_count": len(channels),
        "channels": channel_reports,
        "cross_channel_hook_pattern_counts": dict(sorted(all_hook_counts.items(), key=lambda x: -x[1])),
        "cross_channel_top_keywords": _top_keywords(" ".join(all_titles), limit=20),
    }
    path = _write_report(payload, LATEST_CHANNEL_ANALYSIS, "youtube_channel_analysis")
    return payload, path
