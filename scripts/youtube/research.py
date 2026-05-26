"""YouTube search, transcript intake, and analysis workflow.

The module intentionally avoids unofficial transcript scraping. Public video
search and metadata use the official YouTube Data API when an API key is
available. Transcript analysis accepts user-provided text/caption files or
captions obtained through an authorized owner/OAuth flow.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_utils import safe_preview


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "youtube_research_reports"
LATEST_SEARCH = ROOT / "data" / "youtube_research_search_latest.json"
LATEST_TRANSCRIPT_PLAN = ROOT / "data" / "youtube_transcript_plan_latest.json"
LATEST_ANALYSIS = ROOT / "data" / "youtube_transcript_analysis_latest.json"
LATEST_CAPTION_LIST = ROOT / "data" / "youtube_caption_list_latest.json"
LATEST_CAPTION_DOWNLOAD = ROOT / "data" / "youtube_caption_download_latest.json"

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
YOUTUBE_CAPTIONS_URL = "https://www.googleapis.com/youtube/v3/captions"
CAPTION_DOWNLOAD_FORMATS = {"srt", "vtt", "ttml"}
TRANSCRIPT_SOURCE_POLICY = {
    "allowed": [
        "user_provided_transcript_file",
        "owned_channel_caption_file_obtained_with_oauth",
        "manually_exported_caption_file",
    ],
    "blocked": [
        "unofficial_caption_scraping",
        "browser_hidden_caption_endpoint_scraping",
        "third_party_transcript_api_without_user_approval",
    ],
}
SENSITIVE_WORDS = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|cookie|credential|otp|password|refresh[_-]?token|secret|session[_-]?id|token)"
)
WORD_RE = re.compile(r"[A-Za-z가-힣0-9][A-Za-z가-힣0-9_+-]{1,}")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "you",
    "are",
    "from",
    "have",
    "will",
    "your",
    "영상",
    "그리고",
    "그러면",
    "합니다",
    "있는",
    "이번",
    "오늘",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_report(payload: dict[str, Any], latest: Path, prefix: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{prefix}_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return path


def _api_key(explicit: str | None = None) -> str:
    return explicit or os.environ.get("YOUTUBE_API_KEY", "") or os.environ.get("GOOGLE_YOUTUBE_API_KEY", "")


def _resolve_repo_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved


def _oauth_token(explicit: str | None = None, token_file: str | Path | None = None) -> str:
    if explicit:
        return explicit
    env_token = os.environ.get("YOUTUBE_OAUTH_ACCESS_TOKEN") or os.environ.get("GOOGLE_YOUTUBE_OAUTH_ACCESS_TOKEN")
    if env_token:
        return env_token
    if not token_file:
        return ""
    path = _resolve_repo_path(token_file)
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        refreshed = _refresh_oauth_token(parsed)
        if refreshed:
            return refreshed
        return str(parsed.get("access_token") or parsed.get("token") or "")
    return raw


def _refresh_oauth_token(parsed: dict[str, Any]) -> str:
    refresh_token = str(parsed.get("refresh_token") or "")
    client_id = str(parsed.get("client_id") or "")
    client_secret = str(parsed.get("client_secret") or "")
    token_uri = str(parsed.get("token_uri") or "https://oauth2.googleapis.com/token")
    if not refresh_token or not client_id or not client_secret:
        return ""
    encoded = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(token_uri, data=encoded, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""
    return str(payload.get("access_token") or "")


def parse_kv_args(args: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    positional: list[str] = []
    for item in args:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key.strip().lstrip("-")] = value.strip()
        elif item.startswith("--"):
            values[item[2:]] = "1"
        else:
            positional.append(item)
    if positional and "query" not in values:
        values["query"] = " ".join(positional)
    return values


def _get_json(url: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json_oauth(url: str, params: dict[str, str | int], token: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_text_oauth(url: str, params: dict[str, str | int], token: str) -> str:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"Accept": "text/plain,text/vtt,application/x-subrip,*/*", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


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


def collect_video_info(video_id: str, *, api_key: str | None = None) -> tuple[dict[str, Any], Path]:
    """Collect public video metadata through the official YouTube Data API."""
    key = _api_key(api_key)
    video_id = video_id.strip()
    if not key:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_video_info",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_required",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
        }
        return payload, _write_report(payload, ROOT / "data" / "youtube_video_info_latest.json", "youtube_video_info")

    data = _get_json(
        YOUTUBE_VIDEOS_URL,
        {
            "key": key,
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
        },
    )
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
    order: str = "relevance",
    api_key: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Collect public top-level comments through the official API."""
    key = _api_key(api_key)
    video_id = video_id.strip()
    max_results = max(1, min(int(max_results), 100))
    if not key:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_comment_collection",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_required",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
            "comments": [],
        }
        return payload, _write_report(payload, ROOT / "data" / "youtube_comments_latest.json", "youtube_comments")

    try:
        data = _get_json(
            YOUTUBE_COMMENT_THREADS_URL,
            {
                "key": key,
                "part": "snippet",
                "videoId": video_id,
                "maxResults": max_results,
                "order": order if order in {"time", "relevance"} else "relevance",
                "textFormat": "plainText",
            },
        )
        status = "ok"
        reason = ""
    except Exception as exc:
        data = {"items": []}
        status = "blocked_or_unavailable"
        reason = type(exc).__name__ + ": " + str(exc)[:180]

    comments: list[dict[str, Any]] = []
    for item in data.get("items", []):
        top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        comments.append(
            {
                "comment_id": safe_preview(item.get("id", ""), limit=120),
                "author_display_name": safe_preview(top.get("authorDisplayName", ""), limit=80),
                "published_at": top.get("publishedAt", ""),
                "updated_at": top.get("updatedAt", ""),
                "like_count": top.get("likeCount", 0),
                "text": safe_preview(SENSITIVE_WORDS.sub("[redacted-sensitive]", top.get("textDisplay", "")), limit=1000),
            }
        )

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
        "comment_count": len(comments),
        "comments": comments,
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_comments_latest.json", "youtube_comments")


