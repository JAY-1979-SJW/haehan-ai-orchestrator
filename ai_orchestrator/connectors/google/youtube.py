"""Google/YouTube 시장조사 엔드포인트.

자유 주제(검색어)로 유튜브 인기 영상·키워드·시청자 반응을 조사한다.
실제 수집 로직은 scripts/google/youtube 에 위임. 패키지 앱에서도 동작하도록
Next API 의 python execFile 대신 서버(번들 Python+CDP)가 직접 실행한다.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event

logger = logging.getLogger(__name__)
router = APIRouter()

_ROOT = Path(__file__).resolve().parents[3]


class MarketResearchRequest(BaseModel):
    topic: str
    per_keyword_limit: int = 8
    max_comments: int = 50
    max_comment_pages: int = 3
    collect_comments: bool = True
    order: str = "relevance"  # "relevance" 또는 "date"(최신 등록일순)
    published_after: str = ""  # ISO 8601 UTC, 예: "2026-08-01T00:00:00Z"


@router.post("/market-research")
def youtube_market_research(
    req: MarketResearchRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """자유 주제로 유튜브 시장조사 실행 후 결과 payload 반환."""
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="주제(검색어)를 입력하세요")
    try:
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))
        from scripts.google.youtube import market_research_run

        payload, _meta, _state = market_research_run(
            topic=topic,
            auto_keywords=True,
            per_keyword_limit=max(1, min(req.per_keyword_limit, 15)),
            collect_comments=req.collect_comments,
            max_comments=max(1, min(req.max_comments, 100)),
            max_comment_pages=max(1, min(req.max_comment_pages, 5)),
            collect_transcripts=False,
            order=req.order if req.order in {"relevance", "date"} else "relevance",
            published_after=req.published_after or None,
        )
        log_event(
            "YOUTUBE_MARKET_RESEARCH",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"topic={topic[:30]} videos={len((payload or {}).get('top_videos', []))}",
        )
        return {"ok": True, "data": payload}
    except Exception as e:
        logger.exception("youtube market research error")
        raise HTTPException(status_code=500, detail=f"시장조사 실패: {e}") from e
