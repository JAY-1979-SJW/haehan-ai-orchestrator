"""YouTube video search and comment collection."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from security_utils import safe_preview
from scripts.youtube.research_common import (
    _now,
    _write_report,
    _api_key,
    _oauth_token,
    _get_json,
    _get_json_oauth,
    _int_value,
    _top_keywords,
    SENSITIVE_WORDS,
    ROOT,
    LATEST_SEARCH,
    YOUTUBE_SEARCH_URL,
    YOUTUBE_VIDEOS_URL,
    YOUTUBE_COMMENT_THREADS_URL,
)


COMMENT_CLASS_RULES: dict[str, tuple[str, ...]] = {
    "question": ("?", "how", "what", "why", "where", "when", "어떻게", "뭐", "왜", "질문", "궁금"),
    "positive_feedback": ("great", "good", "thanks", "helpful", "useful", "감사", "좋", "도움", "유익"),
    "negative_feedback": ("bad", "wrong", "problem", "error", "hate", "아쉽", "문제", "오류", "불편", "별로"),
    "request": ("please", "can you", "make", "show", "해주", "만들", "보여", "요청"),
    "price_business": ("price", "cost", "money", "profit", "가격", "비용", "수익", "매출", "돈"),
    "implementation": ("setup", "install", "tool", "code", "api", "설정", "설치", "도구", "코드", "자동화"),
}


def search_videos(
    query: str,
    *,
    max_results: int = 5,
    api_key: str | None = None,
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
    captions_only: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Search public YouTube videos through the official Data API.

    If no API key is configured, the result is blocked instead of falling back
    to scraping YouTube search pages.
    """
    key = _api_key(api_key)
    token = _oauth_token(oauth_token, token_file)
    max_results = max(1, min(int(max_results), 10))
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
    }
    if key:
        search_params["key"] = key
    if captions_only:
        search_params["videoCaption"] = "closedCaption"

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


def collect_comments(
    video_id: str,
    *,
    max_results: int = 20,
    max_pages: int = 1,
    max_comments_total: int = 100,
    include_replies: bool = False,
    order: str = "relevance",
    api_key: str | None = None,
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Collect public top-level comments through the official API."""
    key = _api_key(api_key)
    token = _oauth_token(oauth_token, token_file)
    video_id = video_id.strip()
    max_results = max(1, min(int(max_results), 100))
    max_pages = max(1, min(int(max_pages), 50))
    max_comments_total = max(1, min(int(max_comments_total), 5000))
    if not key and not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_comment_collection",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_or_oauth_token_required",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
            "api_key_output": "redacted",
            "oauth_token_output": "redacted",
            "comments": [],
        }
        return payload, _write_report(payload, ROOT / "data" / "youtube_comments_latest.json", "youtube_comments")

    comments: list[dict[str, Any]] = []
    pages_fetched = 0
    next_page_token = ""
    status = "ok"
    reason = ""
    try:
        while pages_fetched < max_pages and len(comments) < max_comments_total:
            params: dict[str, str | int] = {
                "part": "snippet,replies" if include_replies else "snippet",
                "videoId": video_id,
                "maxResults": min(max_results, max_comments_total - len(comments)),
                "order": order if order in {"time", "relevance"} else "relevance",
                "textFormat": "plainText",
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            if key:
                params["key"] = key
                data = _get_json(YOUTUBE_COMMENT_THREADS_URL, params)
            else:
                data = _get_json_oauth(YOUTUBE_COMMENT_THREADS_URL, params, token)
            pages_fetched += 1
            for item in data.get("items", []):
                top_comment = item.get("snippet", {}).get("topLevelComment", {})
                top = top_comment.get("snippet", {})
                comments.append(
                    _comment_row(
                        comment_id=str(top_comment.get("id") or item.get("id") or ""),
                        snippet=top,
                        parent_id="",
                        kind="top_level",
                    )
                )
                if len(comments) >= max_comments_total:
                    break
                if include_replies:
                    for reply in item.get("replies", {}).get("comments", []):
                        reply_snippet = reply.get("snippet", {})
                        comments.append(
                            _comment_row(
                                comment_id=str(reply.get("id") or ""),
                                snippet=reply_snippet,
                                parent_id=str(item.get("id") or ""),
                                kind="reply",
                            )
                        )
                        if len(comments) >= max_comments_total:
                            break
                if len(comments) >= max_comments_total:
                    break
            next_page_token = str(data.get("nextPageToken") or "")
            if not next_page_token:
                break
    except Exception as exc:
        if not comments:
            status = "blocked_or_unavailable"
        else:
            status = "partial"
        reason = type(exc).__name__ + ": " + str(exc)[:180]
    classification = classify_comments(comments)

    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_comment_collection",
        "ok": status == "ok",
        "status": status,
        "reason": reason,
        "video_id": safe_preview(video_id, limit=80),
        "state_change": False,
        "secret_values_read": False,
        "api_key_output": "redacted",
        "oauth_token_output": "redacted",
        "credential_source": "api_key" if key else "oauth",
        "collection_scope": "bounded_full_public_comment_threads",
        "pages_fetched": pages_fetched,
        "next_page_token_present": bool(next_page_token),
        "max_pages": max_pages,
        "max_comments_total": max_comments_total,
        "include_replies": include_replies,
        "comment_count": len(comments),
        "classification": classification,
        "comments": comments,
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_comments_latest.json", "youtube_comments")


def _comment_row(*, comment_id: str, snippet: dict[str, Any], parent_id: str, kind: str) -> dict[str, Any]:
    return {
        "comment_id": safe_preview(comment_id, limit=120),
        "parent_id": safe_preview(parent_id, limit=120),
        "kind": kind,
        "author_display_name": safe_preview(snippet.get("authorDisplayName", ""), limit=80),
        "published_at": snippet.get("publishedAt", ""),
        "updated_at": snippet.get("updatedAt", ""),
        "like_count": snippet.get("likeCount", 0),
        "text": safe_preview(SENSITIVE_WORDS.sub("[redacted-sensitive]", snippet.get("textDisplay", "")), limit=1000),
    }


def classify_comments(comments: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify collected comments into simple market-research buckets."""
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in COMMENT_CLASS_RULES}
    buckets["uncategorized"] = []
    keyword_text = []
    for row in comments:
        text = str(row.get("text", ""))
        lower = text.lower()
        matched = False
        for label, terms in COMMENT_CLASS_RULES.items():
            if any(term.lower() in lower for term in terms):
                buckets[label].append(row)
                matched = True
        if not matched:
            buckets["uncategorized"].append(row)
        keyword_text.append(text)
    bucket_counts = {key: len(value) for key, value in buckets.items() if value}
    top_samples = {}
    for key, rows in buckets.items():
        if not rows:
            continue
        sorted_rows = sorted(rows, key=lambda item: _int_value(item.get("like_count")), reverse=True)
        top_samples[key] = [
            {
                "like_count": _int_value(row.get("like_count")),
                "text_preview": safe_preview(row.get("text", ""), limit=180),
            }
            for row in sorted_rows[:3]
        ]
    return {
        "comment_count": len(comments),
        "bucket_counts": bucket_counts,
        "top_keywords": _top_keywords(" ".join(keyword_text), limit=20),
        "top_samples": top_samples,
    }
