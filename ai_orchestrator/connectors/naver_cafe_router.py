"""네이버 카페 read-only 조회 엔드포인트 (/api/v1/naver-cafe/*).

- 쓰기 API 없음. 모두 read-only.
- data/cafe/ 디렉터리에 저장된 수집·분류 결과 파일을 읽어 반환.
- 민감정보(쿠키/세션/경로 풀) 응답 금지.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

# parents[2] = repo 루트(소스) / _internal(frozen exe) — collector(_OUT_DIR)와 동일 기준
ROOT = Path(__file__).resolve().parents[2]
_CAFE_DIR = ROOT / "data" / "cafe"

naver_cafe_router = APIRouter(
    prefix="/naver-cafe",
    tags=["naver-cafe"],
)


def _latest_file(pattern: str) -> Path | None:
    files = sorted(_CAFE_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _ensure_path() -> None:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


# ── 수집 (CDP, 네이버 로그인 필요) ────────────────────────────────────────────


class CafeCollectRequest(BaseModel):
    cafe_url: str
    days: int = 90
    max_detail: int = 300


@naver_cafe_router.post("/collect-my-cafes")
def collect_my_cafes(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """내 가입 카페 목록을 CDP 로 수집해 저장."""
    try:
        _ensure_path()
        from scripts.naver.cafe.explorer import get_my_cafes, save_my_cafes
        from scripts.web_connector import get_page

        page = get_page()
        cafes = get_my_cafes(page)
        save_my_cafes(cafes)
        log_event(
            "NAVER_CAFE_COLLECT_MY_CAFES",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"count={len(cafes)}",
        )
        return {"ok": True, "count": len(cafes), "cafes": cafes}
    except Exception as e:
        logger.exception("collect my-cafes error")
        raise HTTPException(status_code=500, detail=f"카페 목록 수집 실패: {e}")


@naver_cafe_router.post("/collect")
def collect_cafe_articles(
    req: CafeCollectRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """선택한 카페의 게시글을 수집 + 분류 (CDP). 외부 발행 아님(읽기/수집)."""
    cafe_url = (req.cafe_url or "").strip()
    if not cafe_url.startswith("http"):
        raise HTTPException(status_code=400, detail="카페 URL 을 입력하세요")
    try:
        _ensure_path()
        from scripts.naver.cafe.collector import collect_articles
        from scripts.naver.cafe.organizer import organize
        from scripts.naver.cafe.pipeline import run_pipeline
        from scripts.web_connector import get_page

        page = get_page()
        articles = collect_articles(
            page,
            cafe_url=cafe_url,
            days=max(1, min(req.days, 365)),
            max_detail=max(1, min(req.max_detail, 500)),
        )
        run_pipeline()
        organize()
        log_event(
            "NAVER_CAFE_COLLECT",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"url={cafe_url[:40]} n={len(articles)}",
        )
        return {"ok": True, "collected": len(articles)}
    except Exception as e:
        logger.exception("collect cafe articles error")
        raise HTTPException(status_code=500, detail=f"게시글 수집 실패: {e}")


@naver_cafe_router.get("/my-cafes")
def api_my_cafes(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """내가 가입한 카페 목록 반환 (my_cafes.json)."""
    t0 = time.monotonic()
    path = _CAFE_DIR / "my_cafes.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="my_cafes.json 없음 — my-cafes 명령 먼저 실행")
    cafes = json.loads(path.read_text(encoding="utf-8"))
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_MY_CAFES_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(cafes)} duration_ms={duration_ms}",
    )
    return {"cafes": cafes, "count": len(cafes), "duration_ms": duration_ms}


@naver_cafe_router.get("/collected")
def api_collected(
    cafe_id: str | None = None,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """수집된 raw_articles 파일 목록 반환 (최근 10개)."""
    t0 = time.monotonic()
    pattern = f"{cafe_id}_raw_articles_*.json" if cafe_id else "raw_articles_*.json"
    files = sorted(_CAFE_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)[:10]
    items = [
        {
            "filename": f.name,
            "modified_at": f.stat().st_mtime,
            "size_kb": round(f.stat().st_size / 1024, 1),
        }
        for f in files
    ]
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_COLLECTED_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"files={len(items)} duration_ms={duration_ms}",
    )
    return {"files": items, "count": len(items), "duration_ms": duration_ms}


@naver_cafe_router.get("/articles")
def api_articles(
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """최신 classified 파일에서 게시글 목록 반환."""
    t0 = time.monotonic()
    path = _latest_file("classified_*.json")
    if not path:
        raise HTTPException(status_code=404, detail="classified 파일 없음 — collect-pipeline 먼저 실행")
    articles = json.loads(path.read_text(encoding="utf-8"))
    if category:
        articles = [a for a in articles if a.get("category") == category]
    total = len(articles)
    page_items = articles[offset : offset + limit]
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_ARTICLES_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"total={total} returned={len(page_items)} duration_ms={duration_ms}",
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "article_id": a.get("article_id"),
                "title": a.get("title"),
                "category": a.get("category"),
                "type": a.get("type"),
                "date": a.get("date"),
                "view_count": a.get("view_count"),
                "href": a.get("href"),
                "confidence": a.get("confidence"),
            }
            for a in page_items
        ],
        "source_file": path.name,
        "duration_ms": duration_ms,
    }


class CafeAnalyzeRequest(BaseModel):
    category: str | None = None  # 특정 분류만 분석(없으면 전체)
    days: int | None = None  # 최근 N일 글만(없으면 전체 수집분)
    max_posts: int = 400  # 분석에 넣을 최대 글 수(상한)


@naver_cafe_router.post("/ai-analyze")
def api_ai_analyze(
    body: CafeAnalyzeRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """수집·분류된 카페 글을 AI(커뮤니티 analyzer)로 분석 → 트렌드·수익기회 보고.

    - 입력: 최신 classified 파일(없으면 404).
    - 필터: category(분류) / days(최근 N일).
    - 출력: {summary, trends[], opportunities[], topics[], actions[]} + 메타.
    """
    t0 = time.monotonic()
    path = _latest_file("classified_*.json")
    if not path:
        raise HTTPException(status_code=404, detail="수집된 게시글이 없습니다 — 먼저 [게시글 수집]을 실행하세요")
    articles = json.loads(path.read_text(encoding="utf-8"))

    if body.category:
        articles = [a for a in articles if a.get("category") == body.category]
    if body.days and body.days > 0:
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=body.days)).strftime("%Y-%m-%d")
        articles = [a for a in articles if str(a.get("date", "")) >= cutoff]

    if not articles:
        raise HTTPException(status_code=404, detail="조건에 맞는 게시글이 없습니다 (분류/기간 확인)")

    # 전체 수집분을 대표하도록 조회수 상위로 샘플링(관심 높은 글이 흐름을 잘 보여줌).
    def _views(a: dict) -> int:
        try:
            return int(str(a.get("view_count", "0")).replace(",", "") or 0)
        except (ValueError, TypeError):
            return 0

    articles_sorted = sorted(articles, key=_views, reverse=True)
    cap = max(1, min(body.max_posts, 600))

    # analyzer 입력 매핑(title/views/comments/date)
    posts = [
        {
            "title": a.get("title", ""),
            "views": a.get("view_count", ""),
            "comments": a.get("comment_count", ""),
            "date": a.get("date", ""),
        }
        for a in articles_sorted
    ][:cap]
    total_collected = len(articles)

    _ensure_path()
    from scripts.community.analyzer import analyze_posts

    ctx = "네이버 카페 수집글"
    if body.category:
        ctx += f" · 분류={body.category}"
    report = analyze_posts(posts, context=ctx)
    if not report.get("ok"):
        raise HTTPException(status_code=502, detail=f"AI 분석 실패: {report.get('error', '알 수 없음')}")

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_AI_ANALYZE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"posts={len(posts)} cat={body.category or '-'} days={body.days or '-'} duration_ms={duration_ms}",
    )
    return {
        **report,
        "source_file": path.name,
        "post_count": len(posts),
        "total_collected": total_collected,
        "category": body.category,
        "days": body.days,
        "duration_ms": duration_ms,
    }


@naver_cafe_router.get("/kb")
def api_kb(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """최신 organized_kb JSON 반환 (카테고리별 구조화 데이터)."""
    t0 = time.monotonic()
    path = _latest_file("organized_kb_*.json")
    if not path:
        raise HTTPException(status_code=404, detail="organized_kb 파일 없음 — organize 먼저 실행")
    kb = json.loads(path.read_text(encoding="utf-8"))
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_KB_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"categories={len(kb.get('categories', []))} duration_ms={duration_ms}",
    )
    return {**kb, "source_file": path.name, "duration_ms": duration_ms}


@naver_cafe_router.get("/report")
def api_report(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """최신 organized_report 텍스트 반환."""
    t0 = time.monotonic()
    path = _latest_file("organized_report_*.txt")
    if not path:
        raise HTTPException(status_code=404, detail="report 파일 없음 — organize 먼저 실행")
    text = path.read_text(encoding="utf-8")
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_REPORT_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"chars={len(text)} duration_ms={duration_ms}",
    )
    return {"report": text, "source_file": path.name, "duration_ms": duration_ms}


@naver_cafe_router.get("/summary")
def api_summary(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """카페 수집 현황 요약 (파일 존재 여부 + 건수)."""
    t0 = time.monotonic()

    my_cafes_path = _CAFE_DIR / "my_cafes.json"
    my_cafes_count = 0
    if my_cafes_path.exists():
        try:
            my_cafes_count = len(json.loads(my_cafes_path.read_text(encoding="utf-8")))
        except Exception:  # noqa: S110
            pass

    raw_path = _latest_file("raw_articles_*.json")
    raw_count = 0
    raw_file = None
    if raw_path:
        try:
            raw_count = len(json.loads(raw_path.read_text(encoding="utf-8")))
            raw_file = raw_path.name
        except Exception:  # noqa: S110
            pass

    cls_path = _latest_file("classified_*.json")
    cls_count = 0
    cls_file = None
    if cls_path:
        try:
            cls_count = len(json.loads(cls_path.read_text(encoding="utf-8")))
            cls_file = cls_path.name
        except Exception:  # noqa: S110
            pass

    report_path = _latest_file("organized_report_*.txt")

    duration_ms = int((time.monotonic() - t0) * 1000)
    return {
        "my_cafes_count": my_cafes_count,
        "latest_raw_file": raw_file,
        "latest_raw_count": raw_count,
        "latest_classified_file": cls_file,
        "latest_classified_count": cls_count,
        "has_report": report_path is not None,
        "latest_report_file": report_path.name if report_path else None,
        "duration_ms": duration_ms,
    }
