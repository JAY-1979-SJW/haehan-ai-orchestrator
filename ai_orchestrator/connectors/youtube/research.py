"""YouTube 리서치 라우트 (읽기 전용)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from scripts.youtube import research as _research_svc
from tools.gates.auth import require_role

from ._helpers import audit, duration_ms

router = APIRouter()


class ContextAnalysisRequest(BaseModel):
    video_info: dict[str, Any] = {}
    comments: dict[str, Any] = {}
    transcript_text: str = ""
    topic: str = ""


@router.get("/status")
def get_research_status(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """YouTube 리서치 기능 맵 반환."""
    from scripts.youtube.router import __status__

    audit("YOUTUBE_RESEARCH_STATUS_READ", user, status="ok")
    return {
        "ok": True,
        "status": "ok",
        "read_only": True,
        "state_change": False,
        "secret_values_output": False,
        "capabilities": __status__["tasks"],
    }


@router.get("/search")
def search_videos(
    query: str,
    max_results: int = 5,
    captions_only: bool = False,
    order: str = "relevance",
    published_after: str = "",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """공식 API로 YouTube 영상 검색.

    order: relevance(기본) 또는 date(최신 등록일순).
    published_after: ISO 8601 UTC (예: 2026-08-01T00:00:00Z) 이후 등록된 영상만.
    """
    import urllib.error

    from fastapi import HTTPException

    t0 = time.monotonic()
    try:
        result, path = _research_svc.search_videos(
            query,
            max_results=max_results,
            captions_only=captions_only,
            order=order,
            published_after=published_after or None,
        )
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise HTTPException(
                status_code=429, detail="YouTube API 일일 할당량 초과(429). 내일 재시도하거나 다른 API 키를 사용하세요."
            ) from e
        raise HTTPException(status_code=502, detail=f"YouTube API 오류: HTTP {e.code}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube 검색 오류: {type(e).__name__}: {str(e)[:200]}") from e
    result["report_path"] = str(path)
    result["duration_ms"] = duration_ms(t0)
    audit(
        "YOUTUBE_RESEARCH_SEARCH_READ",
        user,
        status=result.get("status", "unknown"),
        note=f"query={query[:80]} count={result.get('result_count', 0)}",
    )
    return result


@router.get("/video-info")
def get_video_info(
    video_id: str,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """공식 API로 YouTube 영상 메타데이터 수집."""
    t0 = time.monotonic()
    result, path = _research_svc.collect_video_info(video_id)
    result["report_path"] = str(path)
    result["duration_ms"] = duration_ms(t0)
    audit("YOUTUBE_VIDEO_INFO_READ", user, status=result.get("status", "unknown"), note=f"video_id={video_id[:80]}")
    return result


@router.get("/comments")
def get_comments(
    video_id: str,
    max_results: int = 20,
    order: str = "relevance",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """공식 API로 공개 최상위 댓글 수집."""
    t0 = time.monotonic()
    result, path = _research_svc.collect_comments(video_id, max_results=max_results, order=order)
    result["report_path"] = str(path)
    result["duration_ms"] = duration_ms(t0)
    audit(
        "YOUTUBE_COMMENTS_READ",
        user,
        status=result.get("status", "unknown"),
        note=f"video_id={video_id[:80]} count={result.get('comment_count', 0)}",
    )
    return result


@router.get("/transcript-plan")
def get_transcript_plan(
    video_id: str,
    owned: bool = False,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """영상 자막 수집 플랜 생성."""
    t0 = time.monotonic()
    result, path = _research_svc.build_transcript_collection_plan(video_id, owned=owned)
    result["report_path"] = str(path)
    result["duration_ms"] = duration_ms(t0)
    audit(
        "YOUTUBE_TRANSCRIPT_PLAN_READ", user, status=result.get("status", "unknown"), note=f"video_id={video_id[:80]}"
    )
    return result


@router.post("/context-report")
def build_context_report(
    body: ContextAnalysisRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """영상 메타데이터·댓글·자막을 통합 분석."""
    t0 = time.monotonic()
    context, context_path = _research_svc.analyze_video_context(
        video_info=body.video_info,
        comments=body.comments,
        transcript_text=body.transcript_text,
    )
    scorecard, scorecard_path = _research_svc.build_video_strategy_scorecard(
        video_info=body.video_info,
        comments=body.comments,
        transcript_text=body.transcript_text,
        channel_topic=body.topic,
    )
    audit(
        "YOUTUBE_CONTEXT_REPORT_BUILT",
        user,
        status="ok",
        note=f"comments={context['source_counts']['comments']} topic={body.topic[:80]}",
    )
    return {
        "ok": True,
        "status": "ok",
        "read_only": True,
        "state_change": False,
        "secret_values_output": False,
        "context": context,
        "scorecard": scorecard,
        "report_paths": {"context": str(context_path), "scorecard": str(scorecard_path)},
        "duration_ms": duration_ms(t0),
    }
