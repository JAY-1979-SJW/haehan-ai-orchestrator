"""High-level analysis, market research pipeline, comment summary, and reporting."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.common.youtube_comments import collect_comments
from scripts.google.youtube.search_common import (
    LATEST_ANALYSIS,
    LATEST_MARKET_RESEARCH,
    LATEST_SEARCH,
    LATEST_TOPIC_ANALYSIS,
    MARKET_RESEARCH_REPORT_DIR,
    TOPIC_ALIASES,
    TOPIC_KEYWORD_PRESETS,
    _int_value,
    _normalize_keywords,
    _now,
    _stamp,
    _top_keywords,
    _write_report,
    build_public_signal_model,
)
from scripts.google.youtube.search_score import (
    _score_topic_market_video,
    _score_video,
    _strategy_summary,
    _topic_strategy_summary,
)
from scripts.google.youtube.search_search import (
    _load_search_payload,
    search_videos,
)
from scripts.google.youtube.search_transcript import collect_visible_transcript_summary
from ai_orchestrator.core.security_utils import safe_preview


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


def analyze_keyword_topic_market(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
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
    order: str = "relevance",
    published_after: str | None = None,
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
            result, path = search_videos(
                keyword,
                max_results=per_keyword_limit,
                source=source,
                wait_seconds=wait_seconds,
                order=order,
                published_after=published_after,
            )
        except Exception as exc:  # noqa: BLE001 - 유튜브 검색/댓글 수집 분석(읽기 전용) -- 키워드 검색·댓글 수집 실패 시 status=blocked로 처리(안전한 실패), 에러 메시지는 safe_preview로 200자 제한 축약해 민감정보 노출 방지
            result = {
                "status": "blocked",
                "source": source,
                "result_count": 0,
                "reason": "youtube_keyword_search_failed",
                "error": safe_preview(str(exc), limit=240),
                "results": [],
            }
            path = LATEST_SEARCH
        search_runs.append(
            {
                "keyword": keyword,
                "status": result.get("status", ""),
                "source": result.get("source", ""),
                "reason": result.get("reason", ""),
                "result_count": result.get("result_count", 0),
                "report_path": str(path),
            }
        )
        for rank, item in enumerate(result.get("results", []), start=1):
            video_id = str(item.get("video_id") or "")
            if not video_id:
                continue
            entry = videos.setdefault(video_id, {"video": item, "appearances": []})
            if not entry.get("video", {}).get("statistics") and item.get("statistics"):
                entry["video"] = item
            entry["appearances"].append(
                {
                    "keyword": keyword,
                    "observed_rank": rank,
                    "source": result.get("source", ""),
                }
            )

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


def run_market_research(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
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
    order: str = "relevance",
    published_after: str | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    """Run the integrated YouTube market research pipeline.

    order: "relevance"(기본) 또는 "date"(최신 등록일순).
    published_after: ISO 8601 UTC(예: "2026-08-01T00:00:00Z") 이후 등록된 영상만.
    """
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
        order=order,
        published_after=published_after,
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
        "order": order,
        "published_after": published_after or "",
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


def collect_public_comment_summary(
    video_id: str,
    *,
    max_results: int = 20,
    max_pages: int = 1,
    max_comments_total: int = 100,
    include_replies: bool = False,
    comment_collector: Any = None,
) -> dict[str, Any]:
    """Collect and summarize public top-level comments through official API only.

    공식 YouTube Data API 수집기는 두 도메인이 함께 쓰는 공용 잎(scripts/common/youtube_comments)에 있다.
    호출자가 ``comment_collector`` 를 주입하면 그것을 쓰고, 없으면 그 공용 수집기를 쓴다(실패하면 우아하게 차단 응답).
    """
    try:
        if comment_collector is None:
            comment_collector = collect_comments

        comments, report_path = comment_collector(
            video_id,
            max_results=max_results,
            max_pages=max_pages,
            max_comments_total=max_comments_total,
            include_replies=include_replies,
        )
    except Exception as exc:  # noqa: BLE001 - 유튜브 검색/댓글 수집 분석(읽기 전용) -- 키워드 검색·댓글 수집 실패 시 status=blocked로 처리(안전한 실패), 에러 메시지는 safe_preview로 200자 제한 축약해 민감정보 노출 방지
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


def _topic_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        topic = row.get("topic_classification", {}).get("primary_topic", "uncategorized")
        grouped.setdefault(topic, []).append(row)
    clusters = []
    for topic, items in grouped.items():
        clusters.append(
            {
                "topic": topic,
                "video_count": len(items),
                "average_opportunity_score": round(
                    sum(item["scores"]["topic_opportunity_score"] for item in items) / max(1, len(items)),
                    2,
                ),
                "top_video_ids": [item["video_id"] for item in items[:5]],
            }
        )
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