def analyze_video_context(
    *,
    video_info: dict[str, Any] | None = None,
    comments: dict[str, Any] | None = None,
    transcript_text: str = "",
) -> tuple[dict[str, Any], Path]:
    """Analyze collected video metadata, comments, and optional transcript text."""
    video_info = video_info or {}
    comments = comments or {}
    video = video_info.get("video", {}) if isinstance(video_info.get("video"), dict) else {}
    comment_rows = comments.get("comments", []) if isinstance(comments.get("comments"), list) else []
    comment_text = "\n".join(str(row.get("text", "")) for row in comment_rows)
    combined = "\n".join(
        part
        for part in (
            str(video.get("title", "")),
            str(video.get("description", "")),
            comment_text,
            transcript_text,
        )
        if part
    )
    combined = SENSITIVE_WORDS.sub("[redacted-sensitive]", combined)
    keywords = _top_keywords(combined)
    comment_likes = sorted(comment_rows, key=lambda row: int(row.get("like_count") or 0), reverse=True)[:5]
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_video_context_analysis",
        "ok": True,
        "status": "ok",
        "state_change": False,
        "source_counts": {
            "has_video_info": bool(video),
            "comments": len(comment_rows),
            "has_transcript": bool(transcript_text.strip()),
        },
        "video_summary": {
            "title": safe_preview(video.get("title", ""), limit=180),
            "channel_title": safe_preview(video.get("channel_title", ""), limit=120),
            "published_at": video.get("published_at", ""),
            "caption_available_hint": video.get("caption_available_hint", ""),
            "statistics": video.get("statistics", {}),
        },
        "top_keywords": keywords,
        "comment_insights": {
            "top_liked_comments": [
                {
                    "author_display_name": row.get("author_display_name", ""),
                    "like_count": row.get("like_count", 0),
                    "text": safe_preview(row.get("text", ""), limit=260),
                }
                for row in comment_likes
            ],
            "common_topics": [row["keyword"] for row in keywords[:8]],
        },
        "report": {
            "what_to_watch": [
                "Check high-frequency topics against the transcript before creating our own video.",
                "Use top liked comments as audience pain-point signals.",
                "Compare title/description keywords with search query intent.",
            ],
            "approval_boundaries": [
                "Do not post comments, like, subscribe, upload, or publish without final approval.",
                "Do not copy transcript/comment text into a public asset without rights review.",
            ],
        },
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_video_context_analysis_latest.json", "youtube_video_context_analysis")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bounded(value: float, *, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def build_video_strategy_scorecard(
    *,
    video_info: dict[str, Any] | None = None,
    comments: dict[str, Any] | None = None,
    transcript_text: str = "",
    channel_topic: str = "",
) -> tuple[dict[str, Any], Path]:
    """Score a reference video for our production and management planning."""
    video_info = video_info or {}
    comments = comments or {}
    video = video_info.get("video", {}) if isinstance(video_info.get("video"), dict) else {}
    stats = video.get("statistics", {}) if isinstance(video.get("statistics"), dict) else {}
    comment_rows = comments.get("comments", []) if isinstance(comments.get("comments"), list) else []
    text_parts = [
        str(video.get("title", "")),
        str(video.get("description", "")),
        "\n".join(str(row.get("text", "")) for row in comment_rows),
        transcript_text,
    ]
    combined = SENSITIVE_WORDS.sub("[redacted-sensitive]", "\n".join(part for part in text_parts if part))
    keywords = _top_keywords(combined, limit=15)
    keyword_set = {row["keyword"].lower() for row in keywords}
    topic_words = {word.lower() for word in WORD_RE.findall(channel_topic) if len(word) > 1}

    views = _int(stats.get("view_count"))
    likes = _int(stats.get("like_count"))
    comment_count_stat = _int(stats.get("comment_count"))
    comment_count = max(len(comment_rows), comment_count_stat)
    title_len = len(str(video.get("title", "")))
    transcript_words = len(WORD_RE.findall(transcript_text))
    question_comments = sum(1 for row in comment_rows if "?" in str(row.get("text", "")) or "어떻게" in str(row.get("text", "")))

    demand_score = _bounded(min(60, views ** 0.5 / 20) + min(25, comment_count * 2) + min(15, likes ** 0.5 / 10))
    comment_pain_score = _bounded((question_comments / max(1, len(comment_rows))) * 70 + min(30, comment_count * 1.5))
    topic_fit_score = 50
    if topic_words:
        overlap = len(topic_words & keyword_set)
        topic_fit_score = _bounded(35 + overlap * 20)
    script_quality_score = _bounded(35 + min(35, transcript_words / 60) + (20 if video.get("caption_available_hint") == "true" else 0))
    hook_score = _bounded(70 if 20 <= title_len <= 80 else 45)
    competition_score = _bounded(80 - min(55, views ** 0.5 / 15))
    production_effort_score = _bounded(80 - min(50, transcript_words / 120))
    monetization_score = _bounded((topic_fit_score * 0.35) + (demand_score * 0.35) + (comment_pain_score * 0.3))
    opportunity_score = _bounded(
        demand_score * 0.24
        + topic_fit_score * 0.18
        + comment_pain_score * 0.18
        + script_quality_score * 0.14
        + hook_score * 0.1
        + competition_score * 0.08
        + production_effort_score * 0.08
    )
    management_score = _bounded(
        min(35, len(comment_rows) * 4)
        + min(35, question_comments * 8)
        + (20 if comments.get("status") == "ok" else 0)
        + (10 if video.get("caption_available_hint") == "true" else 0)
    )

    recommended_actions: list[str] = []
    if opportunity_score >= 70:
        recommended_actions.append("produce_video")
    elif opportunity_score >= 50:
        recommended_actions.append("prepare_script_outline")
    else:
        recommended_actions.append("monitor_only")
    if comment_pain_score >= 60:
        recommended_actions.append("answer_unresolved_comment_questions")
    if hook_score < 60:
        recommended_actions.append("rewrite_title_hook")
    if script_quality_score >= 65:
        recommended_actions.append("use_transcript_structure_as_reference")

    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_video_strategy_scorecard",
        "ok": True,
        "status": "ok",
        "state_change": False,
        "channel_topic": safe_preview(channel_topic, limit=160),
        "video": {
            "title": safe_preview(video.get("title", ""), limit=180),
            "channel_title": safe_preview(video.get("channel_title", ""), limit=120),
            "caption_available_hint": video.get("caption_available_hint", ""),
            "statistics": stats,
        },
        "signals": {
            "views": views,
            "likes": likes,
            "comments": comment_count,
            "collected_comments": len(comment_rows),
            "question_comments": question_comments,
            "transcript_word_like_count": transcript_words,
            "top_keywords": keywords,
        },
        "scores": {
            "topic_fit_score": topic_fit_score,
            "demand_score": demand_score,
            "script_quality_score": script_quality_score,
            "hook_score": hook_score,
            "comment_pain_score": comment_pain_score,
            "competition_score": competition_score,
            "production_effort_score": production_effort_score,
            "monetization_score": monetization_score,
            "my_video_opportunity_score": opportunity_score,
            "my_video_management_score": management_score,
        },
        "recommended_actions": recommended_actions,
        "approval_boundaries": [
            "Competitor/reference video analysis is read-only.",
            "Publishing, uploading, commenting, replying, liking, subscribing, hiding, deleting, or pinning requires final approval.",
        ],
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_video_strategy_scorecard_latest.json", "youtube_video_strategy_scorecard")


