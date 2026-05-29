"""YouTube video search collectors for the Google tool namespace.

The official collector uses the YouTube Data API. The browser collector reads
only the public YouTube search results page through the existing CDP browser
session. It does not click, type, submit, export cookies, call hidden caption
endpoints, or bypass challenges.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_utils import safe_preview

from scripts.cdp_console import connect


ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "data" / "google_youtube_search_reports"
LATEST_SEARCH = ROOT / "data" / "google_youtube_search_latest.json"
LATEST_ANALYSIS = ROOT / "data" / "google_youtube_rank_analysis_latest.json"
LATEST_TOPIC_ANALYSIS = ROOT / "data" / "google_youtube_topic_analysis_latest.json"
LATEST_MARKET_RESEARCH = ROOT / "data" / "youtube_market_research_latest.json"
MARKET_RESEARCH_REPORT_DIR = ROOT / "docs" / "reports"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
WORD_RE = re.compile(r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣_+-]{1,}")
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
    "그리고",
    "그래서",
    "합니다",
    "있는",
    "이런",
    "영상",
}
TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "beginner_overview": ("beginner", "basic", "intro", "\uc785\ubb38", "\uae30\ucd08", "\ucd08\ubcf4"),
    "chatgpt_prompting": ("chatgpt", "gpt", "prompt", "\ucc57gpt", "\ud504\ub86c\ud504\ud2b8"),
    "workflow_automation": ("automation", "workflow", "process", "\uc5c5\ubb34", "\uc790\ub3d9\ud654", "\ud504\ub85c\uc138\uc2a4"),
    "spreadsheet_automation": ("excel", "sheets", "spreadsheet", "\uc5d1\uc140", "\uc2dc\ud2b8"),
    "nocode_automation": ("zapier", "make", "n8n", "nocode", "no-code", "\ub178\ucf54\ub4dc"),
    "agent_browser_automation": ("agent", "browser", "crawler", "scraping", "\uc5d0\uc774\uc804\ud2b8", "\ube0c\ub77c\uc6b0\uc800", "\uc2a4\ud06c\ub798\ud551"),
    "monetization_side_hustle": ("money", "profit", "side hustle", "\uc218\uc775", "\ubd80\uc5c5", "\ub3c8"),
    "enterprise_productivity": ("enterprise", "productivity", "team", "\uae30\uc5c5", "\uc0dd\uc0b0\uc131", "\ud611\uc5c5"),
    "smartstore_seller": ("smartstore", "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4", "\ub124\uc774\ubc84\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4", "\uc1fc\ud551\ubab0", "\uc0c1\ud488\ub4f1\ub85d", "\uc0c1\uc138\ud398\uc774\uc9c0", "\uc704\ud0c1\ud310\ub9e4"),
    "commerce_marketing": ("commerce", "marketing", "seo", "\ub9c8\ucf00\ud305", "\uc0c1\uc704\ub178\ucd9c", "\ud0a4\uc6cc\ub4dc", "\uad11\uace0", "\uc804\ud658"),
    "global_sourcing": ("sourcing", "dropshipping", "\uad6c\ub9e4\ub300\ud589", "\uc0ac\uc785", "\uc704\ud0c1", "\uc54c\ub9ac", "\ud0c0\uc624\ubc14\uc624"),
}
TOPIC_KEYWORD_PRESETS: dict[str, tuple[str, ...]] = {
    "ai_work_automation": (
        "AI \uc5c5\ubb34 \uc790\ub3d9\ud654",
        "\ucc57GPT \uc5c5\ubb34 \uc790\ub3d9\ud654",
        "\uc5d1\uc140 \uc790\ub3d9\ud654 AI",
        "\uad6c\uae00\uc2dc\ud2b8 \uc790\ub3d9\ud654",
        "\ub178\ucf54\ub4dc \uc790\ub3d9\ud654",
        "n8n \uc790\ub3d9\ud654",
        "AI \uc5d0\uc774\uc804\ud2b8 \uc790\ub3d9\ud654",
    ),
    "smartstore": (
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \uc2dc\uc791",
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \uc0c1\ud488\ub4f1\ub85d",
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \uc0c1\uc704\ub178\ucd9c",
        "\ub124\uc774\ubc84 \uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \ud310\ub9e4\uc790",
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \ud0a4\uc6cc\ub4dc",
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \uc0c1\uc138\ud398\uc774\uc9c0",
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \uad11\uace0",
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \uc704\ud0c1\ud310\ub9e4",
    ),
    "shopping_mall": (
        "\uc1fc\ud551\ubab0 \ucc3d\uc5c5",
        "\uc1fc\ud551\ubab0 \uc0c1\ud488\ub4f1\ub85d",
        "\uc1fc\ud551\ubab0 \ub9c8\ucf00\ud305",
        "\uc1fc\ud551\ubab0 SEO",
        "\uc1fc\ud551\ubab0 \uc0c1\uc704\ub178\ucd9c",
        "\uc628\ub77c\uc778 \ud310\ub9e4 \ud0a4\uc6cc\ub4dc",
    ),
    "purchase_agency": (
        "\uad6c\ub9e4\ub300\ud589 \uc2dc\uc791",
        "\uad6c\ub9e4\ub300\ud589 \uc0c1\ud488\uc18c\uc2f1",
        "\uad6c\ub9e4\ub300\ud589 \uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4",
        "\ud0c0\uc624\ubc14\uc624 \uc0ac\uc785",
        "\uc54c\ub9ac\uc775\uc2a4\ud504\ub808\uc2a4 \uc704\ud0c1\ud310\ub9e4",
        "\uc704\ud0c1\ud310\ub9e4 \uc0c1\ud488\uc18c\uc2f1",
    ),
    "commerce_marketing": (
        "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4 \ub9c8\ucf00\ud305",
        "\ub124\uc774\ubc84 \uc1fc\ud551 \uc0c1\uc704\ub178\ucd9c",
        "\uc0c1\ud488\uba85 \ud0a4\uc6cc\ub4dc",
        "\uc1fc\ud551\ubab0 \uc804\ud658\uc728",
        "\uc1fc\ud551 \uad11\uace0 \uc6b4\uc601",
        "\uc0c1\uc138\ud398\uc774\uc9c0 \uae30\ud68d",
    ),
}
TOPIC_ALIASES: dict[str, str] = {
    "\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4": "smartstore",
    "\ub124\uc774\ubc84\uc2a4\ub9c8\ud2b8\uc2a4\ud1a0\uc5b4": "smartstore",
    "\uc1fc\ud551\ubab0": "shopping_mall",
    "\uad6c\ub9e4\ub300\ud589": "purchase_agency",
    "\uc704\ud0c1\ud310\ub9e4": "purchase_agency",
    "\ub9c8\ucf00\ud305": "commerce_marketing",
    "ai\uc5c5\ubb34\uc790\ub3d9\ud654": "ai_work_automation",
}


def build_public_signal_model() -> dict[str, Any]:
    """Describe what YouTube market research can and cannot know.

    This model is included in reports so downstream tools do not treat inferred
    opportunity scores as official YouTube search or watch demand.
    """
    return {
        "model": "public_signal_inference",
        "officially_available": [
            "public video search results for a supplied query",
            "public video metadata such as title, channel, published date, and description",
            "public video statistics when available, such as view, like, and comment counts",
            "caption availability hint through the official API",
        ],
        "not_officially_available": [
            "absolute YouTube search volume by keyword",
            "keyword click-through rate",
            "viewer watch history or audience-level behavior",
            "impressions, retention, and traffic-source data for videos we do not own",
            "stable global ranking for an arbitrary topic",
        ],
        "inferred_signals": [
            "observed search position per keyword at collection time",
            "repeated appearance across related keywords",
            "public popularity based on visible or API-provided counts",
            "topic fit from title, description, metadata, and optional transcript summary",
        ],
        "confidence_rule": (
            "Treat results as directional market signals. Confidence improves when a video "
            "appears across multiple related keywords, has public statistics, and has a "
            "transcript summary; it is not proof of absolute user demand."
        ),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_report(
    payload: dict[str, Any],
    path: Path | None = None,
    *,
    latest_path: Path = LATEST_SEARCH,
) -> tuple[dict[str, Any], Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    target = path or REPORT_DIR / f"google_youtube_search_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return payload, target


def _api_key(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("YOUTUBE_DATA_API_KEY", "")
            or os.environ.get("YOUTUBE_API_KEY", "") or os.environ.get("GOOGLE_YOUTUBE_API_KEY", ""))


def _oauth_access_token() -> str | None:
    """저장된 OAuth 토큰을 갱신해서 반환. 없으면 None."""
    import urllib.parse
    token_path = os.environ.get(
        "YOUTUBE_OAUTH_TOKEN_FILE",
        str(Path(__file__).resolve().parents[3] / "ai_orchestrator" / "storage" / "secrets" / "youtube_oauth_authorized_user.json"),
    )
    if not Path(token_path).exists():
        return None
    try:
        t = json.loads(Path(token_path).read_text(encoding="utf-8"))
        data = urllib.parse.urlencode({
            "client_id":     t["client_id"],
            "client_secret": t["client_secret"],
            "refresh_token": t["refresh_token"],
            "grant_type":    "refresh_token",
        }).encode()
        req = urllib.request.Request(
            t.get("token_uri", "https://oauth2.googleapis.com/token"), data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read()).get("access_token")
    except Exception:
        return None


def _get_json(url: str, params: dict[str, str | int]) -> dict[str, Any]:
    # OAuth 우선, 없으면 API 키
    access_token = _oauth_access_token()
    if access_token:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{url}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        )
    else:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(f"{url}?{query}", headers={"Accept": "application/json"})
    with _urlopen_with_dead_proxy_fallback(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _urlopen_with_dead_proxy_fallback(request: urllib.request.Request, *, timeout: int):
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        if not _should_retry_without_proxy(exc):
            raise
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)


def _should_retry_without_proxy(exc: urllib.error.URLError) -> bool:
    reason = str(getattr(exc, "reason", exc))
    proxy_values = [
        os.environ.get("HTTPS_PROXY", ""),
        os.environ.get("HTTP_PROXY", ""),
        os.environ.get("https_proxy", ""),
        os.environ.get("http_proxy", ""),
    ]
    dead_local_proxy = any("127.0.0.1:9" in value or "localhost:9" in value for value in proxy_values)
    return dead_local_proxy and ("10061" in reason or "Connection refused" in reason or "연결을 거부" in reason)


def build_search_url(query: str) -> str:
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)


def search_videos(
    query: str,
    *,
    max_results: int = 10,
    source: str = "auto",
    api_key: str | None = None,
    wait_seconds: float = 3.0,
) -> tuple[dict[str, Any], Path]:
    """Collect YouTube video search results.

    source values:
    - official: official YouTube Data API only.
    - browser: public search results page DOM only.
    - auto: official API when an API key is available, otherwise browser DOM.
    """
    normalized_source = (source or "auto").strip().lower()
    if normalized_source not in {"auto", "official", "browser"}:
        payload = _base_payload(query, normalized_source, max_results)
        payload.update({"ok": False, "status": "blocked", "reason": "unknown_youtube_search_source"})
        return _write_report(payload)

    key = _api_key(api_key)
    has_oauth = bool(_oauth_access_token())
    if normalized_source == "official" or (normalized_source == "auto" and (key or has_oauth)):
        if not key and not has_oauth:
            payload = _base_payload(query, "official", max_results)
            payload.update({
                "ok": False,
                "status": "blocked",
                "reason": "youtube_data_api_key_required_for_official_source",
                "next_step": "Set YOUTUBE_DATA_API_KEY or complete OAuth flow.",
            })
            return _write_report(payload)
        return search_videos_official(query, max_results=max_results, api_key=key)

    return search_videos_browser(query, max_results=max_results, wait_seconds=wait_seconds)


def search_videos_official(
    query: str,
    *,
    max_results: int = 10,
    api_key: str | None = None,
) -> tuple[dict[str, Any], Path]:
    key = _api_key(api_key)
    max_results = max(1, min(int(max_results), 25))
    payload = _base_payload(query, "official", max_results)
    if not key and not _oauth_access_token():
        payload.update({
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_key_required_for_official_source",
            "next_step": "Set YOUTUBE_DATA_API_KEY or complete OAuth flow.",
        })
        return _write_report(payload)

    # API 키가 있으면 key 파라미터, OAuth면 _get_json이 Authorization 헤더 자동 추가
    params: dict[str, str | int] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "safeSearch": "moderate",
    }
    if key:
        params["key"] = key

    try:
        search_data = _get_json(YOUTUBE_SEARCH_URL, params)
    except Exception as exc:
        payload.update({
            "ok": False,
            "status": "blocked",
            "reason": "youtube_data_api_request_failed",
            "error": safe_preview(str(exc), limit=240),
            "results": [],
        })
        return _write_report(payload)
    video_ids = [
        item.get("id", {}).get("videoId", "")
        for item in search_data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    details: dict[str, Any] = {"items": []}
    if video_ids:
        try:
            details = _get_json(
                YOUTUBE_VIDEOS_URL,
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(video_ids),
                    "key": key,
                },
            )
        except Exception:
            details = {"items": []}
    detail_by_id = {item.get("id"): item for item in details.get("items", [])}
    rows: list[dict[str, Any]] = []
    for item in search_data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        detail = detail_by_id.get(video_id, {})
        rows.append({
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": safe_preview(snippet.get("title", ""), limit=180),
            "channel_title": safe_preview(snippet.get("channelTitle", ""), limit=120),
            "published_at": snippet.get("publishedAt", ""),
            "description": safe_preview(snippet.get("description", ""), limit=500),
            "duration": detail.get("contentDetails", {}).get("duration", ""),
            "caption_available_hint": detail.get("contentDetails", {}).get("caption", ""),
            "statistics": {
                "view_count": detail.get("statistics", {}).get("viewCount", ""),
                "like_count": detail.get("statistics", {}).get("likeCount", ""),
                "comment_count": detail.get("statistics", {}).get("commentCount", ""),
            },
            "collection_source": "official_youtube_data_api",
        })

    payload.update({
        "ok": True,
        "status": "ok",
        "reason": "",
        "credential_source": "api_key",
        "api_key_output": "redacted",
        "result_count": len(rows),
        "results": rows,
    })
    return _write_report(payload)


def search_videos_browser(
    query: str,
    *,
    max_results: int = 10,
    wait_seconds: float = 3.0,
) -> tuple[dict[str, Any], Path]:
    max_results = max(1, min(int(max_results), 25))
    payload = _base_payload(query, "browser", max_results)
    payload["search_url"] = build_search_url(query)
    try:
        with connect() as session:
            session.goto(payload["search_url"], wait_idle=False)
            session.wait(wait_seconds)
            snapshot = extract_browser_search_results(session, limit=max_results)
    except Exception as exc:
        payload.update({
            "ok": False,
            "status": "blocked",
            "reason": "youtube_browser_cdp_unavailable",
            "error": safe_preview(str(exc), limit=240),
            "results": [],
        })
        return _write_report(payload)

    if snapshot.get("challenge_detected"):
        payload.update({
            "ok": False,
            "status": "blocked",
            "reason": "youtube_browser_challenge_detected",
            "challenge_markers": snapshot.get("challenge_markers", []),
            "results": [],
        })
        return _write_report(payload)

    payload.update({
        "ok": True,
        "status": "ok",
        "reason": "",
        "final_url": safe_preview(snapshot.get("url", ""), limit=220),
        "title": safe_preview(snapshot.get("title", ""), limit=160),
        "result_count": len(snapshot.get("results", [])),
        "results": snapshot.get("results", []),
        "warnings": snapshot.get("warnings", []),
    })
    return _write_report(payload)


def analyze_ranked_videos(
    *,
    query: str = "",
    search_report_path: str | Path | None = None,
    max_videos: int = 5,
    collect_transcripts: bool = True,
    wait_seconds: float = 3.0,
) -> tuple[dict[str, Any], Path]:
    """Analyze ranked YouTube search results with visible transcript summaries.

    The transcript pass reads only user-visible transcript panel text from the
    browser. It stores derived summaries, keywords, and scores, not full
    third-party transcript text.
    """
    search_payload = _load_search_payload(search_report_path)
    if not search_payload.get("results") and query:
        search_payload, _ = search_videos(query, source="auto", max_results=max_videos)
    results = list(search_payload.get("results", []))[: max(1, min(max_videos, 20))]
    analyzed: list[dict[str, Any]] = []
    for rank, item in enumerate(results, start=1):
        transcript_summary = {"status": "skipped", "reason": "transcript_collection_disabled"}
        if collect_transcripts and item.get("video_id"):
            transcript_summary = collect_visible_transcript_summary(
                item["video_id"],
                wait_seconds=wait_seconds,
            )
        analyzed.append(_score_video(item, rank=rank, transcript_summary=transcript_summary))

    analyzed.sort(key=lambda row: row["scores"]["overall_opportunity_score"], reverse=True)
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "google_youtube_rank_transcript_analysis",
        "query": search_payload.get("query") or safe_preview(query, limit=120),
        "search_source": search_payload.get("source", ""),
        "public_signal_model": build_public_signal_model(),
        "state_change": False,
        "read_only": True,
        "raw_transcript_stored": False,
        "transcript_policy": "visible_transcript_summary_only_no_hidden_endpoint_no_full_text_storage",
        "input_result_count": len(results),
        "analyzed_count": len(analyzed),
        "ranked_videos": analyzed,
        "top_video": analyzed[0] if analyzed else {},
        "strategy_summary": _strategy_summary(analyzed),
    }
    return _write_report(payload, LATEST_ANALYSIS, latest_path=LATEST_ANALYSIS)


def analyze_keyword_topic_market(
    keywords: list[str],
    *,
    per_keyword_limit: int = 10,
    source: str = "auto",
    collect_transcripts: bool = False,
    max_transcript_videos: int = 5,
    collect_comments: bool = False,
    max_comment_videos: int = 5,
    max_comments: int = 20,
    max_comment_pages: int = 1,
    include_comment_replies: bool = False,
    wait_seconds: float = 3.0,
) -> tuple[dict[str, Any], Path]:
    """Analyze a YouTube topic across multiple keyword searches.

    YouTube does not expose a stable global ranking. This collector records
    observed rank per keyword, deduplicates repeated videos, classifies topics,
    and computes opportunity scores from coverage, rank, popularity, and
    transcript-derived signals when available.
    """
    normalized_keywords = _normalize_keywords(keywords)
    if not normalized_keywords:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "google_youtube_keyword_topic_market_analysis",
            "ok": False,
            "status": "blocked",
            "reason": "keywords_required",
            "state_change": False,
            "read_only": True,
            "videos": [],
        }
        return _write_report(payload, LATEST_TOPIC_ANALYSIS, latest_path=LATEST_TOPIC_ANALYSIS)

    videos: dict[str, dict[str, Any]] = {}
    search_runs: list[dict[str, Any]] = []
    for keyword in normalized_keywords:
        try:
            result, path = search_videos(keyword, max_results=per_keyword_limit, source=source, wait_seconds=wait_seconds)
        except Exception as exc:
            result = {
                "status": "blocked",
                "source": source,
                "result_count": 0,
                "reason": "youtube_keyword_search_failed",
                "error": safe_preview(str(exc), limit=240),
                "results": [],
            }
            path = LATEST_SEARCH
        search_runs.append({
            "keyword": keyword,
            "status": result.get("status", ""),
            "source": result.get("source", ""),
            "reason": result.get("reason", ""),
            "result_count": result.get("result_count", 0),
            "report_path": str(path),
        })
        for rank, item in enumerate(result.get("results", []), start=1):
            video_id = str(item.get("video_id") or "")
            if not video_id:
                continue
            entry = videos.setdefault(video_id, {"video": item, "appearances": []})
            if not entry.get("video", {}).get("statistics") and item.get("statistics"):
                entry["video"] = item
            entry["appearances"].append({
                "keyword": keyword,
                "observed_rank": rank,
                "source": result.get("source", ""),
            })

    ordered_entries = sorted(
        videos.values(),
        key=lambda entry: (
            -len(entry["appearances"]),
            min(row["observed_rank"] for row in entry["appearances"]),
            str(entry["video"].get("title", "")),
        ),
    )
    transcript_budget = max(0, min(max_transcript_videos, len(ordered_entries))) if collect_transcripts else 0
    comment_budget = max(0, min(max_comment_videos, len(ordered_entries))) if collect_comments else 0
    analyzed: list[dict[str, Any]] = []
    for index, entry in enumerate(ordered_entries):
        transcript_summary = {"status": "skipped", "reason": "transcript_collection_disabled"}
        if index < transcript_budget and entry.get("video", {}).get("video_id"):
            transcript_summary = collect_visible_transcript_summary(
                entry["video"]["video_id"],
                wait_seconds=wait_seconds,
            )
        comment_summary = {"status": "skipped", "reason": "comment_collection_disabled"}
        if index < comment_budget and entry.get("video", {}).get("video_id"):
            comment_summary = collect_public_comment_summary(
                entry["video"]["video_id"],
                max_results=max_comments,
                max_pages=max_comment_pages,
                max_comments_total=max_comments * max_comment_pages,
                include_replies=include_comment_replies,
            )
        analyzed.append(
            _score_topic_market_video(
                entry,
                total_keywords=len(normalized_keywords),
                transcript_summary=transcript_summary,
                comment_summary=comment_summary,
            )
        )

    analyzed.sort(key=lambda row: row["scores"]["topic_opportunity_score"], reverse=True)
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "google_youtube_keyword_topic_market_analysis",
        "ok": True,
        "status": "ok",
        "official_ranking_note": "YouTube has no stable public global ranking. Rankings here are observed search positions per keyword at collection time.",
        "public_signal_model": build_public_signal_model(),
        "keywords": normalized_keywords,
        "per_keyword_limit": per_keyword_limit,
        "source": source,
        "state_change": False,
        "read_only": True,
        "raw_transcript_stored": False,
        "raw_comments_stored": False,
        "comment_policy": "official_youtube_data_api_top_level_comments_summary_only",
        "search_runs": search_runs,
        "unique_video_count": len(analyzed),
        "videos": analyzed,
        "topic_clusters": _topic_clusters(analyzed),
        "top_channels": _top_channels(analyzed),
        "strategy_summary": _topic_strategy_summary(analyzed),
    }
    return _write_report(payload, LATEST_TOPIC_ANALYSIS, latest_path=LATEST_TOPIC_ANALYSIS)


def expand_topic_keywords(topic: str, *, auto_keywords: bool = True) -> list[str]:
    value = re.sub(r"\s+", "", str(topic or "")).strip().lower()
    if not value:
        return []
    preset_key = TOPIC_ALIASES.get(value, value)
    if auto_keywords and preset_key in TOPIC_KEYWORD_PRESETS:
        return list(TOPIC_KEYWORD_PRESETS[preset_key])
    return [str(topic).strip()]


def run_market_research(
    *,
    topic: str = "",
    keywords: list[str] | None = None,
    auto_keywords: bool = True,
    per_keyword_limit: int = 10,
    source: str = "auto",
    collect_transcripts: bool = False,
    max_transcript_videos: int = 5,
    collect_comments: bool = True,
    max_comment_videos: int = 5,
    max_comments: int = 20,
    max_comment_pages: int = 1,
    include_comment_replies: bool = False,
    wait_seconds: float = 3.0,
) -> tuple[dict[str, Any], Path, Path]:
    """Run the integrated YouTube market research pipeline."""
    expanded_keywords: list[str] = []
    if topic:
        expanded_keywords.extend(expand_topic_keywords(topic, auto_keywords=auto_keywords))
    expanded_keywords.extend(keywords or [])
    analysis, analysis_path = analyze_keyword_topic_market(
        expanded_keywords,
        per_keyword_limit=per_keyword_limit,
        source=source,
        collect_transcripts=collect_transcripts,
        max_transcript_videos=max_transcript_videos,
        collect_comments=collect_comments,
        max_comment_videos=max_comment_videos,
        max_comments=max_comments,
        max_comment_pages=max_comment_pages,
        include_comment_replies=include_comment_replies,
        wait_seconds=wait_seconds,
    )
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_market_research_run",
        "ok": analysis.get("status") == "ok",
        "status": analysis.get("status", "unknown"),
        "topic": safe_preview(topic, limit=120),
        "keywords": analysis.get("keywords", expanded_keywords),
        "state_change": False,
        "read_only": True,
        "source": source,
        "limits": {
            "per_keyword_limit": per_keyword_limit,
            "collect_transcripts": collect_transcripts,
            "max_transcript_videos": max_transcript_videos,
            "collect_comments": collect_comments,
            "max_comment_videos": max_comment_videos,
            "max_comments": max_comments,
            "max_comment_pages": max_comment_pages,
            "include_comment_replies": include_comment_replies,
        },
        "analysis_report": str(analysis_path),
        "public_signal_model": analysis.get("public_signal_model", build_public_signal_model()),
        "official_ranking_note": analysis.get("official_ranking_note", ""),
        "unique_video_count": analysis.get("unique_video_count", 0),
        "top_videos": analysis.get("videos", [])[:20],
        "topic_clusters": analysis.get("topic_clusters", []),
        "top_channels": analysis.get("top_channels", []),
        "strategy_summary": analysis.get("strategy_summary", {}),
        "raw_transcript_stored": analysis.get("raw_transcript_stored", False),
        "raw_comments_stored": analysis.get("raw_comments_stored", False),
    }
    LATEST_MARKET_RESEARCH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_MARKET_RESEARCH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = _write_market_research_markdown(payload)
    payload["markdown_report"] = str(markdown_path)
    LATEST_MARKET_RESEARCH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, LATEST_MARKET_RESEARCH, markdown_path


def collect_visible_transcript_summary(
    video_id: str,
    *,
    wait_seconds: float = 3.0,
    max_segments: int = 180,
) -> dict[str, Any]:
    """Open a video and summarize visible transcript text via CDP.

    This uses visible page controls only. It does not call timedtext, captions,
    or other hidden transcript endpoints.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    base = {
        "status": "blocked",
        "reason": "",
        "video_id": safe_preview(video_id, limit=20),
        "url": url,
        "raw_transcript_stored": False,
        "hidden_endpoint_scraping": False,
        "segments_observed": 0,
        "word_like_count": 0,
        "top_keywords": [],
        "highlights": [],
    }
    try:
        with connect() as session:
            session.goto(url, wait_idle=False)
            session.wait(wait_seconds)
            opened = _try_open_transcript_panel(session)
            if opened.get("needs_wait"):
                session.wait(1.5)
            segments = _extract_visible_transcript_segments(session, limit=max_segments)
    except Exception as exc:
        base["reason"] = "youtube_transcript_cdp_unavailable"
        base["error"] = safe_preview(str(exc), limit=220)
        return base

    if not segments:
        base["reason"] = "visible_transcript_not_found"
        base["open_transcript_result"] = opened
        return base

    summary = summarize_transcript_segments(segments)
    base.update(summary)
    base["status"] = "ok"
    base["reason"] = ""
    base["open_transcript_result"] = opened
    return base


