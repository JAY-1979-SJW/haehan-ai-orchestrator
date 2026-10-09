"""범용 커뮤니티 추출 엔드포인트 (/api/v1/community/*).

URL만 주면 게시글 목록을 구조화 추출(휴리스틱 → GPT 폴백). CDP 브라우저 사용.
- 쓰기 없음. 사용자가 제공한 URL만 조회.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tools.gates.auth import require_role

from ..audit.audit_logger import log_event

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
        from scripts.browser.cdp.connection import get_page, run_on_browser_thread
        from scripts.community.universal_extractor import extract_posts

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        result = run_on_browser_thread(
            lambda: extract_posts(
                get_page(),
                url,
                max_posts=max(1, min(req.max_posts, 120)),
                use_gpt=bool(req.use_gpt),
            ),
            timeout=300,
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
        raise HTTPException(status_code=500, detail=f"추출 실패: {e}") from e


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
        raise HTTPException(status_code=400, detail=str(ve)) from ve
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
    from scripts.community.analyzer import prepare_posts_for_review

    posts = req.posts or []
    context = req.context or ""
    method = "provided"

    # url 이 있으면 먼저 추출
    if req.url:
        try:
            from scripts.browser.cdp.connection import get_page, run_on_browser_thread
            from scripts.community.universal_extractor import extract_posts

            ex = run_on_browser_thread(
                lambda: extract_posts(get_page(), req.url.strip(), max_posts=max(1, min(req.max_posts, 120))),
                timeout=300,
            )
            if not ex.get("ok"):
                raise HTTPException(status_code=502, detail=ex.get("error") or "추출 실패")
            posts = ex.get("posts", [])
            method = ex.get("method", "extract")
            context = context or req.url
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("analyze extract error")
            raise HTTPException(status_code=500, detail=f"추출 실패: {e}") from e

    if not posts:
        raise HTTPException(status_code=400, detail="분석할 게시글(url 또는 posts)이 필요합니다")

    try:
        report = prepare_posts_for_review(posts, context=context)
    except Exception as e:
        logger.exception("analyze error")
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}") from e

    log_event(
        "COMMUNITY_ANALYZE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if report.get("ok") else "error",
        note=f"method={method} posts={len(posts)}",
    )
    return {**report, "source_method": method, "posts": posts[:50]}


# ── 자율 스케줄러 (리포트 조회 + 수동 실행) ──────────────────────────────────


@community_router.get("/reports")
def reports(limit: int = 10, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """저장된 자율 분석 리포트 목록 + 스케줄 상태."""
    _ensure_path()
    from scripts.community.scheduler import get_state, list_reports

    return {"ok": True, "state": get_state(), "reports": list_reports(limit=max(1, min(limit, 30)))}


@community_router.post("/run-now")
def run_now(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """등록된 모든 사이트를 지금 즉시 수집·분석·리포트 저장."""
    _ensure_path()
    from scripts.community.scheduler import run_all_sites

    try:
        rep = run_all_sites(reason="manual")
    except Exception as e:
        logger.exception("community run-now error")
        raise HTTPException(status_code=500, detail=f"실행 실패: {e}") from e
    log_event(
        "COMMUNITY_RUN_NOW",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"sites={rep.get('site_count')} ok={rep.get('ok_count')}",
    )
    return {"ok": True, **rep}


# ── 알림 설정 (텔레그램) ─────────────────────────────────────────────────────


class TelegramSetupRequest(BaseModel):
    token: str


class NotifyToggleRequest(BaseModel):
    enabled: bool


@community_router.get("/notify/config")
def notify_config(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """알림 설정(토큰 마스킹)."""
    _ensure_path()
    from scripts.community.notifier import public_config

    return {"ok": True, **public_config()}


@community_router.post("/notify/telegram")
def notify_telegram_setup(req: TelegramSetupRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """봇 토큰 저장 + chat_id 자동 감지(봇에 메시지를 먼저 보내야 감지됨)."""
    _ensure_path()
    from scripts.community.notifier import public_config, set_token_and_detect

    r = set_token_and_detect(req.token)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "설정 실패")
    log_event(
        "COMMUNITY_NOTIFY_SETUP",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"chat_detected={r.get('detected')}",
    )
    return {"ok": True, "detected": r.get("detected"), **public_config()}


@community_router.post("/notify/test")
def notify_test(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """테스트 메시지 발송."""
    _ensure_path()
    from scripts.community.notifier import send_message

    res = send_message("✅ 해한 AI 알림 연결 테스트입니다. 자율 분석 리포트가 이 채널로 전송됩니다.")
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "발송 실패(봇에 먼저 메시지를 보냈는지 확인)")
    return {"ok": True}


@community_router.post("/notify/toggle")
def notify_toggle(req: NotifyToggleRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """알림 발송 on/off."""
    _ensure_path()
    from scripts.community.notifier import load_config, public_config, save_config

    cfg = load_config()
    cfg["enabled"] = bool(req.enabled)
    save_config(cfg)
    return {"ok": True, **public_config()}