COMMENT_ACTION_POLICY = {
    "prepare": {
        "state_change": False,
        "approval_required": False,
        "allowed": True,
    },
    "post": {
        "state_change": True,
        "approval_required": True,
        "approval_boundary": "final_post_comment_button",
        "allowed_without_approval": False,
    },
    "reply": {
        "state_change": True,
        "approval_required": True,
        "approval_boundary": "final_reply_button",
        "allowed_without_approval": False,
    },
    "moderate": {
        "state_change": True,
        "approval_required": True,
        "approval_boundary": "hide_report_delete_or_pin_button",
        "allowed_without_approval": False,
    },
}


def prepare_comment_plan(
    *,
    video_id: str,
    text: str,
    parent_comment_id: str = "",
    action: str = "comment",
) -> tuple[dict[str, Any], Path]:
    """Prepare a YouTube comment/reply plan without posting it."""
    action = action if action in {"comment", "reply"} else "comment"
    clean_text = SENSITIVE_WORDS.sub("[redacted-sensitive]", text).strip()
    missing: list[str] = []
    if not video_id.strip():
        missing.append("video_id")
    if not clean_text:
        missing.append("comment_text")
    if action == "reply" and not parent_comment_id.strip():
        missing.append("parent_comment_id")
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_comment_prepare",
        "ok": not missing,
        "status": "ready_for_approval" if not missing else "blocked",
        "action": action,
        "video_id": safe_preview(video_id, limit=80),
        "parent_comment_id": safe_preview(parent_comment_id, limit=120),
        "comment_text": safe_preview(clean_text, limit=1000),
        "comment_length": len(clean_text),
        "missing_requirements": missing,
        "state_change": False,
        "approval": {
            "required_for_execution": True,
            "approval_boundary": "final_comment_or_reply_button",
            "confirm_phrase": "YOUTUBE_APPROVED_COMMENT",
        },
        "execution": {
            "post_executed": False,
            "reply_executed": False,
            "api_call_allowed_now": False,
        },
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_comment_plan_latest.json", "youtube_comment_plan")