def collect_public_comment_summary(
    video_id: str,
    *,
    max_results: int = 20,
    max_pages: int = 1,
    max_comments_total: int = 100,
    include_replies: bool = False,
) -> dict[str, Any]:
    """Collect and summarize public top-level comments through official API only."""
    try:
        from scripts.youtube import research

        comments, report_path = research.collect_comments(
            video_id,
            max_results=max_results,
            max_pages=max_pages,
            max_comments_total=max_comments_total,
            include_replies=include_replies,
        )
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": "youtube_comment_collection_unavailable",
            "error": safe_preview(str(exc), limit=200),
            "raw_comments_stored": False,
            "source_policy": "official_youtube_data_api_only",
        }
    rows = comments.get("comments", []) if comments.get("status") == "ok" else []
    text = " ".join(str(row.get("text", "")) for row in rows if isinstance(row, dict))
    keywords = _top_keywords(text, limit=12)
    liked = sorted(
        [row for row in rows if isinstance(row, dict)],
        key=lambda row: _int_value(row.get("like_count")),
        reverse=True,
    )[:5]
    return {
        "status": comments.get("status", "unknown"),
        "reason": comments.get("reason", ""),
        "video_id": safe_preview(video_id, limit=80),
        "comment_count_observed": len(rows),
        "report_path": str(report_path),
        "raw_comments_stored": False,
        "source_policy": "official_youtube_data_api_top_level_comments_summary_only",
        "classification": comments.get("classification", {}),
        "top_keywords": keywords,
        "sample_comments": [
            {
                "like_count": _int_value(row.get("like_count")),
                "text_preview": safe_preview(row.get("text", ""), limit=180),
            }
            for row in liked[:3]
        ],
    }


