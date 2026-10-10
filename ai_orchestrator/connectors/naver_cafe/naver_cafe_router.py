"""네이버 카페 엔드포인트 (/api/v1/naver-cafe/*).

- read-only 조회 + 수집·발행(글쓰기 포함, Claude Code/MCP가 도구를 직접 호출)
- 민감정보(쿠키/세션/경로 풀) 응답 금지.
- GPT 채팅 루프(/chat)는 삭제됨.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.connectors.naver_cafe import membership_service as cafe_membership_service
from ai_orchestrator.paths import repo_root
from ai_orchestrator.paths.runtime import data_dir
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

# parents[2] = repo 루트(소스) / _internal(frozen exe) — collector(_OUT_DIR)와 동일 기준
ROOT = repo_root()
_CAFE_DIR = data_dir() / "cafe"

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
    keyword: str = ""


@naver_cafe_router.post("/collect-my-cafes")
def collect_my_cafes(confirm_mass_change: bool = False, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """내 가입 카페 목록을 CDP 로 수집하고 이전 이력과 비교해 신규 가입·탈퇴를 반영한다.

    작업 탭 하나만 쓰고 끝나면 닫는다. 빈 결과·화면 읽기 대체·중복·대량 감소는 비교하지 않고 경고만 낸다(저장본을 덮어쓰지 않는다).
    `confirm_mass_change=true` 는 절반 이상 줄어든 결과를 사람이 확인하고 반영할 때만 쓴다.
    """
    try:
        _ensure_path()
        from scripts.browser.cdp.connection import close_page, get_context, run_on_browser_thread
        from scripts.naver.cafe.collection.explorer import get_my_cafes_with_source, save_my_cafes

        def collect() -> tuple[list[dict], str]:
            # 자기 탭을 직접 만들어 쓰고 닫는다. browser_task_session 은 컨텍스트의 아무 빈 탭을 골라 재사용하므로(2026-10-05 실측:
            # 사라지는 탭에서 `Frame has been detached`, 다른 작업·사용자의 빈 탭을 가로챌 위험) 쓰지 않는다.
            page = get_context().new_page()
            try:
                return get_my_cafes_with_source(page)
            finally:
                with contextlib.suppress(Exception):
                    close_page(page)  # 작업 탭을 남기지 않는다(사용자 탭 불간섭)

        # CDP page 조작은 반드시 브라우저 전용 스레드에서 실행(playwright sync 스레드 경계).
        cafes, source = run_on_browser_thread(collect, timeout=120)
        outcome = cafe_membership_service.apply_collection(
            cafes, source=source, confirm_mass_change=confirm_mass_change
        )
        changes = outcome["changes"]
        if outcome["persist_current"]:
            save_my_cafes(cafes)  # 보호 규칙에 걸린 수집은 현재 목록 파일도 덮어쓰지 않는다
        log_event(
            "NAVER_CAFE_COLLECT_MY_CAFES",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok" if changes["status"] in ("baseline", "ok") else changes["status"],
            note=f"count={len(cafes)} source={source} status={changes['status']} new={len(changes['new'])} left={len(changes['left'])}",
        )
        return {
            "ok": True,
            "count": len(cafes),
            "cafes": cafes,
            "source": source,
            "changes": changes,
            "activity": outcome["activity"],
        }
    except Exception as e:
        logger.exception("collect my-cafes error")
        raise HTTPException(status_code=500, detail=f"카페 목록 수집 실패: {e}") from e


@naver_cafe_router.get("/my-cafes/changes")
def api_my_cafes_changes(limit: int = 20, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """가입 카페 신규 가입·탈퇴 변동 기록과 가입 수 추이(읽기 전용)."""
    out = cafe_membership_service.recent(limit)
    log_event(
        "NAVER_CAFE_MY_CAFES_CHANGES_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"changes={len(out['changes'])}",
    )
    return out


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
        from scripts.browser.cdp.connection import get_page, run_on_browser_thread
        from scripts.naver.cafe.collector import collect_articles
        from scripts.naver.cafe.organizer import organize
        from scripts.naver.cafe.pipeline import run_pipeline

        # CDP page 조작은 반드시 브라우저 전용 스레드에서 실행(playwright sync 스레드 경계).
        articles = run_on_browser_thread(
            lambda: collect_articles(
                get_page(),
                cafe_url=cafe_url,
                days=max(1, min(req.days, 365)),
                max_detail=max(1, min(req.max_detail, 500)),
                keyword=req.keyword.strip(),
            ),
            timeout=300,
        )
        run_pipeline()
        organize()
        log_event(
            "NAVER_CAFE_COLLECT",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"url={cafe_url[:40]} n={len(articles)} keyword={req.keyword[:20] or '-'}",
        )
        return {"ok": True, "collected": len(articles)}
    except Exception as e:
        logger.exception("collect cafe articles error")
        raise HTTPException(status_code=500, detail=f"게시글 수집 실패: {e}") from e


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
        raise HTTPException(
            status_code=404,
            detail="수집된 게시글이 없습니다 — 먼저 [게시글 수집]을 실행하세요",
        )
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
    from scripts.community.analyzer import prepare_posts_for_review

    ctx = "네이버 카페 수집글"
    if body.category:
        ctx += f" · 분류={body.category}"
    report = prepare_posts_for_review(posts, context=ctx)
    if not report.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"분석 준비 실패: {report.get('error', '알 수 없음')}",
        )

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
        # 하위호환: 프론트엔드가 읽는 옛 필드는 빈 값으로 유지(UI 크래시 방지)
        "summary": "",
        "trends": [],
        "topics": [],
        "opportunities": [],
        "actions": [],
        **report,
        "analysis_mode": "claude_review",
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
    _: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """카페 수집 현황 요약 (파일 존재 여부 + 건수)."""
    t0 = time.monotonic()

    my_cafes_path = _CAFE_DIR / "my_cafes.json"
    my_cafes_count = 0
    if my_cafes_path.exists():
        with contextlib.suppress(Exception):
            my_cafes_count = len(json.loads(my_cafes_path.read_text(encoding="utf-8")))

    raw_path = _latest_file("raw_articles_*.json")
    raw_count = 0
    raw_file = None
    if raw_path:
        try:
            raw_count = len(json.loads(raw_path.read_text(encoding="utf-8")))
            raw_file = raw_path.name
        except Exception as exc:  # noqa: BLE001
            logger.debug("카페 raw 건수 파일 읽기 실패(무시): %s", type(exc).__name__)
            pass

    cls_path = _latest_file("classified_*.json")
    cls_count = 0
    cls_file = None
    if cls_path:
        try:
            cls_count = len(json.loads(cls_path.read_text(encoding="utf-8")))
            cls_file = cls_path.name
        except Exception as exc:  # noqa: BLE001
            logger.debug("카페 분류 건수 파일 읽기 실패(무시): %s", type(exc).__name__)
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


# ── 카페 → 해한Ai 홈페이지 블로그 자동화 ─────────────────────────────────────


class CafeToHaehanBlogRequest(BaseModel):
    max_topics: int = 3  # 생성할 블로그 포스트 수 (최대 10)
    days: int | None = None  # 최근 N일 게시글만 분석 (없으면 전체)
    category: str | None = None  # 특정 카페 분류만 분석 (없으면 전체)
    status: str = "draft"  # "draft" | "published"


def _pick_blog_topics(articles: list[dict]) -> list[str]:
    """무료 결정론 규칙: 조회수 상위 제목을 중복 제거해 그대로 후보로 사용."""

    def _views(a: dict) -> int:
        try:
            return int(str(a.get("view_count", "0")).replace(",", "") or 0)
        except (ValueError, TypeError):
            return 0

    top_articles = sorted(articles, key=_views, reverse=True)[:200]

    seen_norm: set[str] = set()
    raw_topics: list[str] = []
    for a in top_articles:
        title = (a.get("title") or "").strip()
        if len(title) < 6:
            continue
        norm = " ".join(title.lower().split())
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        raw_topics.append(title)
    return raw_topics


def _generate_and_save_post(topic: str, haehan_url: str, headers_common: dict, post_status: str) -> dict:
    """주제 1개를 blog-generate 로 생성하고 /api/admin/blog 에 저장. 결과 item dict 반환."""
    import urllib.error
    import urllib.request

    item: dict = {"topic": topic, "generate": None, "save": None, "error": None}
    try:
        # 3. blog-generate 호출 (Claude + Unsplash)
        gen_payload = json.dumps({"topic": topic}, ensure_ascii=False).encode()
        gen_req = urllib.request.Request(  # noqa: S310
            f"{haehan_url}/api/admin/blog-generate",
            data=gen_payload,
            headers=headers_common,
            method="POST",
        )
        with urllib.request.urlopen(gen_req, timeout=60) as resp:  # noqa: S310
            generated = json.loads(resp.read().decode())
        item["generate"] = {
            "ok": True,
            "title": generated.get("title"),
            "slug": generated.get("slug"),
        }

        # 4. blog 저장
        save_payload = json.dumps(
            {
                "slug": generated["slug"],
                "title": generated["title"],
                "summary": generated["summary"],
                "category": generated["category"],
                "published_at": generated.get("publishedAt"),
                "status": post_status,
                "featured": False,
                "thumbnail": generated.get("thumbnail"),
                "thumbnail_credit": generated.get("thumbnailCredit"),
                "thumbnail_credit_url": generated.get("thumbnailCreditUrl"),
                "tags": generated.get("tags", []),
                "content": generated.get("content", []),
            },
            ensure_ascii=False,
        ).encode()
        save_req = urllib.request.Request(  # noqa: S310
            f"{haehan_url}/api/admin/blog",
            data=save_payload,
            headers=headers_common,
            method="POST",
        )
        with urllib.request.urlopen(save_req, timeout=30) as resp:  # noqa: S310
            saved = json.loads(resp.read().decode())
        item["save"] = {
            "ok": True,
            "id": saved.get("post", {}).get("id"),
            "status": post_status,
        }

    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")[:200]
        item["error"] = f"HTTP {e.code}: {body_text}"
    except Exception as exc:  # noqa: BLE001 - 네이버 카페 수집 FastAPI 라우터 - 예외를 HTTPException 500으로 변환, 파일 통계 읽기 실패는 무시, 쓰기/삭제 없음
        item["error"] = str(exc)[:200]
    return item


@naver_cafe_router.post("/cafe-to-haehan-blog")
def cafe_to_haehan_blog(
    body: CafeToHaehanBlogRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 카페 수집 데이터 → AI 주제 추출 → 해한Ai 홈페이지 블로그 자동 생성·저장.

    1. 최신 classified 파일에서 조회수 상위 게시글 읽기
    2. AI로 인기 질문/주제 N개 추출
    3. 각 주제를 해한Ai /api/admin/blog-generate 에 전송 (Claude + Unsplash)
    4. 생성된 포스트를 /api/admin/blog 에 저장 (draft 또는 published)
    """
    t0 = time.monotonic()

    # ── 환경 변수 ──────────────────────────────────────────────────────────────
    haehan_url = os.environ.get("HAEHAN_BLOG_URL", "https://haehan-ai.kr").rstrip("/")
    admin_secret = os.environ.get("HAEHAN_ADMIN_SECRET", "")
    if not admin_secret:
        raise HTTPException(status_code=500, detail="HAEHAN_ADMIN_SECRET 환경변수가 설정되지 않았습니다")

    max_topics = max(1, min(body.max_topics, 10))
    valid_statuses = {"draft", "published"}
    post_status = body.status if body.status in valid_statuses else "draft"

    # ── 1. 카페 게시글 로드 ────────────────────────────────────────────────────
    path = _latest_file("classified_*.json")
    if not path:
        raise HTTPException(
            status_code=404,
            detail="수집된 게시글이 없습니다 — 먼저 [게시글 수집]을 실행하세요",
        )

    articles = json.loads(path.read_text(encoding="utf-8"))

    if body.category:
        articles = [a for a in articles if a.get("category") == body.category]
    if body.days and body.days > 0:
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=body.days)).strftime("%Y-%m-%d")
        articles = [a for a in articles if str(a.get("date", "")) >= cutoff]

    if not articles:
        raise HTTPException(status_code=404, detail="조건에 맞는 게시글이 없습니다")

    raw_topics = _pick_blog_topics(articles)

    topics = raw_topics[:max_topics]
    if not topics:
        raise HTTPException(
            status_code=502,
            detail="블로그 주제로 쓸 만한 제목을 찾지 못했습니다 — 조건에 맞는 게시글 제목이 없음",
        )

    # ── 3 & 4. 주제별 블로그 생성 → 홈페이지 DB 저장 ─────────────────────────
    headers_common = {
        "Content-Type": "application/json",
        "x-admin-key": admin_secret,
    }

    results = [_generate_and_save_post(topic, haehan_url, headers_common, post_status) for topic in topics]

    success = [r for r in results if r["error"] is None]
    failed = [r for r in results if r["error"] is not None]

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "CAFE_TO_HAEHAN_BLOG",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"topics={len(topics)} success={len(success)} failed={len(failed)} status={post_status} duration_ms={duration_ms}",
    )
    return {
        "ok": len(success) > 0,
        "topics_requested": len(topics),
        "success_count": len(success),
        "failed_count": len(failed),
        "status": post_status,
        "results": results,
        "source_file": path.name,
        "duration_ms": duration_ms,
    }
