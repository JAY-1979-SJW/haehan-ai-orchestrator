"""YouTube 공개 댓글 수집 — 공식 Data API(commentThreads) 만 사용하는 공용 잎.

scripts/youtube(리서치)와 scripts/google/youtube(검색·분석)가 함께 쓴다. google 도메인은 youtube 도메인을 import 할 수 없어서(금지 import 규칙)
예전에는 동적 import 로 우회했다 — 공용부를 아래층(scripts/common)으로 내려 정적 import 로 해결(2026-10-08).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_orchestrator.core.security_utils import safe_preview
from scripts.common.youtube_api_common import (
    ROOT,
    SENSITIVE_WORDS,
    YOUTUBE_COMMENT_THREADS_URL,
    _api_key,
    _get_json,
    _get_json_oauth,
    _int_value,
    _now,
    _oauth_token,
    _top_keywords,
    _write_report,
)

COMMENT_CLASS_RULES: dict[str, tuple[str, ...]] = {
    "question": ("?", "how", "what", "why", "where", "when", "어떻게", "뭐", "왜", "질문", "궁금"),
    "positive_feedback": ("great", "good", "thanks", "helpful", "useful", "감사", "좋", "도움", "유익"),
    "negative_feedback": ("bad", "wrong", "problem", "error", "hate", "아쉽", "문제", "오류", "불편", "별로"),
    "request": ("please", "can you", "make", "show", "해주", "만들", "보여", "요청"),
    "price_business": ("price", "cost", "money", "profit", "가격", "비용", "수익", "매출", "돈"),
    "implementation": ("setup", "install", "tool", "code", "api", "설정", "설치", "도구", "코드", "자동화"),
}


def _append_thread_comments(
    comments: list[dict[str, Any]], item: dict[str, Any], include_replies: bool, max_comments_total: int
) -> bool:
    """댓글 스레드 1건(최상위 + 선택적 답글)을 comments 에 추가. 상한 도달 시 True."""
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
        return True
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
    return len(comments) >= max_comments_total


def collect_comments(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
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
                if _append_thread_comments(comments, item, include_replies, max_comments_total):
                    break
            next_page_token = str(data.get("nextPageToken") or "")
            if not next_page_token:
                break
    except Exception as exc:  # noqa: BLE001 - 유튜브 리서치 검색(읽기전용, SQLite 캐시 활용) — 캐시 조회/저장 실패는 무시(캐시미스로 간주), API 조회 실패는 status를 blocked_or_unavailable/partial로 기록
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