def extract_browser_search_results(session: Any, *, limit: int = 10) -> dict[str, Any]:
    data, err = session.js_json(
        f"""(function() {{
            function clean(value, max) {{
                return ((value || '') + '').replace(/\\s+/g, ' ').trim().slice(0, max);
            }}
            function visible(el) {{
                if (!el) return false;
                var rect = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }}
            function videoIdFromUrl(url) {{
                try {{
                    var parsed = new URL(url, location.href);
                    return parsed.searchParams.get('v') || '';
                }} catch (e) {{
                    return '';
                }}
            }}
            var text = clean(document.body && document.body.innerText, 4000).toLowerCase();
            var challengeMarkers = ['captcha', 'unusual traffic', 'robot', 'verify you are human', 'not a robot']
                .filter(function(marker) {{ return text.indexOf(marker) >= 0; }});
            var nodes = Array.from(document.querySelectorAll('ytd-video-renderer, ytd-grid-video-renderer, ytd-rich-item-renderer, ytd-compact-video-renderer'));
            var seen = {{}};
            var results = [];
            for (var i = 0; i < nodes.length && results.length < {limit}; i++) {{
                var node = nodes[i];
                if (!visible(node)) continue;
                var link = node.querySelector('a#video-title, a#video-title-link, a[href*="/watch?v="]');
                if (!link) continue;
                var href = link.href || link.getAttribute('href') || '';
                var videoId = videoIdFromUrl(href);
                if (!videoId || seen[videoId]) continue;
                seen[videoId] = true;
                var title = clean(link.textContent || link.getAttribute('title') || link.getAttribute('aria-label'), 180);
                var channel = clean((node.querySelector('ytd-channel-name yt-formatted-string, #channel-name yt-formatted-string, a.yt-simple-endpoint[href*="/@"]') || {{}}).textContent, 120);
                var meta = Array.from(node.querySelectorAll('#metadata-line span, ytd-video-meta-block span'))
                    .map(function(el) {{ return clean(el.textContent, 80); }})
                    .filter(Boolean);
                var description = clean((node.querySelector('#description-text, #dismissible #description') || {{}}).textContent, 300);
                var thumbnail = node.querySelector('img');
                results.push({{
                    video_id: videoId,
                    url: 'https://www.youtube.com/watch?v=' + videoId,
                    title: title,
                    channel_title: channel,
                    metadata_line: meta,
                    description: description,
                    thumbnail_present: !!thumbnail,
                    collection_source: 'public_youtube_search_dom'
                }});
            }}
            return {{
                url: location.href,
                title: document.title,
                challenge_detected: challengeMarkers.length > 0,
                challenge_markers: challengeMarkers,
                result_count: results.length,
                results: results,
                warnings: results.length ? [] : ['no_visible_video_results_detected']
            }};
        }})()"""
    )
    if err or not isinstance(data, dict):
        return {
            "url": "",
            "title": "",
            "challenge_detected": False,
            "challenge_markers": [],
            "results": [],
            "warnings": [safe_preview(str(data), limit=200)],
        }
    return _sanitize_browser_snapshot(data)