def build_channel_ops_plan(*, workflow: str, video_id: str = "", comment_id: str = "") -> tuple[dict[str, Any], Path]:
    """Describe owner-channel operations and their approval boundaries."""
    state_changing = workflow in {"upload", "publish", "comment_post", "comment_reply", "hide_comment", "delete_comment", "pin_comment"}
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_channel_ops_plan",
        "operation": workflow,
        "video_id": safe_preview(video_id, limit=80),
        "comment_id": safe_preview(comment_id, limit=120),
        "state_change": False,
        "would_change_state_if_executed": state_changing,
        "owner_oauth_required": state_changing,
        "approval_required": state_changing,
        "approval_boundary": "final_confirm_button" if state_changing else "read_only",
        "allowed_now": not state_changing,
        "note": "This plan does not execute YouTube mutations. Final execution requires owner OAuth and explicit approval.",
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_channel_ops_plan_latest.json", "youtube_channel_ops_plan")


def build_transcript_collection_plan(video_id: str, *, owned: bool = False) -> tuple[dict[str, Any], Path]:
    """Create a compliant transcript collection plan for a specific video."""
    video_id = video_id.strip()
    allowed_sources = list(TRANSCRIPT_SOURCE_POLICY["allowed"])
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_transcript_collection_plan",
        "ok": bool(video_id),
        "status": "ready" if video_id else "blocked",
        "video_id": safe_preview(video_id, limit=80),
        "video_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "state_change": False,
        "policy": TRANSCRIPT_SOURCE_POLICY,
        "owned_or_authorized_video": owned,
        "allowed_next_steps": allowed_sources,
        "blocked_next_steps": list(TRANSCRIPT_SOURCE_POLICY["blocked"]),
        "note": (
            "The official YouTube Data API can search videos and inspect metadata. "
            "Caption download requires ownership/OAuth permission or a user-provided transcript file."
        ),
    }
    return payload, _write_report(payload, LATEST_TRANSCRIPT_PLAN, "youtube_transcript_plan")


