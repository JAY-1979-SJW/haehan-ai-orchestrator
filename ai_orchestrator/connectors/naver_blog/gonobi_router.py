"""gonobi 블로그 수집 API (L8 Server API).

POST /api/v1/gonobi/scrape          수집 시작 (백그라운드)
GET  /api/v1/gonobi/scrape/status   수집 진행 상황
GET  /api/v1/gonobi/posts           수집된 포스트 목록
GET  /api/v1/gonobi/posts/{log_no}  포스트 상세
GET  /api/v1/gonobi/stats           DB 통계
POST /api/v1/gonobi/classify        미분류 포스트 AI 재분류
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

gonobi_router = APIRouter(prefix="/gonobi", tags=["gonobi"])

# 수집 상태 공유 (단일 프로세스 내)
_scrape_state: dict = {"running": False, "total": 0, "new": 0, "errors": 0, "current": ""}


@gonobi_router.post("/scrape")
async def start_scrape(delay: float = 0.8):
    """gonobi 블로그 전체 수집 시작 (백그라운드)."""
    if _scrape_state["running"]:
        return {"status": "already_running", "state": _scrape_state}

    _scrape_state.update({"running": True, "total": 0, "new": 0, "errors": 0, "current": ""})

    def _progress(cat_idx, total_cats, cat_name, log_no, title):
        _scrape_state["current"] = f"[{cat_idx}/{total_cats}] {cat_name} - {title[:30]}"
        _scrape_state["total"] = _scrape_state.get("total", 0) + 1

    async def _run():
        try:
            from scripts.naver.blog.gonobi.runner import run_scrape

            result = await asyncio.to_thread(run_scrape, delay=delay, progress_cb=_progress)
            _scrape_state.update(
                {
                    "running": False,
                    "total": result.total,
                    "new": result.new,
                    "errors": result.errors,
                    "by_category": result.by_category,
                    "current": "완료",
                }
            )
        except Exception as e:  # noqa: BLE001 - gonobi 블로그 수집 FastAPI 라우터 - 예외를 HTTPException 500으로 변환(내부 오류 메시지 포함), DB 읽기 API로 쓰기/삭제 없음
            logger.error("gonobi 수집 오류: %s", e)
            _scrape_state.update({"running": False, "current": f"오류: {e}"})

    task = asyncio.create_task(_run())
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return {"status": "started", "message": "백그라운드 수집 시작됨"}


@gonobi_router.get("/scrape/status")
async def scrape_status():
    """수집 진행 상황."""
    return _scrape_state


@gonobi_router.get("/posts")
async def list_posts(
    category: str | None = Query(None, description="our_category 필터"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """수집된 포스트 목록."""
    try:
        from scripts.naver.blog.gonobi.db import get_posts, open_db

        with open_db() as conn:
            posts = get_posts(conn, our_category=category or "", limit=limit, offset=offset)
        return {"posts": posts, "count": len(posts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@gonobi_router.get("/posts/{log_no}")
async def get_post_detail(log_no: str):
    """포스트 상세 (본문 + 이미지)."""
    try:
        from scripts.naver.blog.gonobi.db import get_post, open_db

        with open_db() as conn:
            post = get_post(conn, log_no)
        if not post:
            raise HTTPException(status_code=404, detail="포스트 없음")
        return post
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@gonobi_router.get("/stats")
async def get_stats():
    """DB 통계."""
    try:
        from scripts.naver.blog.gonobi.db import count_posts, open_db

        with open_db() as conn:
            stats = count_posts(conn)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@gonobi_router.post("/classify")
async def reclassify(limit: int = Query(100, description="재분류할 미분류 포스트 수")):
    """our_category가 비어있는 포스트 키워드 재분류."""
    try:
        from scripts.naver.blog.gonobi.db import open_db, reclassify_untagged

        with open_db() as conn:
            updated = reclassify_untagged(conn, limit=limit)
        return {"updated": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