def _try_open_transcript_panel(session: Any) -> dict[str, Any]:
    data, err = session.js_json(
        r"""(function() {
            function visible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }
            var labels = ['Show transcript', 'Transcript', '스크립트 표시', '스크립트', '자막 스크립트', '대본'];
            var controls = Array.from(document.querySelectorAll('button, ytd-button-renderer, tp-yt-paper-item, yt-button-shape button'));
            for (var i = 0; i < controls.length; i++) {
                var el = controls[i];
                if (!visible(el)) continue;
                var text = ((el.innerText || el.textContent || '') + '').trim();
                var aria = ((el.getAttribute('aria-label') || '') + '').trim();
                for (var j = 0; j < labels.length; j++) {
                    if (text.indexOf(labels[j]) >= 0 || aria.indexOf(labels[j]) >= 0) {
                        el.click();
                        return {clicked: true, label: (text || aria).slice(0, 80), needs_wait: true};
                    }
                }
            }
            return {clicked: false, label: '', needs_wait: false};
        })()"""
    )
    if err or not isinstance(data, dict):
        return {"clicked": False, "label": "", "needs_wait": False, "error": safe_preview(str(data), limit=120)}
    return {
        "clicked": bool(data.get("clicked")),
        "label": safe_preview(data.get("label", ""), limit=80),
        "needs_wait": bool(data.get("needs_wait")),
    }


