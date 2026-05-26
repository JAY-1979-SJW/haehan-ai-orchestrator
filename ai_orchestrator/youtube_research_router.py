"""Read-only YouTube research API routes."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from scripts.youtube import research

from .audit_logger import log_event
from .auth import require_role

youtube_research_router = APIRouter(prefix="/youtube/research", tags=["youtube-research"])


class YouTubeContextAnalysisRequest(BaseModel):
    video_info: dict[str, Any] = {}
    comments: dict[str, Any] = {}
    transcript_text: str = ""
    topic: str = ""


def _duration_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _audit(event: str, user: dict, *, status: str, note: str = "") -> None:
    log_event(
        event,
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision=status,
        note=note[:300],
    )


@youtube_research_router.get("/status")
def get_youtube_research_status(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """Return the locked YouTube research capability map."""
    from scripts.youtube.router import __status__

    _audit("YOUTUBE_RESEARCH_STATUS_READ", user, status="ok")
    return {
        "ok": True,
        "status": "ok",
        "read_only": True,
        "state_change": False,
        "secret_values_output": False,
        "capabilities": __status__["tasks"],
    }


@youtube_research_router.get("/search")
def search_youtube_videos(
    query: str,
    max_results: int = 5,
    captions_only: bool = False,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Search public YouTube videos through the official API."""
    t0 = time.monotonic()
    result, path = research.search_videos(query, max_results=max_results, captions_only=captions_only)
    result["report_path"] = str(path)
    result["duration_ms"] = _duration_ms(t0)
    _audit(
        "YOUTUBE_RESEARCH_SEARCH_READ",
        user,
        status=result.get("status", "unknown"),
        note=f"query={query[:80]} count={result.get('result_count', 0)}",
    )
    return result


@youtube_research_router.get("/video-info")
def get_youtube_video_info(
    video_id: str,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Collect public YouTube video metadata through the official API."""
    t0 = time.monotonic()
    result, path = research.collect_video_info(video_id)
    result["report_path"] = str(path)
    result["duration_ms"] = _duration_ms(t0)
    _audit("YOUTUBE_VIDEO_INFO_READ", user, status=result.get("status", "unknown"), note=f"video_id={video_id[:80]}")
    return result


@youtube_research_router.get("/comments")
def get_youtube_comments(
    video_id: str,
    max_results: int = 20,
    order: str = "relevance",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Collect public top-level comments through the official API."""
    t0 = time.monotonic()
    result, path = research.collect_comments(video_id, max_results=max_results, order=order)
    result["report_path"] = str(path)
    result["duration_ms"] = _duration_ms(t0)
    _audit(
        "YOUTUBE_COMMENTS_READ",
        user,
        status=result.get("status", "unknown"),
        note=f"video_id={video_id[:80]} count={result.get('comment_count', 0)}",
    )
    return result


@youtube_research_router.get("/transcript-plan")
def get_youtube_transcript_plan(
    video_id: str,
    owned: bool = False,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Build the compliant transcript collection plan for a video."""
    t0 = time.monotonic()
    result, path = research.build_transcript_collection_plan(video_id, owned=owned)
    result["report_path"] = str(path)
    result["duration_ms"] = _duration_ms(t0)
    _audit("YOUTUBE_TRANSCRIPT_PLAN_READ", user, status=result.get("status", "unknown"), note=f"video_id={video_id[:80]}")
    return result


@youtube_research_router.post("/context-report")
def build_youtube_context_report(
    body: YouTubeContextAnalysisRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Analyze collected video metadata, comments, and optional transcript text."""
    t0 = time.monotonic()
    context, context_path = research.analyze_video_context(
        video_info=body.video_info,
        comments=body.comments,
        transcript_text=body.transcript_text,
    )
    scorecard, scorecard_path = research.build_video_strategy_scorecard(
        video_info=body.video_info,
        comments=body.comments,
        transcript_text=body.transcript_text,
        channel_topic=body.topic,
    )
    result = {
        "ok": True,
        "status": "ok",
        "read_only": True,
        "state_change": False,
        "secret_values_output": False,
        "context": context,
        "scorecard": scorecard,
        "report_paths": {
            "context": str(context_path),
            "scorecard": str(scorecard_path),
        },
        "duration_ms": _duration_ms(t0),
    }
    _audit(
        "YOUTUBE_CONTEXT_REPORT_BUILT",
        user,
        status="ok",
        note=f"comments={context['source_counts']['comments']} topic={body.topic[:80]}",
    )
    return result


__all__ = ["youtube_research_router"]
