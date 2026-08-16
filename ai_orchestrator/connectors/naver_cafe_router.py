"""네이버 카페 엔드포인트 (/api/v1/naver-cafe/*).

- read-only 조회 + AI 채팅(글쓰기 포함)
- 민감정보(쿠키/세션/경로 풀) 응답 금지.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..app_llm import APP_LLM_MODEL
from ..audit_logger import log_event
from ..auth import require_role
from .tool_registry import register, to_openai_tools

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
    keyword: str = ""


@naver_cafe_router.post("/collect-my-cafes")
def collect_my_cafes(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """내 가입 카페 목록을 CDP 로 수집해 저장."""
    try:
        _ensure_path()
        from scripts.naver.cafe.collection.explorer import get_my_cafes, save_my_cafes
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 반드시 브라우저 전용 스레드에서 실행(playwright sync 스레드 경계).
        cafes = run_on_browser_thread(lambda: get_my_cafes(get_page()), timeout=120)
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
        from scripts.web_connector import get_page, run_on_browser_thread

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


# ── 채팅 ─────────────────────────────────────────────────────────────────────

_CAFE_SYSTEM_PROMPT = """당신은 네이버 카페 AI 에이전트입니다.
사용자의 자연어 명령을 이해하고 적절한 도구를 즉시 호출하세요.
- 수집(collect_cafe_posts)·조회(get_cafe_summary)는 묻지 말고 즉시 실행합니다.
- 글 발행(write_cafe_post)은 내용을 먼저 보여주고 '발행할까요?' 한 번만 확인합니다.
- '진행할까요?', '실행해도 될까요?' 등의 질문은 절대 하지 않습니다.
- 결과는 한국어로 간결하게 요약합니다."""

_CAFE_WRITE_TOOLS = {"write_cafe_post"}
_CDP = "http://127.0.0.1:9222"


def _cafe_tool_defs() -> list[dict]:
    return [
        {
            "name": "write_cafe_post",
            "description": "네이버 카페에 글을 작성합니다. confirmed=false면 임시저장, true면 즉시 발행.",
            "params": {
                "cafe_url": {"type": "string", "description": "카페 URL (예: https://cafe.naver.com/0moo)"},
                "board_name": {"type": "string", "description": "게시판 이름 (예: 기업홍보/기업자료)"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "confirmed": {"type": "boolean", "description": "true면 즉시 발행, false면 임시저장"},
            },
            "required": ["cafe_url", "board_name", "title", "body"],
        },
        {
            "name": "collect_cafe_posts",
            "description": "카페 게시글을 수집합니다.",
            "params": {
                "cafe_url": {"type": "string"},
                "keyword": {"type": "string"},
                "days": {"type": "integer"},
            },
            "required": ["cafe_url"],
        },
        {
            "name": "get_cafe_summary",
            "description": "카페 수집 현황 요약을 반환합니다.",
            "params": {},
        },
    ]


def _run_cafe_tool(name: str, inputs: dict) -> dict:
    sys.path.insert(0, str(ROOT))
    try:
        if name == "write_cafe_post":
            from playwright.sync_api import sync_playwright

            from scripts.naver.cafe import confirm_publish, write_post

            confirmed = inputs.pop("confirmed", False)
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(_CDP).contexts[0].pages[0]
                result = write_post(page, **inputs, require_approval=not confirmed)
                if confirmed and result.get("ok"):
                    result = confirm_publish(page)
            return result

        if name == "collect_cafe_posts":
            from playwright.sync_api import sync_playwright

            from scripts.naver.cafe import collect_articles

            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(_CDP).contexts[0].pages[0]
                articles = collect_articles(
                    page,
                    cafe_url=inputs["cafe_url"],
                    days=inputs.get("days", 30),
                    keyword=inputs.get("keyword", ""),
                    max_detail=50,
                )
            return {"ok": True, "count": len(articles), "articles": articles[:20]}

        if name == "get_cafe_summary":
            t0 = time.monotonic()
            raw_path = _latest_file("raw_articles_*.json")
            raw_count = 0
            if raw_path:
                try:
                    raw_count = len(json.loads(raw_path.read_text(encoding="utf-8")))
                except Exception:  # noqa: S110
                    pass
            return {
                "ok": True,
                "raw_count": raw_count,
                "raw_file": raw_path.name if raw_path else None,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        return {"ok": False, "error": f"알 수 없는 도구: {name}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_GPT_MODEL = APP_LLM_MODEL  # 앱 표준=GPT (app_llm 단일 출처)


# 카페 도구를 중앙 레지스트리에 등록(단일 출처). OpenAI 변환은 to_openai_tools 사용.
register("cafe", _cafe_tool_defs, _CAFE_WRITE_TOOLS)


def _run_cafe_gpt(messages: list, confirmed: bool):
    """자연어 명령 → GPT tool_use → 카페 수집/글쓰기 → SSE. (앱 표준=GPT)"""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        yield _sse("error", {"message": "OPENAI_API_KEY 미설정 — .env에 추가하세요"})
        return

    client = OpenAI(api_key=api_key)
    tools = to_openai_tools(_cafe_tool_defs(), _CAFE_WRITE_TOOLS, confirmed)
    history = [{"role": "system", "content": _CAFE_SYSTEM_PROMPT}, *messages]
    step = 0

    while True:
        res = client.chat.completions.create(
            model=_GPT_MODEL,
            max_tokens=2048,
            tools=tools,
            tool_choice="auto",
            messages=history,
        )
        msg = res.choices[0].message
        if msg.content:
            yield _sse("text", {"text": msg.content})
        if not msg.tool_calls:
            break

        tool_results = []
        for tc in msg.tool_calls:
            name = tc.function.name
            inputs = json.loads(tc.function.arguments or "{}")
            is_write = name in _CAFE_WRITE_TOOLS
            if is_write and not confirmed:
                yield _sse(
                    "confirm_required",
                    {
                        "tool": name,
                        "inputs": inputs,
                        "message": "글 발행에 승인이 필요합니다. confirmed=true로 재요청하세요.",
                    },
                )
                return
            step += 1
            yield _sse("step_start", {"step": step, "tool": name, "inputs": inputs, "write": is_write})
            result = _run_cafe_tool(name, inputs)
            yield _sse("step_done", {"step": step, "tool": name, "ok": result.get("ok") is not False, "result": result})
            tool_results.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)}
            )

        history.append(msg)
        history.extend(tool_results)

    yield _sse("done", {"steps": step})


# ── 카페 → 해한Ai 홈페이지 블로그 자동화 ─────────────────────────────────────


class CafeToHaehanBlogRequest(BaseModel):
    max_topics: int = 3  # 생성할 블로그 포스트 수 (최대 10)
    days: int | None = None  # 최근 N일 게시글만 분석 (없으면 전체)
    category: str | None = None  # 특정 카페 분류만 분석 (없으면 전체)
    status: str = "draft"  # "draft" | "published"


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
    import urllib.error
    import urllib.request

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
        raise HTTPException(status_code=404, detail="수집된 게시글이 없습니다 — 먼저 [게시글 수집]을 실행하세요")

    articles = json.loads(path.read_text(encoding="utf-8"))

    if body.category:
        articles = [a for a in articles if a.get("category") == body.category]
    if body.days and body.days > 0:
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=body.days)).strftime("%Y-%m-%d")
        articles = [a for a in articles if str(a.get("date", "")) >= cutoff]

    if not articles:
        raise HTTPException(status_code=404, detail="조건에 맞는 게시글이 없습니다")

    def _views(a: dict) -> int:
        try:
            return int(str(a.get("view_count", "0")).replace(",", "") or 0)
        except (ValueError, TypeError):
            return 0

    top_articles = sorted(articles, key=_views, reverse=True)[:200]

    # ── 2. AI로 블로그 주제 추출 ───────────────────────────────────────────────
    _ensure_path()
    from scripts.community.analyzer import analyze_posts

    ctx = "네이버 카페 수집글 — 소방·건설 실무자 커뮤니티"
    if body.category:
        ctx += f" · 분류={body.category}"

    posts_for_analysis = [
        {"title": a.get("title", ""), "views": a.get("view_count", ""), "date": a.get("date", "")} for a in top_articles
    ]
    report = analyze_posts(posts_for_analysis, context=ctx)
    if not report.get("ok"):
        raise HTTPException(status_code=502, detail=f"AI 분석 실패: {report.get('error', '알 수 없음')}")

    # topics 필드에서 주제 추출 (analyze_posts 반환 구조 활용)
    raw_topics: list[str] = []
    for t in report.get("topics", []):
        if isinstance(t, dict):
            raw_topics.append(t.get("title") or t.get("topic") or str(t))
        elif isinstance(t, str):
            raw_topics.append(t)
    # topics 부족하면 opportunities, trends 에서 보완
    for field in ("opportunities", "trends"):
        for item in report.get(field, []):
            label = item.get("title") or item.get("keyword") or str(item) if isinstance(item, dict) else str(item)
            if label and label not in raw_topics:
                raw_topics.append(label)

    topics = [t for t in raw_topics if t.strip()][:max_topics]
    if not topics:
        raise HTTPException(status_code=502, detail="AI가 블로그 주제를 추출하지 못했습니다 — topics 필드 없음")

    # ── 3 & 4. 주제별 블로그 생성 → 홈페이지 DB 저장 ─────────────────────────
    results = []
    headers_common = {
        "Content-Type": "application/json",
        "x-admin-key": admin_secret,
    }

    for topic in topics:
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
            item["generate"] = {"ok": True, "title": generated.get("title"), "slug": generated.get("slug")}

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
            item["save"] = {"ok": True, "id": saved.get("post", {}).get("id"), "status": post_status}

        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")[:200]
            item["error"] = f"HTTP {e.code}: {body_text}"
        except Exception as exc:
            item["error"] = str(exc)[:200]

        results.append(item)

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


class CafeChatMessage(BaseModel):
    role: str
    content: str


class CafeChatRequest(BaseModel):
    messages: list[CafeChatMessage]
    confirmed: bool = False


@naver_cafe_router.post("/chat")
def api_cafe_chat(body: CafeChatRequest, user: dict = Depends(require_role("admin", "owner"))):
    """자연어 명령 → GPT tool_use → 카페 글쓰기/수집 → SSE."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    def generate():
        try:
            yield from _run_cafe_gpt(messages, body.confirmed)
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    log_event(
        "NAVER_CAFE_CHAT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"msgs={len(messages)} confirmed={body.confirmed}",
    )
    return StreamingResponse(
        generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