def list_captions(
    video_id: str,
    *,
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """List authorized caption tracks through the official YouTube Data API."""
    video_id = video_id.strip()
    token = _oauth_token(oauth_token, token_file)
    if not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_list",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_oauth_token_required",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Provide an approved owner/authorized OAuth access token or a user-provided transcript file.",
            "captions": [],
        }
        return payload, _write_report(payload, LATEST_CAPTION_LIST, "youtube_caption_list")

    data = _get_json_oauth(
        YOUTUBE_CAPTIONS_URL,
        {"part": "snippet", "videoId": video_id},
        token,
    )
    captions: list[dict[str, Any]] = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        captions.append(
            {
                "caption_id": safe_preview(item.get("id", ""), limit=120),
                "video_id": safe_preview(snippet.get("videoId", video_id), limit=80),
                "language": safe_preview(snippet.get("language", ""), limit=40),
                "name": safe_preview(snippet.get("name", ""), limit=120),
                "track_kind": safe_preview(snippet.get("trackKind", ""), limit=80),
                "audio_track_type": safe_preview(snippet.get("audioTrackType", ""), limit=80),
                "status": safe_preview(snippet.get("status", ""), limit=80),
                "is_draft": bool(snippet.get("isDraft", False)),
                "last_updated": safe_preview(snippet.get("lastUpdated", ""), limit=80),
            }
        )
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_caption_list",
        "ok": True,
        "status": "ok",
        "video_id": safe_preview(video_id, limit=80),
        "state_change": False,
        "secret_values_read": False,
        "oauth_token_output": "redacted",
        "source_policy": "official_youtube_captions_api_authorized_only",
        "caption_count": len(captions),
        "captions": captions,
    }
    return payload, _write_report(payload, LATEST_CAPTION_LIST, "youtube_caption_list")


