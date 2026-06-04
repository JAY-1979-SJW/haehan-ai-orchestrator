"""네이버 블로그 API 라우터 — 초안 저장·조회·SEO 분석."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_orchestrator.auth import require_role
from scripts.realtime_audit import emit_event

naver_blog_router = APIRouter(prefix="/naver/blog", tags=["naver-blog"])

DRAFTS_DIR = Path(__file__).resolve().parents[2] / "data" / "blog_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ── 모델 ─────────────────────────────────────────────────────────────────────


class ComposeRequest(BaseModel):
    title: str
    body: str
    category: str = "일반"
    tags: list[str] = []
    dry_run: bool = True


class SeoRequest(BaseModel):
    title: str
    body: str
    target_keywords: list[str] = []


class AIGenerateRequest(BaseModel):
    topic: str
    tone: str = "정보형"


# ── 엔드포인트 ───────────────────────────────────────────────────────────────


@naver_blog_router.post("/ai-generate")
def ai_generate_blog(
    req: AIGenerateRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """주제 → AI 가 제목·본문·태그 생성 (초안 작성용, 발행 아님)."""
    import re

    topic = (req.topic or "").strip()
    if not topic:
        return {"ok": False, "error": "주제를 입력하세요"}
    from ai_orchestrator.openai_proxy_caller import call_openai_chat

    prompt = (
        "당신은 네이버 블로그 전문 작가입니다. 아래 주제로 블로그 글을 작성하세요.\n"
        f"톤: {req.tone}. 자연스러운 한국어, 본문 800~1500자, 소제목(■) 활용.\n"
        "아래 형식으로만 출력하세요. JSON 쓰지 마세요.\n"
        "제목: (한 줄 제목)\n"
        "태그: 태그1, 태그2, 태그3 (쉼표 구분, 최대 8개)\n"
        "본문:\n"
        "(여기에 본문 전체)\n\n"
        f"주제: {topic}"
    )
    res = call_openai_chat(message=prompt)
    if not res.ok:
        return {"ok": False, "error": res.error_code or "생성 실패"}
    text = res.text.strip()
    title, tags, body = topic, [], text
    mt = re.search(r"제목\s*[:：]\s*(.+)", text)  # noqa: RUF001
    if mt:
        title = mt.group(1).strip()
    mg = re.search(r"태그\s*[:：]\s*(.+)", text)  # noqa: RUF001
    if mg:
        tags = [t.strip().lstrip("#") for t in re.split(r"[,，]", mg.group(1)) if t.strip()][:8]  # noqa: RUF001
    mb = re.search(r"본문\s*[:：]\s*\n?(.+)", text, re.S)  # noqa: RUF001
    if mb:
        body = mb.group(1).strip()
    return {"ok": True, "title": title, "body": body, "tags": tags}


@naver_blog_router.post("/compose")
def compose_post(
    req: ComposeRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """블로그 초안 저장 (dry_run 기본). 실제 발행은 승인 게이트 별도 진행."""
    draft_id = f"blog_draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    draft = {
        "id": draft_id,
        "created_at": _now(),
        "title": req.title,
        "category": req.category,
        "tags": req.tags,
        "body_length": len(req.body),
        "body_preview": req.body[:200],
        "body": req.body,
        "dry_run": req.dry_run,
        "status": "draft",
        "published_url": None,
    }
    path = DRAFTS_DIR / f"{draft_id}.json"
    path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    emit_event(
        "NAVER_BLOG_COMPOSE",
        site="naver_blog",
        workflow="blog_compose",
        status="draft_saved",
        risk="none",
        artifact_path=str(path),
        metadata={"title": req.title, "dry_run": req.dry_run},
    )
    return {"ok": True, "draft_id": draft_id, "status": "draft_saved", "path": str(path)}


@naver_blog_router.get("/drafts")
def list_drafts(
    limit: int = 20,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """저장된 블로그 초안 목록 조회."""
    files = sorted(DRAFTS_DIR.glob("blog_draft_*.json"), reverse=True)[:limit]
    drafts = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            drafts.append(
                {
                    "id": d.get("id", f.stem),
                    "title": d.get("title", ""),
                    "category": d.get("category", ""),
                    "tags": d.get("tags", []),
                    "body_length": d.get("body_length", 0),
                    "status": d.get("status", "draft"),
                    "created_at": d.get("created_at", ""),
                    "published_url": d.get("published_url"),
                }
            )
        except Exception:  # noqa: S110
            pass
    return {"ok": True, "total": len(files), "items": drafts}


@naver_blog_router.post("/seo")
def analyze_seo(
    req: SeoRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """제목·본문 SEO 분석 및 태그 추천 (브라우저 불필요)."""
    try:
        from scripts.naver.blog.seo.seo import BlogSEO

        seo = BlogSEO(page=None)  # type: ignore[arg-type]
        title_result = seo.analyze_title(req.title)
        body_result = seo.analyze_body(req.body, req.target_keywords or None)
        tags = seo.suggest_tags(req.body)
        return {"ok": True, "title": title_result, "body": body_result, "suggested_tags": tags}
    except Exception as e:
        # 브라우저 없이 실행할 수 없는 경우 기본 분석으로 폴백
        words = [w.strip(".,!?") for w in req.body.split() if len(w.strip(".,!?")) >= 2]
        freq: dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        top_tags = sorted(freq, key=lambda x: -freq[x])[:7]
        return {
            "ok": True,
            "fallback": True,
            "error": str(e)[:100],
            "title": {"length": len(req.title), "ok": 20 <= len(req.title) <= 50},
            "body": {"length": len(req.body), "word_count": len(words)},
            "suggested_tags": top_tags,
        }
