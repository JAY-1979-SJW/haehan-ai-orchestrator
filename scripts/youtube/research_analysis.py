"""YouTube video context analysis, strategy scoring, and transcript analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.common.youtube_api_common import (
    LATEST_ANALYSIS,
    ROOT,
    SENSITIVE_WORDS,
    WORD_RE,
    _bounded,
    _int,
    _now,
    _read_transcript,
    _sentences,
    _top_keywords,
    _write_report,
)
from ai_orchestrator.core.security_utils import safe_preview


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
    return payload, _write_report(
        payload, ROOT / "data" / "youtube_video_context_analysis_latest.json", "youtube_video_context_analysis"
    )


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
    question_comments = sum(
        1 for row in comment_rows if "?" in str(row.get("text", "")) or "어떻게" in str(row.get("text", ""))
    )

    demand_score = _bounded(min(60, views**0.5 / 20) + min(25, comment_count * 2) + min(15, likes**0.5 / 10))
    comment_pain_score = _bounded((question_comments / max(1, len(comment_rows))) * 70 + min(30, comment_count * 1.5))
    topic_fit_score = 50
    if topic_words:
        overlap = len(topic_words & keyword_set)
        topic_fit_score = _bounded(35 + overlap * 20)
    script_quality_score = _bounded(
        35 + min(35, transcript_words / 60) + (20 if video.get("caption_available_hint") == "true" else 0)
    )
    hook_score = _bounded(70 if 20 <= title_len <= 80 else 45)
    competition_score = _bounded(80 - min(55, views**0.5 / 15))
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
    return payload, _write_report(
        payload, ROOT / "data" / "youtube_video_strategy_scorecard_latest.json", "youtube_video_strategy_scorecard"
    )


def analyze_transcript(
    transcript_file: str | Path, *, video_id: str = "", title: str = ""
) -> tuple[dict[str, Any], Path]:
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
