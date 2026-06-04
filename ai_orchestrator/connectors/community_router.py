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


class SiteAddRequest(BaseModel):
    url: str
    name: str = ""
    note: str = ""


class AnalyzeRequest(BaseModel):
    url: str = ""
    posts: list[dict] = []
    max_posts: int = 50
    context: str = ""


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


# ── 사이트 레지스트리 ────────────────────────────────────────────────────────


@community_router.get("/sites")
def list_sites(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """등록된 모니터링 사이트 목록."""
    _ensure_path()
    from scripts.community.registry import list_sites as _ls

    sites = _ls()
    return {"ok": True, "sites": sites, "count": len(sites)}


@community_router.post("/sites")
def add_site(req: SiteAddRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """모니터링 사이트 등록."""
    _ensure_path()
    from scripts.community.registry import add_site as _add

    try:
        site = _add(req.url, req.name, req.note)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    log_event(
        "COMMUNITY_SITE_ADD",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"url={req.url[:40]}",
    )
    return {"ok": True, "site": site}


@community_router.delete("/sites/{site_id}")
def remove_site(site_id: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """모니터링 사이트 삭제."""
    _ensure_path()
    from scripts.community.registry import remove_site as _rm

    ok = _rm(site_id)
    return {"ok": ok}


# ── AI 트렌드·수익 분석 ──────────────────────────────────────────────────────


@community_router.post("/analyze")
def analyze(req: AnalyzeRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """URL 추출 또는 제공된 게시글 → AI 트렌드·수익 분석."""
    _ensure_path()
    from scripts.community.analyzer import analyze_posts

    posts = req.posts or []
    context = req.context or ""
    method = "provided"

    # url 이 있으면 먼저 추출
    if req.url:
        try:
            from scripts.community.universal_extractor import extract_posts
            from scripts.web_connector import get_page

            page = get_page()
            ex = extract_posts(page, req.url.strip(), max_posts=max(1, min(req.max_posts, 120)))
            if not ex.get("ok"):
                raise HTTPException(status_code=502, detail=ex.get("error") or "추출 실패")
            posts = ex.get("posts", [])
            method = ex.get("method", "extract")
            context = context or req.url
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("analyze extract error")
            raise HTTPException(status_code=500, detail=f"추출 실패: {e}")

    if not posts:
        raise HTTPException(status_code=400, detail="분석할 게시글(url 또는 posts)이 필요합니다")

    try:
        report = analyze_posts(posts, context=context)
    except Exception as e:
        logger.exception("analyze error")
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}")

    log_event(
        "COMMUNITY_ANALYZE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if report.get("ok") else "error",
        note=f"method={method} posts={len(posts)}",
    )
    return {**report, "source_method": method, "posts": posts[:50]}
