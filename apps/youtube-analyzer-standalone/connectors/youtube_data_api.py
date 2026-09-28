"""YouTube Data API v3 얇은 래퍼. search.list + videos.list(statistics/contentDetails) 조합."""

from __future__ import annotations

import html
import os
from typing import Any

from googleapiclient.discovery import build

_API_SERVICE_NAME = "youtube"
_API_VERSION = "v3"


def _get_client():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY 가 설정되지 않았습니다 (.env 확인)")
    return build(_API_SERVICE_NAME, _API_VERSION, developerKey=api_key)


def search_videos(
    query: str,
    max_results: int = 25,
    published_after: str | None = None,
    order: str = "viewCount",
) -> list[dict[str, Any]]:
    """키워드로 영상 검색 후 videoId 목록 반환 (통계 정보 없음)."""
    youtube = _get_client()
    params: dict[str, Any] = {
        "q": query,
        "part": "id,snippet",
        "type": "video",
        "maxResults": min(max_results, 50),
        "order": order,
    }
    if published_after:
        params["publishedAfter"] = published_after

    response = youtube.search().list(**params).execute()
    return [
        {
            "video_id": item["id"]["videoId"],
            "title": html.unescape(item["snippet"]["title"]),
            "channel_title": html.unescape(item["snippet"]["channelTitle"]),
            "published_at": item["snippet"]["publishedAt"],
            "description": html.unescape(item["snippet"].get("description", "")),
        }
        for item in response.get("items", [])
    ]


def get_video_snippet(video_id: str) -> dict[str, Any] | None:
    """단일 video_id 의 snippet(published_at 등) 조회. 리포트에서 통계 재조합용."""
    youtube = _get_client()
    response = youtube.videos().list(part="snippet", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        return None
    snippet = items[0]["snippet"]
    return {"published_at": snippet["publishedAt"], "title": html.unescape(snippet["title"])}


def get_video_statistics(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    """videoId 리스트 → {video_id: {view_count, like_count, comment_count, duration}}."""
    if not video_ids:
        return {}
    youtube = _get_client()
    result: dict[str, dict[str, Any]] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        response = youtube.videos().list(part="statistics,contentDetails", id=",".join(chunk)).execute()
        for item in response.get("items", []):
            stats = item.get("statistics", {})
            result[item["id"]] = {
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration": item.get("contentDetails", {}).get("duration", ""),
            }
    return result
