"""범용 커뮤니티 추출 엔드포인트 (/api/v1/community/*).

URL만 주면 게시글 목록을 구조화 추출(휴리스틱 → GPT 폴백). CDP 브라우저 사용.
- 쓰기 없음. 사용자가 제공한 URL만 조회.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

community_router = APIRouter(prefix="/community", tags=["community"])


def _ensure_path() -> None:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


class ExtractRequest(BaseModel):
    url: str
    max_posts: int = 50
    use_gpt: bool = True


@community_router.post("/extract")
def extract(req: ExtractRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """임의 커뮤니티 게시판 URL → 게시글 목록 추출(휴리스틱→GPT 폴백)."""
    url = (req.url or "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="http(s) URL 을 입력하세요")
    try:
        _ensure_path()
        from scripts.community.universal_extractor import extract_posts
        from scripts.web_connector import get_page

        page = get_page()
        result = extract_posts(
            page,
            url,
            max_posts=max(1, min(req.max_posts, 120)),
            use_gpt=bool(req.use_gpt),
        )
        log_event(
            "COMMUNITY_EXTRACT",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok" if result.get("ok") else "error",
            note=f"url={url[:40]} method={result.get('method')} n={result.get('count')}",
        )
        return result
    except Exception as e:
        logger.exception("community extract error")
        raise HTTPException(status_code=500, detail=f"추출 실패: {e}")
