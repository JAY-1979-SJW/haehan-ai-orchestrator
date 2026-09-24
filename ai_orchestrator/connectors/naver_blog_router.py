"""네이버 블로그 API 라우터 — 초안 저장·조회·SEO 분석·AI 채팅."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ai_orchestrator.app_llm import APP_LLM_MODEL
from ai_orchestrator.audit_logger import log_event
from ai_orchestrator.connectors.tool_registry import register, to_openai_tools
from ai_orchestrator.gates.auth import require_role
from scripts.realtime_audit import emit_event

_log = logging.getLogger(__name__)

naver_blog_router = APIRouter(prefix="/naver/blog", tags=["naver-blog"])

DRAFTS_DIR = Path(__file__).resolve().parents[2] / "data" / "blog_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "blog_uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_UNSPLASH_CACHE = Path(__file__).resolve().parents[2] / "data" / "unsplash_images.json"
_UNSPLASH_API = "https://api.unsplash.com"


def _unsplash_key() -> str:
    return os.environ.get("UNSPLASH_ACCESS_KEY", "")


# 허용 미디어 확장자 (사진·이미지·동영상)
_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
_VID_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB (동영상 고려)


def _unsplash_english_query(topic: str) -> str:
    """한국어 주제 → Unsplash 검색용 영어 키워드(3단어 이내) 변환."""
    try:
        from ai_orchestrator.openai_proxy_caller import call_openai_chat

        prompt = (
            "다음 한국어 블로그 주제를 Unsplash 이미지 검색에 적합한 영어 키워드로 변환하세요.\n"
            "영어 단어 3개 이내, 명사 위주로만 출력하세요 (설명·문장 금지).\n"
            f"주제: {topic}"
        )
        res = call_openai_chat(message=prompt)
        if res.ok and res.text.strip():
            import re as _re

            first_line = res.text.strip().splitlines()[0]
            cleaned = _re.sub(r"[^A-Za-z ]", " ", first_line).strip()
            words = cleaned.split()[:3]
            if words:
                return " ".join(words)
    except Exception:  # noqa: S110
        pass
    return "interior design"


def _unsplash_live_search(topic: str, count: int) -> list[str]:
    """Unsplash 공개 검색 API(AI 아님, 허용된 외부 API)로 실시간 이미지 검색·다운로드.

    쿼리: 영어 3단어 이내 / orientation=landscape (해한 AI 홈페이지 프로젝트 검증된 방식과 동일).
    """
    key = _unsplash_key()
    if not key:
        return []

    import hashlib
    import time

    import requests as _req

    query = _unsplash_english_query(topic)
    resp = _req.get(
        f"{_UNSPLASH_API}/search/photos",
        params={"query": query, "per_page": count, "orientation": "landscape"},
        headers={"Authorization": f"Client-ID {key}"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    result_names: list[str] = []
    for photo in results[:count]:
        img_url = (photo.get("urls") or {}).get("regular")
        if not img_url:
            continue
        fname = f"unsplash_{hashlib.md5(img_url.encode(), usedforsecurity=False).hexdigest()[:10]}.jpg"
        dest = UPLOADS_DIR / fname
        if not dest.exists():
            img_r = _req.get(img_url, timeout=20, headers={"User-Agent": "HaehanAI/1.0"})
            img_r.raise_for_status()
            dest.write_bytes(img_r.content)
        # Unsplash Production 요건: 사용 시 download 엔드포인트 호출
        photo_id = photo.get("id")
        if photo_id:
            try:
                _req.get(
                    f"{_UNSPLASH_API}/photos/{photo_id}/download",
                    headers={"Authorization": f"Client-ID {key}"},
                    timeout=5,
                )
            except Exception:  # noqa: S110
                pass
        result_names.append(fname)
        time.sleep(0.1)

    if result_names:
        emit_event(
            "NAVER_BLOG_UNSPLASH",
            site="naver_blog",
            workflow="blog_media",
            status="resolved_live",
            risk="none",
            metadata={"topic": topic[:80], "query": query, "count": len(result_names)},
        )
    return result_names


def _resolve_unsplash_images(topic: str, media: list[str], count: int = 3) -> list[str]:
    """media가 비어 있으면 Unsplash에서 이미지를 가져와 blog_uploads에 다운로드 후 파일명 반환.

    1. media가 이미 있으면 그대로 반환
    2. Unsplash 실시간 검색(API 키 있을 때) 우선 시도
    3. 실패 시 로컬 캐시(unsplash_images.json)로 폴백
    """
    if media:
        return media

    try:
        names = _unsplash_live_search(topic, count)
        if names:
            return names
    except Exception:  # noqa: S110
        pass

    return _resolve_unsplash_images_from_cache(topic, count)


def _resolve_unsplash_images_from_cache(topic: str, count: int = 3) -> list[str]:
    """Unsplash 실시간 검색 실패 시 폴백 — 로컬 캐시(unsplash_images.json)에서 선택.

    1. unsplash_images.json 로드 → topic 키워드 매칭 → 없으면 전체 순환
    2. URL → data/blog_uploads/unsplash_*.jpg 다운로드
    3. Unsplash 정책상 download_location 트리거
    """
    if not _UNSPLASH_CACHE.exists():
        return []

    try:
        import hashlib
        import time

        import requests as _req

        all_imgs: list[dict] = json.loads(_UNSPLASH_CACHE.read_text(encoding="utf-8")).get("images", [])
        if not all_imgs:
            return []

        # 키워드 매칭 (topic 단어 중 하나라도 query/desc에 포함)
        words = [w for w in topic.lower().split() if len(w) > 1]
        matched = [
            img for img in all_imgs if any(w in (img.get("query", "") + img.get("desc", "")).lower() for w in words)
        ] or all_imgs  # 매칭 없으면 전체 사용

        selected = [matched[i % len(matched)] for i in range(count)]
        result_names: list[str] = []

        for img in selected:
            url = img.get("url", "")
            if not url:
                continue
            fname = f"unsplash_{hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:10]}.jpg"
            dest = UPLOADS_DIR / fname
            if not dest.exists():
                r = _req.get(url, timeout=20, headers={"User-Agent": "HaehanAI/1.0"})
                r.raise_for_status()
                dest.write_bytes(r.content)
            # Unsplash 정책: 다운로드 트리거
            dl_loc = img.get("download_location", "")
            if dl_loc:
                try:
                    _req.get(dl_loc, headers={"Authorization": f"Client-ID {_unsplash_key()}"}, timeout=5)
                except Exception as e:
                    # Unsplash 정책상 download_location 통지는 실패해도 본 작업은 계속한다
                    _log.debug("[unsplash] download_location 통지 실패: %s", type(e).__name__)
            result_names.append(fname)
            time.sleep(0.1)

        emit_event(
            "NAVER_BLOG_UNSPLASH",
            site="naver_blog",
            workflow="blog_media",
            status="resolved",
            risk="none",
            metadata={"topic": topic[:80], "count": len(result_names), "files": result_names},
        )
        return result_names
    except Exception:
        return []


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


class BlogWriteRequest(BaseModel):
    title: str
    body: str
    tags: list[str] = []
    category: str | None = None
    media: list[str] = []  # 업로드된 사진·동영상 파일명
    image_count: int = 3  # Unsplash 자동 선택 이미지 수 (media 없을 때 적용, 0=이미지 없음)
    publish: bool = False  # False=임시저장(되돌림 가능) / True=실제 발행(외부공개 — 사용자 확인 필수)
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


@naver_blog_router.post("/write-to-naver")
def write_to_naver(
    req: BlogWriteRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """전용 작성기(BlogWriter)로 네이버 블로그에 직접 작성. 기본 임시저장, publish=True면 발행.

    BlogWriter 가 SE3 셀렉터·iframe·자동로그인을 처리. 범용 클릭 에이전트보다 정확.
    """
    from scripts.web_connector import get_page, run_on_browser_thread

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

        if req.sections:
            # 섹션별 배치 — 지정한 순서 그대로 텍스트/사진을 섞어서 삽입.
            # 이미지 경로는 업로드 폴더 기준으로 해석(존재하지 않으면 그대로 URL 취급).
            blocks: list[dict[str, str]] = []
            for section in req.sections:
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
        else:
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
    mt = re.search(r"제목\s*[:：]\s*(.+)", text)
    if mt:
        title = mt.group(1).strip()
    mg = re.search(r"태그\s*[:：]\s*(.+)", text)
    if mg:
        tags = [t.strip().lstrip("#") for t in re.split(r"[,，]", mg.group(1)) if t.strip()][:8]
    mb = re.search(r"본문\s*[:：]\s*\n?(.+)", text, re.S)
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


# ── 채팅 ─────────────────────────────────────────────────────────────────────

_BLOG_SYSTEM_PROMPT = """당신은 네이버 블로그 AI 에이전트입니다.
사용자의 자연어 명령을 이해하고 적절한 도구를 즉시 호출하세요.
- 글 생성(ai_generate_blog)·초안 목록(list_blog_drafts)은 묻지 말고 즉시 실행합니다.
- 글 발행(write_blog_post, publish=true)은 초안을 먼저 보여주고 '발행할까요?' 한 번만 확인합니다.
- '진행할까요?', '실행해도 될까요?' 등의 질문은 절대 하지 않습니다.
- 결과는 한국어로 간결하게 요약합니다."""

_BLOG_WRITE_TOOLS = {"write_blog_post"}
_ROOT = Path(__file__).resolve().parents[2]


def _blog_tool_defs() -> list[dict]:
    return [
        {
            "name": "write_blog_post",
            "description": "네이버 블로그에 글을 작성합니다. publish=false면 임시저장, true면 즉시 발행. Unsplash 이미지를 자동으로 삽입합니다.",
            "params": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "category": {"type": "string"},
                "image_count": {
                    "type": "integer",
                    "description": "삽입할 Unsplash 이미지 수 (기본 3, 최대 10, 0이면 이미지 없음)",
                },
                "publish": {"type": "boolean", "description": "true면 즉시 발행, false면 임시저장"},
            },
            "required": ["title", "body"],
        },
        {
            "name": "ai_generate_blog",
            "description": "주제를 받아 블로그 제목·본문·태그를 AI로 생성합니다 (발행 없음).",
            "params": {
                "topic": {"type": "string"},
                "tone": {"type": "string", "enum": ["친근한", "전문적인", "정보성"]},
            },
            "required": ["topic"],
        },
        {
            "name": "list_blog_drafts",
            "description": "임시저장된 블로그 초안 목록을 반환합니다.",
            "params": {},
        },
    ]


def _run_blog_tool(name: str, inputs: dict, confirmed: bool) -> dict:
    sys.path.insert(0, str(_ROOT))
    try:
        if name == "write_blog_post":
            from scripts.web_connector import run_on_browser_thread

            publish = inputs.pop("publish", False)
            if publish and not confirmed:
                return {"ok": False, "error": "발행은 confirmed=true가 필요합니다"}

            def _do() -> dict:
                from scripts.naver.blog.core.writer import BlogWriter
                from scripts.web_connector import get_page

                page = get_page()
                bw = BlogWriter(page)
                if not bw.open():
                    return {"ok": False, "needs_login": True, "error": "글쓰기 열기 실패 — 네이버 로그인 필요"}
                img_count = max(0, min(int(inputs.get("image_count", 3)), 10))
                media = _resolve_unsplash_images(inputs["title"] + " " + inputs["body"][:100], [], count=img_count)
                bw.set_title(inputs["title"])
                bw.write_body(inputs["body"])
                for m in media:
                    mp = UPLOADS_DIR / Path(m).name
                    if mp.exists():
                        bw.insert_image(str(mp))
                if inputs.get("category"):
                    bw.set_category(inputs["category"])
                if inputs.get("tags"):
                    bw.set_tags(inputs["tags"])
                return bw.publish() if publish else bw.save_draft()

            result = run_on_browser_thread(_do, timeout=180)
            return result or {"ok": False, "error": "브라우저 실행 실패"}

        if name == "ai_generate_blog":
            import re

            from ai_orchestrator.openai_proxy_caller import call_openai_chat

            topic = inputs.get("topic", "")
            tone = inputs.get("tone", "정보성")
            prompt = (
                f"당신은 네이버 블로그 전문 작가입니다. 아래 주제로 블로그 글을 작성하세요.\n"
                f"톤: {tone}. 자연스러운 한국어, 본문 800~1500자, 소제목(■) 활용.\n"
                "아래 형식으로만 출력하세요.\n"
                "제목: (한 줄 제목)\n태그: 태그1, 태그2 (최대 8개)\n본문:\n(본문 전체)\n\n"
                f"주제: {topic}"
            )
            res = call_openai_chat(message=prompt)
            if not res.ok:
                return {"ok": False, "error": res.error_code or "생성 실패"}
            text = res.text.strip()
            title, tags, body = topic, [], text
            mt = re.search(r"제목\s*[:：]\s*(.+)", text)
            if mt:
                title = mt.group(1).strip()
            mg = re.search(r"태그\s*[:：]\s*(.+)", text)
            if mg:
                tags = [t.strip().lstrip("#") for t in re.split(r"[,，]", mg.group(1)) if t.strip()][:8]
            mb = re.search(r"본문\s*[:：]\s*\n?(.+)", text, re.S)
            if mb:
                body = mb.group(1).strip()
            return {"ok": True, "title": title, "body": body, "tags": tags}

        if name == "list_blog_drafts":
            drafts_dir = _ROOT / "data" / "blog_drafts"
            if not drafts_dir.exists():
                return {"ok": True, "drafts": []}
            drafts = []
            for f in sorted(drafts_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    drafts.append({"id": f.stem, "title": d.get("title", ""), "created_at": d.get("created_at", "")})
                except Exception:  # noqa: S110
                    pass
            return {"ok": True, "count": len(drafts), "drafts": drafts}

        return {"ok": False, "error": f"알 수 없는 도구: {name}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}


def _sse_blog(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_GPT_MODEL = APP_LLM_MODEL  # 앱 표준=GPT (app_llm 단일 출처)


# 블로그 도구를 중앙 레지스트리에 등록(단일 출처). OpenAI 변환은 to_openai_tools 사용.
register("blog", _blog_tool_defs, _BLOG_WRITE_TOOLS)


def _run_blog_gpt(messages: list, confirmed: bool):
    """자연어 명령 → GPT tool_use → 블로그 글쓰기/초안 → SSE. (앱 표준=GPT)"""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        yield _sse_blog("error", {"message": "OPENAI_API_KEY 미설정 — .env에 추가하세요"})
        return

    client = OpenAI(api_key=api_key)
    tools = to_openai_tools(_blog_tool_defs(), _BLOG_WRITE_TOOLS, confirmed)
    history = [{"role": "system", "content": _BLOG_SYSTEM_PROMPT}, *messages]
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
            yield _sse_blog("text", {"text": msg.content})
        if not msg.tool_calls:
            break

        tool_results = []
        for tc in msg.tool_calls:
            name = tc.function.name
            inputs = json.loads(tc.function.arguments or "{}")
            is_write = name in _BLOG_WRITE_TOOLS
            if is_write and not confirmed:
                yield _sse_blog(
                    "confirm_required",
                    {
                        "tool": name,
                        "inputs": inputs,
                        "message": "블로그 발행에 승인이 필요합니다. confirmed=true로 재요청하세요.",
                    },
                )
                return
            step += 1
            yield _sse_blog("step_start", {"step": step, "tool": name, "inputs": inputs, "write": is_write})
            result = _run_blog_tool(name, inputs, confirmed)
            yield _sse_blog(
                "step_done", {"step": step, "tool": name, "ok": result.get("ok") is not False, "result": result}
            )
            tool_results.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)}
            )

        history.append(msg)
        history.extend(tool_results)

    yield _sse_blog("done", {"steps": step})


class BlogChatMessage(BaseModel):
    role: str
    content: str


class BlogChatRequest(BaseModel):
    messages: list[BlogChatMessage]
    confirmed: bool = False


@naver_blog_router.post("/chat")
def api_blog_chat(body: BlogChatRequest, user: dict = Depends(require_role("admin", "owner"))):
    """자연어 명령 → GPT tool_use → 블로그 글쓰기/초안 → SSE."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    def generate():
        try:
            yield from _run_blog_gpt(messages, body.confirmed)
        except Exception as e:
            yield _sse_blog("error", {"message": str(e)})

    log_event(
        "NAVER_BLOG_CHAT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"msgs={len(messages)} confirmed={body.confirmed}",
    )
    return StreamingResponse(
        generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