def _extract_visible_transcript_segments(session: Any, *, limit: int = 180) -> list[str]:
    data, err = session.js_json(
        f"""(function() {{
            function visible(el) {{
                if (!el) return false;
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }}
            var selectors = [
                'ytd-transcript-segment-renderer',
                'yt-formatted-string.segment-text',
                '#segments-container yt-formatted-string',
                'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]'
            ];
            var rows = [];
            for (var s = 0; s < selectors.length; s++) {{
                var nodes = Array.from(document.querySelectorAll(selectors[s]));
                for (var i = 0; i < nodes.length; i++) {{
                    var el = nodes[i];
                    if (!visible(el)) continue;
                    var text = ((el.innerText || el.textContent || '') + '').replace(/\\s+/g, ' ').trim();
                    if (text && text.length >= 2) rows.push(text);
                }}
            }}
            var seen = {{}};
            return rows.filter(function(text) {{
                var key = text.toLowerCase();
                if (seen[key]) return false;
                seen[key] = true;
                return true;
            }}).slice(0, {limit});
        }})()"""
    )
    if err or not isinstance(data, list):
        return []
    return [safe_preview(item, limit=240) for item in data if str(item).strip()]


def summarize_transcript_segments(segments: list[str]) -> dict[str, Any]:
    clean_segments = [re.sub(r"\s+", " ", str(item)).strip() for item in segments if str(item).strip()]
    text = " ".join(clean_segments)
    keywords = _top_keywords(text)
    highlights = [
        safe_preview(segment, limit=180)
        for segment in clean_segments
        if len(segment) >= 20 and not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", segment)
    ][:10]
    return {
        "segments_observed": len(clean_segments),
        "word_like_count": len(WORD_RE.findall(text)),
        "top_keywords": keywords,
        "highlights": highlights,
        "topics": [item["keyword"] for item in keywords[:8]],
    }


