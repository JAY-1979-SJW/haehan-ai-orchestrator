"""Scoring, topic classification, and strategy summary helpers."""
from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.google.youtube.search_common import (
    TOPIC_RULES,
    _int_value,
    _metadata_number,
    _top_keywords,
)


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


def _why_it_matters(rank: int, views: int, transcript_summary: dict[str, Any]) -> str:
    parts = [f"search_rank={rank}"]
    if views:
        parts.append(f"views={views}")
    parts.append("transcript=available" if transcript_summary.get("status") == "ok" else "transcript=not_collected")
    return ", ".join(parts)
