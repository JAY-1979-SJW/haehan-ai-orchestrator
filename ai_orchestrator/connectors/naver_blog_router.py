"""네이버 블로그 API 라우터 — 초안 저장·조회·SEO 분석."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai_orchestrator.auth import require_role
from scripts.realtime_audit import emit_event

naver_blog_router = APIRouter(prefix="/naver/blog", tags=["naver-blog"])

DRAFTS_DIR = Path(__file__).resolve().parents[2] / "data" / "blog_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "blog_uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 허용 미디어 확장자 (사진·이미지·동영상)
_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
_VID_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB (동영상 고려)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ── 모델 ─────────────────────────────────────────────────────────────────────


class ComposeRequest(BaseModel):
    title: str
    body: str
    category: str = "일반"
    tags: list[str] = []
    media: list[str] = []  # 업로드된 사진·동영상 파일명 목록
    dry_run: bool = True


class SeoRequest(BaseModel):
    title: str
    body: str
    target_keywords: list[str] = []


class AIGenerateRequest(BaseModel):
    topic: str
    tone: str = "정보형"


# ── 엔드포인트 ───────────────────────────────────────────────────────────────


def _safe_media_name(original: str) -> str:
    """안전한 파일명 생성: 확장자 검증 + 타임스탬프 prefix(경로주입 차단)."""
    import re

    ext = Path(original or "").suffix.lower()
    if ext not in _IMG_EXT and ext not in _VID_EXT:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다: {ext or '(없음)'} (이미지/동영상만)")
    stem = re.sub(r"[^A-Za-z0-9가-힣_-]", "_", Path(original).stem)[:40] or "media"
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{stem}{ext}"


@naver_blog_router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """블로그용 사진·이미지·동영상 업로드 → data/blog_uploads/ 저장."""
    name = _safe_media_name(file.filename or "")
    dest = UPLOADS_DIR / name
    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 200MB)")
                out.write(chunk)
    finally:
        await file.close()
    kind = "video" if dest.suffix.lower() in _VID_EXT else "image"
    emit_event(
        "NAVER_BLOG_UPLOAD",
        site="naver_blog",
        workflow="blog_media",
        status="uploaded",
        risk="none",
        artifact_path=str(dest),
        metadata={"name": name, "kind": kind, "bytes": size},
    )
    return {"ok": True, "name": name, "kind": kind, "size": size, "url": f"/api/v1/naver/blog/upload/{name}"}


@naver_blog_router.get("/upload/{name}")
def get_media(
    name: str,
    user: dict = Depends(require_role("admin", "owner")),
) -> FileResponse:
    """업로드된 미디어 미리보기 제공 (경로주입 차단)."""
    safe = Path(name).name  # 디렉터리 트래버설 방지
    path = UPLOADS_DIR / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(str(path))


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
        "media": req.media,
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