def download_caption(
    caption_id: str,
    *,
    tfmt: str = "srt",
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
    output: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Download an authorized caption track through the official YouTube Data API."""
    caption_id = caption_id.strip()
    tfmt = (tfmt or "srt").strip().lower()
    if tfmt not in CAPTION_DOWNLOAD_FORMATS:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_download",
            "ok": False,
            "status": "blocked",
            "reason": "unsupported_caption_format",
            "caption_id": safe_preview(caption_id, limit=120),
            "requested_format": safe_preview(tfmt, limit=20),
            "allowed_formats": sorted(CAPTION_DOWNLOAD_FORMATS),
            "state_change": False,
            "secret_values_read": False,
        }
        return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")

    token = _oauth_token(oauth_token, token_file)
    if not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_download",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_oauth_token_required",
            "caption_id": safe_preview(caption_id, limit=120),
            "requested_format": tfmt,
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Provide an approved owner/authorized OAuth access token or a user-provided transcript file.",
        }
        return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")

    try:
        text = _get_text_oauth(f"{YOUTUBE_CAPTIONS_URL}/{urllib.parse.quote(caption_id)}", {"tfmt": tfmt}, token)
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_download",
            "ok": False,
            "status": "blocked",
            "reason": "official_caption_download_forbidden_or_unavailable",
            "error_type": type(exc).__name__,
            "error_summary": safe_preview(str(exc), limit=200),
            "caption_id": safe_preview(caption_id, limit=120),
            "requested_format": tfmt,
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Use an owned/authorized video with downloadable captions, or provide a user-exported transcript file.",
        }
        return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")
    sanitized = SENSITIVE_WORDS.sub("[redacted-sensitive]", text)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    transcript_path = _resolve_repo_path(output) if output else REPORT_DIR / f"youtube_caption_download_{_stamp()}.{tfmt}"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(sanitized, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_caption_download",
        "ok": True,
        "status": "ok",
        "caption_id": safe_preview(caption_id, limit=120),
        "requested_format": tfmt,
        "state_change": False,
        "secret_values_read": False,
        "oauth_token_output": "redacted",
        "source_policy": "official_youtube_captions_api_authorized_only",
        "transcript_path": str(transcript_path),
        "character_count": len(sanitized),
        "word_like_count": len(WORD_RE.findall(sanitized)),
    }
    return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")


def _read_transcript(path: str | Path) -> str:
    transcript_path = _resolve_repo_path(path)
    text = transcript_path.read_text(encoding="utf-8", errors="replace")
    return SENSITIVE_WORDS.sub("[redacted-sensitive]", text)


def _sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 20]


def _top_keywords(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    words = [word for word in words if word not in STOPWORDS and len(word) > 1]
    return [{"keyword": word, "count": count} for word, count in Counter(words).most_common(limit)]


def analyze_transcript(transcript_file: str | Path, *, video_id: str = "", title: str = "") -> tuple[dict[str, Any], Path]:
    """Analyze a user-provided transcript/caption file without external AI calls."""
    text = _read_transcript(transcript_file)
    sentences = _sentences(text)
    keyword_rows = _top_keywords(text)
    highlights = sentences[:8]
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_transcript_analysis",
        "ok": True,
        "status": "ok",
        "video_id": safe_preview(video_id, limit=80),
        "title": safe_preview(title, limit=180),
        "state_change": False,
        "source_policy": "user_provided_or_authorized_transcript_only",
        "transcript_stats": {
            "characters": len(text),
            "word_like_count": len(WORD_RE.findall(text)),
            "sentence_count": len(sentences),
        },
        "top_keywords": keyword_rows,
        "summary": {
            "method": "extractive_local_analysis",
            "highlights": [safe_preview(sentence, limit=260) for sentence in highlights],
        },
        "business_report": {
            "main_topics": [row["keyword"] for row in keyword_rows[:6]],
            "content_reuse_ideas": [
                "Turn the strongest highlights into a short briefing.",
                "Extract repeated keywords into a follow-up search plan.",
                "Compare this transcript with competitor videos before creating upload metadata.",
            ],
            "risk_notes": [
                "Transcript quality depends on the source caption quality.",
                "Do not publish copied transcript text without rights review.",
            ],
        },
    }
    return payload, _write_report(payload, LATEST_ANALYSIS, "youtube_transcript_analysis")
