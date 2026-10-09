"""네이버 블로그 API 라우터 — 초안 저장·조회·SEO 분석. (GPT 채팅 삭제됨 — 본문 작성은 Claude Code/MCP)"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.realtime_audit import emit_event
from scripts.naver.blog.unsplash_images import UPLOADS_DIR
from scripts.naver.blog.unsplash_images import (
    resolve_unsplash_images as _resolve_unsplash_images,  # 재노출(옛 이름 유지)
)
from tools.gates.auth import require_role

_log = logging.getLogger(__name__)

naver_blog_router = APIRouter(prefix="/naver/blog", tags=["naver-blog"])

DRAFTS_DIR = data_dir() / "blog_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


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


BLOG_PUBLISH_CONFIRM_TEXT = "NAVER_BLOG_APPROVED_PUBLISH"


class BlogWriteRequest(BaseModel):
    title: str
    body: str
    tags: list[str] = []
    category: str | None = None
    media: list[str] = []  # 업로드된 사진·동영상 파일명
    image_count: int = 3  # Unsplash 자동 선택 이미지 수 (media 없을 때 적용, 0=이미지 없음)
    publish: bool = False  # False=임시저장(되돌림 가능) / True=실제 발행(외부공개 — 사용자 확인 필수)
    # publish=True 일 때 사용자가 확인 단계에서 직접 입력한 승인 문구(BLOG_PUBLISH_CONFIRM_TEXT). 없거나 다르면 403.
    publish_confirm: str | None = None
    # 섹션별 사진 배치 (선택) — 지정 시 media/image_count 무시하고 이 순서 그대로 삽입.
    # [{"type": "text", "value": "..."}, {"type": "image", "value": "업로드된 파일명"}, ...]
    # 미지정 시 기존 방식(첫 사진만 맨 위, 나머지는 본문 끝) 그대로 동작 — 하위호환.
    sections: list[dict[str, str]] | None = None


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


def _write_sections(bw, req: BlogWriteRequest) -> dict | None:
    """섹션별 배치 — 지정한 순서 그대로 텍스트/사진을 섞어서 삽입. 실패 시 응답 dict, 성공 시 None."""
    # 이미지 경로는 업로드 폴더 기준으로 해석(존재하지 않으면 그대로 URL 취급).
    blocks: list[dict[str, str]] = []
    for section in req.sections or []:
        if section.get("type") == "image":
            name = section.get("value", "")
            resolved = UPLOADS_DIR / Path(name).name
            blocks.append({"type": "image", "value": str(resolved) if resolved.exists() else name})
        else:
            blocks.append(section)
    ok = bw.write_mixed_content(blocks)
    if not ok:
        return {
            "ok": False,
            "error": "섹션별 본문/사진 삽입 실패 — 실제 화면에 반영되지 않음",
            "verify": bw.verify_body(req.body),
        }
    return None


def _write_plain_body(bw, req: BlogWriteRequest) -> dict | None:
    """본문 + 이미지 배치 후 검증. 실패 시 응답 dict, 성공 시 None."""
    resolved_media = _resolve_unsplash_images(
        req.title + " " + req.body[:100], req.media, count=max(0, min(req.image_count, 10))
    )
    media_paths = [UPLOADS_DIR / Path(m).name for m in resolved_media if (UPLOADS_DIR / Path(m).name).exists()]

    def _insert(mp):
        (bw.insert_video if mp.suffix.lower() in _VID_EXT else bw.insert_image)(str(mp))

    # 배치: 첫 이미지 → 본문 전체 → 나머지 이미지(중간·끝 순)
    # 이미지 삽입 후 write_body(append=True)로 커서 위치에 이어써야
    # BODY_SEL 클릭으로 커서가 이미지 위 텍스트 블록으로 돌아가는 문제 방지
    if media_paths:
        _insert(media_paths[0])  # 맨 처음 이미지
        bw.write_body(req.body, append=True)  # 이미지 바로 아래에 본문 이어쓰기
    else:
        bw.write_body(req.body)  # 이미지 없으면 기존 방식
    for mp in media_paths[1:]:  # 나머지 이미지는 본문 뒤(중간·끝)
        _insert(mp)

    verify = bw.verify_body(req.body)
    if not verify["ok"]:
        return {
            "ok": False,
            "error": "본문 검증 실패 — 실제 화면에 입력한 내용이 반영되지 않음",
            "verify": verify,
        }
    return None


@naver_blog_router.post("/write-to-naver")
def write_to_naver(
    req: BlogWriteRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """전용 작성기(BlogWriter)로 네이버 블로그에 직접 작성. 기본 임시저장, publish=True면 발행.

    BlogWriter 가 SE3 셀렉터·iframe·자동로그인을 처리. 범용 클릭 에이전트보다 정확.
    """
    from scripts.browser.cdp.connection import get_page, run_on_browser_thread
    from tools.gates.gate_core import GateBlocked, require_side_effect

    if req.publish:
        # 외부 공개 발행: 사용자가 확인 단계에서 입력한 승인 문구가 있어야 한다. 막히면 브라우저를 열기 전에 403.
        try:
            require_side_effect(
                "blog_publish", approval=req.publish_confirm, expected=BLOG_PUBLISH_CONFIRM_TEXT, title=req.title
            )
        except GateBlocked as exc:
            raise HTTPException(
                status_code=403,
                detail=f"발행 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)",
            ) from exc

    def _do() -> dict:
        from scripts.naver.blog.core.writer import BlogWriter

        page = get_page()
        bw = BlogWriter(page)
        if not bw.open():
            return {
                "ok": False,
                "needs_login": True,
                "error": "글쓰기 열기 실패 — 네이버 로그인 필요(브라우저에서 로그인 후 재시도).",
            }
        bw.set_title(req.title)

        failure = _write_sections(bw, req) if req.sections else _write_plain_body(bw, req)
        if failure is not None:
            return failure

        if req.category:
            bw.set_category(req.category)
        if req.tags:
            bw.set_tags(req.tags)

        return bw.publish() if req.publish else bw.save_draft()

    result = run_on_browser_thread(_do, timeout=200)
    emit_event(
        "NAVER_BLOG_WRITE",
        site="naver_blog",
        workflow="blog_write_to_naver",
        status="published" if req.publish else "draft",
        risk="high" if req.publish else "low",
        metadata={"title": req.title, "publish": req.publish, "media": len(req.media)},
    )
    return {"ok": bool(result and result.get("ok")), "publish": req.publish, "result": result}


@naver_blog_router.post("/ai-generate")
def ai_generate_blog(
    req: AIGenerateRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """주제 → 초안 자리표시(발행 아님). 본문 작성은 Claude Code(MCP)가 수행 후 /compose 로 저장."""
    topic = (req.topic or "").strip()
    if not topic:
        return {"ok": False, "error": "주제를 입력하세요"}
    return {
        "ok": False,
        "error": "앱 런타임 AI 생성 없음 — Claude Code(MCP)가 본문을 작성해 /naver/blog/compose 로 저장하세요.",
    }


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
        except Exception as exc:  # noqa: BLE001
            _log.debug("블로그 초안 파일 읽기 실패(무시): %s", type(exc).__name__)
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
    except Exception as e:  # noqa: BLE001 - 네이버 블로그 이미지(Unsplash) 다운로드/초안 목록/SEO 제안 라우터 - 실패 시 빈 목록/기본 분석값으로 폴백, 쓰기 실패는 draft 목록에서 빠질 뿐 발행 승인 로직과 무관
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
