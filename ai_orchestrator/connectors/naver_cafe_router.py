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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
_CAFE_DIR = ROOT / "data" / "cafe"

naver_cafe_router = APIRouter(
    prefix="/naver-cafe", tags=["naver-cafe"],
)


def _latest_file(pattern: str) -> Path | None:
    files = sorted(_CAFE_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


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
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"count={len(cafes)} duration_ms={duration_ms}",
    )
    return {"cafes": cafes, "count": len(cafes), "duration_ms": duration_ms}


@naver_cafe_router.get("/collected")
def api_collected(
    cafe_id: Optional[str] = None,
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
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"files={len(items)} duration_ms={duration_ms}",
    )
    return {"files": items, "count": len(items), "duration_ms": duration_ms}


@naver_cafe_router.get("/articles")
def api_articles(
    limit: int = 50,
    offset: int = 0,
    category: Optional[str] = None,
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
    page_items = articles[offset: offset + limit]
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_CAFE_ARTICLES_READ",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
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
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
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
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
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
        except Exception:
            pass

    raw_path = _latest_file("raw_articles_*.json")
    raw_count = 0
    raw_file = None
    if raw_path:
        try:
            raw_count = len(json.loads(raw_path.read_text(encoding="utf-8")))
            raw_file = raw_path.name
        except Exception:
            pass

    cls_path = _latest_file("classified_*.json")
    cls_count = 0
    cls_file = None
    if cls_path:
        try:
            cls_count = len(json.loads(cls_path.read_text(encoding="utf-8")))
            cls_file = cls_path.name
        except Exception:
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