def _sanitize_browser_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    sanitized = {
        "url": safe_preview(str(data.get("url", "")).split("&pp=", 1)[0], limit=220),
        "title": safe_preview(data.get("title", ""), limit=160),
        "challenge_detected": bool(data.get("challenge_detected")),
        "challenge_markers": [safe_preview(item, limit=80) for item in data.get("challenge_markers", [])],
        "warnings": [safe_preview(item, limit=160) for item in data.get("warnings", [])],
        "results": [],
    }
    for item in data.get("results", []):
        if not isinstance(item, dict):
            continue
        sanitized["results"].append({
            "video_id": safe_preview(item.get("video_id", ""), limit=20),
            "url": safe_preview(item.get("url", ""), limit=120),
            "title": safe_preview(item.get("title", ""), limit=180),
            "channel_title": safe_preview(item.get("channel_title", ""), limit=120),
            "metadata_line": [safe_preview(value, limit=80) for value in item.get("metadata_line", [])[:4]],
            "description": safe_preview(item.get("description", ""), limit=300),
            "thumbnail_present": bool(item.get("thumbnail_present")),
            "collection_source": "public_youtube_search_dom",
        })
    return sanitized


def _load_search_payload(search_report_path: str | Path | None) -> dict[str, Any]:
    path = Path(search_report_path) if search_report_path else LATEST_SEARCH
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {"results": []}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"results": []}
    return parsed if isinstance(parsed, dict) else {"results": []}


def _top_keywords(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    words = [word for word in words if word not in STOPWORDS and len(word) > 1]
    return [{"keyword": word, "count": count} for word, count in Counter(words).most_common(limit)]


def _score_video(item: dict[str, Any], *, rank: int, transcript_summary: dict[str, Any]) -> dict[str, Any]:
    stats = item.get("statistics", {}) if isinstance(item.get("statistics"), dict) else {}
    views = _int_value(stats.get("view_count") or _metadata_number(item.get("metadata_line", []), "views"))
    likes = _int_value(stats.get("like_count"))
    comments = _int_value(stats.get("comment_count"))
    rank_score = max(0, 100 - ((rank - 1) * 6))
    view_score = min(100, views ** 0.5 / 40) if views else 0
    engagement_score = min(100, ((likes * 2) + (comments * 4)) ** 0.5 / 8) if (likes or comments) else 0
    transcript_score = 100 if transcript_summary.get("status") == "ok" else 25
    title_keyword_score = min(100, len(_top_keywords(str(item.get("title", "")), limit=6)) * 12)
    overall = round(
        (rank_score * 0.30)
        + (view_score * 0.20)
        + (engagement_score * 0.20)
        + (transcript_score * 0.20)
        + (title_keyword_score * 0.10),
        2,
    )
    return {
        "search_rank": rank,
        "video_id": item.get("video_id", ""),
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "channel_title": item.get("channel_title", ""),
        "metadata_line": item.get("metadata_line", []),
        "statistics": stats,
        "transcript_summary": transcript_summary,
        "scores": {
            "search_rank_score": round(rank_score, 2),
            "view_score": round(view_score, 2),
            "engagement_score": round(engagement_score, 2),
            "transcript_score": transcript_score,
            "title_keyword_match_score": title_keyword_score,
            "overall_opportunity_score": overall,
        },
        "analysis": {
            "why_it_matters": _why_it_matters(rank, views, transcript_summary),
            "topic_keywords": transcript_summary.get("topics") or [row["keyword"] for row in _top_keywords(str(item.get("title", "")), limit=8)],
            "usable_reference": transcript_summary.get("status") == "ok",
        },
        "signal_quality": _video_signal_quality(
            source_count=1,
            coverage_count=1,
            total_keywords=1,
            has_public_stats=bool(views or likes or comments),
            transcript_summary=transcript_summary,
            sources=[str(item.get("collection_source") or "")],
        ),
    }


def _strategy_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "empty", "recommendations": []}
    keyword_counter: Counter[str] = Counter()
    transcript_ready = 0
    for row in rows:
        if row.get("transcript_summary", {}).get("status") == "ok":
            transcript_ready += 1
        for keyword in row.get("analysis", {}).get("topic_keywords", []):
            keyword_counter[str(keyword)] += 1
    return {
        "status": "ok",
        "transcript_ready_count": transcript_ready,
        "common_keywords": [{"keyword": key, "count": count} for key, count in keyword_counter.most_common(12)],
        "recommendations": [
            "Use high-ranking videos to identify title and topic patterns.",
            "Use transcript summaries to compare structure, not to copy source text.",
            "Prioritize videos with transcript summaries and strong engagement for deeper review.",
        ],
    }


def _why_it_matters(rank: int, views: int, transcript_summary: dict[str, Any]) -> str:
    parts = [f"search_rank={rank}"]
    if views:
        parts.append(f"views={views}")
    parts.append("transcript=available" if transcript_summary.get("status") == "ok" else "transcript=not_collected")
    return ", ".join(parts)


def _int_value(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    try:
        return int(float(text))
    except ValueError:
        return 0


def _metadata_number(values: Any, marker: str) -> int:
    if not isinstance(values, list):
        return 0
    for value in values:
        text = str(value).lower().replace(",", "")
        if marker not in text:
            continue
        multiplier = 1
        if "k" in text:
            multiplier = 1_000
        elif "m" in text:
            multiplier = 1_000_000
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            return int(float(match.group(1)) * multiplier)
    return 0


def _normalize_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for keyword in keywords:
        value = re.sub(r"\s+", " ", str(keyword or "")).strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized


def _score_topic_market_video(
    entry: dict[str, Any],
    *,
    total_keywords: int,
    transcript_summary: dict[str, Any],
    comment_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = entry["video"]
    appearances = entry["appearances"]
    comment_summary = comment_summary or {"status": "skipped", "reason": "comment_collection_disabled"}
    ranks = [int(row["observed_rank"]) for row in appearances]
    best_rank = min(ranks)
    average_rank = round(sum(ranks) / len(ranks), 2)
    coverage_score = min(100, (len({row["keyword"] for row in appearances}) / max(1, total_keywords)) * 100)
    best_rank_score = max(0, 100 - ((best_rank - 1) * 6))
    average_rank_score = max(0, 100 - ((average_rank - 1) * 4))
    stats = item.get("statistics", {}) if isinstance(item.get("statistics"), dict) else {}
    views = _int_value(stats.get("view_count") or _metadata_number(item.get("metadata_line", []), "views"))
    likes = _int_value(stats.get("like_count"))
    comments = _int_value(stats.get("comment_count"))
    popularity_score = min(100, (views ** 0.5 / 35) + (((likes * 2) + (comments * 4)) ** 0.5 / 8)) if (views or likes or comments) else 0
    transcript_score = 100 if transcript_summary.get("status") == "ok" else 30
    comment_score = min(100, 35 + (comment_summary.get("comment_count_observed", 0) * 5)) if comment_summary.get("status") == "ok" else 20
    topic = _classify_topic(item, transcript_summary)
    topic_score = topic["confidence_score"]
    source_values = sorted({str(row.get("source", "")) for row in appearances if row.get("source")})
    coverage_count = len({row["keyword"] for row in appearances})
    signal_quality = _video_signal_quality(
        source_count=len(source_values),
        coverage_count=coverage_count,
        total_keywords=total_keywords,
        has_public_stats=bool(views or likes or comments),
        transcript_summary=transcript_summary,
        sources=source_values,
    )
    opportunity = round(
        (coverage_score * 0.25)
        + (best_rank_score * 0.20)
        + (average_rank_score * 0.15)
        + (popularity_score * 0.15)
        + (transcript_score * 0.10)
        + (comment_score * 0.05)
        + (topic_score * 0.10),
        2,
    )
    return {
        "video_id": item.get("video_id", ""),
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "channel_title": item.get("channel_title", ""),
        "appearances": appearances,
        "coverage_count": len({row["keyword"] for row in appearances}),
        "best_observed_rank": best_rank,
        "average_observed_rank": average_rank,
        "statistics": stats,
        "metadata_line": item.get("metadata_line", []),
        "topic_classification": topic,
        "transcript_summary": transcript_summary,
        "comment_summary": comment_summary,
        "signal_quality": signal_quality,
        "scores": {
            "coverage_score": round(coverage_score, 2),
            "best_rank_score": round(best_rank_score, 2),
            "average_rank_score": round(average_rank_score, 2),
            "popularity_score": round(popularity_score, 2),
            "transcript_score": transcript_score,
            "comment_signal_score": comment_score,
            "topic_match_score": topic_score,
            "topic_opportunity_score": opportunity,
        },
    }


def _classify_topic(item: dict[str, Any], transcript_summary: dict[str, Any]) -> dict[str, Any]:
    pieces = [
        str(item.get("title", "")),
        str(item.get("description", "")),
        " ".join(str(value) for value in item.get("metadata_line", [])),
        " ".join(str(value) for value in transcript_summary.get("topics", [])),
        " ".join(str(row.get("keyword", "")) for row in transcript_summary.get("top_keywords", []) if isinstance(row, dict)),
    ]
    text = " ".join(pieces).lower()
    matches: list[dict[str, Any]] = []
    for topic, terms in TOPIC_RULES.items():
        hits = [term for term in terms if term.lower() in text]
        if hits:
            matches.append({"topic": topic, "matched_terms": hits, "score": min(100, len(hits) * 25)})
    matches.sort(key=lambda row: row["score"], reverse=True)
    if not matches:
        keyword_fallback = [row["keyword"] for row in _top_keywords(text, limit=5)]
        return {
            "primary_topic": "uncategorized",
            "confidence_score": 10 if keyword_fallback else 0,
            "matched_topics": [],
            "fallback_keywords": keyword_fallback,
        }
    return {
        "primary_topic": matches[0]["topic"],
        "confidence_score": matches[0]["score"],
        "matched_topics": matches[:3],
        "fallback_keywords": [row["keyword"] for row in _top_keywords(text, limit=5)],
    }


def _video_signal_quality(
    *,
    source_count: int,
    coverage_count: int,
    total_keywords: int,
    has_public_stats: bool,
    transcript_summary: dict[str, Any],
    sources: list[str],
) -> dict[str, Any]:
    coverage_ratio = coverage_count / max(1, total_keywords)
    points = 20
    if coverage_count >= 2:
        points += 25
    elif coverage_count == 1:
        points += 10
    if coverage_ratio >= 0.4:
        points += 15
    if has_public_stats:
        points += 20
    if transcript_summary.get("status") == "ok":
        points += 20
    if source_count > 0:
        points += 5
    if source_count > 1:
        points += 5
    score = min(100, points)
    if score >= 75:
        level = "high_directional"
    elif score >= 50:
        level = "medium_directional"
    else:
        level = "low_directional"
    return {
        "level": level,
        "confidence_score": score,
        "official_demand_data": False,
        "sources": sources,
        "basis": {
            "observed_keyword_coverage_count": coverage_count,
            "observed_keyword_coverage_ratio": round(coverage_ratio, 3),
            "public_stats_available": has_public_stats,
            "transcript_summary_available": transcript_summary.get("status") == "ok",
        },
        "interpretation": "directional_public_signal_not_absolute_youtube_demand",
    }


def _topic_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        topic = row.get("topic_classification", {}).get("primary_topic", "uncategorized")
        grouped.setdefault(topic, []).append(row)
    clusters = []
    for topic, items in grouped.items():
        clusters.append({
            "topic": topic,
            "video_count": len(items),
            "average_opportunity_score": round(
                sum(item["scores"]["topic_opportunity_score"] for item in items) / max(1, len(items)),
                2,
            ),
            "top_video_ids": [item["video_id"] for item in items[:5]],
        })
    clusters.sort(key=lambda row: (row["average_opportunity_score"], row["video_count"]), reverse=True)
    return clusters


def _top_channels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    channels: dict[str, dict[str, Any]] = {}
    for row in rows:
        channel = str(row.get("channel_title") or "")
        if not channel:
            continue
        item = channels.setdefault(channel, {"channel_title": channel, "video_count": 0, "best_score": 0.0})
        item["video_count"] += 1
        item["best_score"] = max(item["best_score"], row["scores"]["topic_opportunity_score"])
    return sorted(channels.values(), key=lambda row: (row["best_score"], row["video_count"]), reverse=True)[:12]


def _topic_strategy_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "empty", "recommendations": []}
    transcript_ready = sum(1 for row in rows if row.get("transcript_summary", {}).get("status") == "ok")
    repeated = [row for row in rows if row.get("coverage_count", 0) >= 2]
    return {
        "status": "ok",
        "transcript_ready_count": transcript_ready,
        "repeated_keyword_video_count": len(repeated),
        "recommendations": [
            "Treat repeated appearances across keywords as stronger topic authority than a single search rank.",
            "Use transcript-derived topics to define content clusters before deciding a title.",
            "Compare high-score videos for structure and gaps; do not copy transcript text.",
        ],
    }


def _write_market_research_markdown(payload: dict[str, Any]) -> Path:
    MARKET_RESEARCH_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = MARKET_RESEARCH_REPORT_DIR / f"youtube_market_research_{_stamp()}.md"
    lines: list[str] = [
        "# YouTube Market Research Report",
        "",
        f"- Created: {payload.get('created_at', '')}",
        f"- Topic: {payload.get('topic') or '-'}",
        f"- Status: {payload.get('status')}",
        f"- Unique videos: {payload.get('unique_video_count', 0)}",
        f"- Raw transcript stored: {payload.get('raw_transcript_stored', False)}",
        f"- Raw comments stored: {payload.get('raw_comments_stored', False)}",
        "",
        "## Keywords",
        "",
    ]
    for keyword in payload.get("keywords", [])[:40]:
        lines.append(f"- {keyword}")
    lines.extend(["", "## Top Videos", ""])
    for index, item in enumerate(payload.get("top_videos", [])[:15], start=1):
        scores = item.get("scores", {})
        topic = item.get("topic_classification", {})
        comments = item.get("comment_summary", {})
        transcript = item.get("transcript_summary", {})
        lines.extend(
            [
                f"### {index}. {item.get('title') or '-'}",
                "",
                f"- Video: {item.get('url') or item.get('video_id') or '-'}",
                f"- Channel: {item.get('channel_title') or '-'}",
                f"- Score: {scores.get('topic_opportunity_score', '-')}",
                f"- Topic: {topic.get('primary_topic', '-')}",
                f"- Coverage: {item.get('coverage_count', 0)} keyword(s)",
                f"- Best observed rank: {item.get('best_observed_rank', '-')}",
                f"- Comments: {comments.get('status', 'skipped')} / observed={comments.get('comment_count_observed', 0)}",
                f"- Transcript: {transcript.get('status', 'skipped')}",
                "",
            ]
        )
    lines.extend(["## Topic Clusters", ""])
    for cluster in payload.get("topic_clusters", [])[:12]:
        lines.append(
            f"- {cluster.get('topic')}: videos={cluster.get('video_count', 0)}, "
            f"avg_score={cluster.get('average_opportunity_score', 0)}"
        )
    lines.extend(["", "## Top Channels", ""])
    for channel in payload.get("top_channels", [])[:12]:
        lines.append(
            f"- {channel.get('channel_title')}: videos={channel.get('video_count', 0)}, "
            f"best_score={channel.get('best_score', 0)}"
        )
    strategy = payload.get("strategy_summary", {})
    lines.extend(["", "## Strategy Notes", ""])
    for note in strategy.get("recommendations", []):
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Data Boundary",
            "",
            "- This report uses public and official API-visible signals.",
            "- It does not claim absolute YouTube search volume, CTR, watch history, impressions, or retention for videos we do not own.",
            "- Scores are directional public-signal estimates.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _base_payload(query: str, source: str, max_results: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "google_youtube_search",
        "query": safe_preview(query, limit=120),
        "source": source,
        "max_results": max_results,
        "state_change": False,
        "read_only": True,
        "no_click": True,
        "no_input": True,
        "no_submit": True,
        "cookie_export": False,
        "storage_export": False,
        "hidden_endpoint_scraping": False,
        "results": [],
    }


__all__ = [
    "build_search_url",
    "expand_topic_keywords",
    "extract_browser_search_results",
    "analyze_ranked_videos",
    "analyze_keyword_topic_market",
    "run_market_research",
    "collect_public_comment_summary",
    "collect_visible_transcript_summary",
    "build_public_signal_model",
    "search_videos",
    "search_videos_browser",
    "search_videos_official",
]
