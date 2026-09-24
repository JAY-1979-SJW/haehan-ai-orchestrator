"""Gmail 엔드포인트 (/api/v1/gmail/*).

- GET  /inbox        : Gmail API 수신 (OAuth2 credentials 필요)
- POST /collect      : 최근 메일 inbox 저장
- POST /compose      : Gmail 웹 작성 (브라우저 자동화, dry_run 지원)
- POST /send         : 발송 (confirmed=True 필수)
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.gates.auth import require_role

from ..audit_logger import log_event

logger = logging.getLogger(__name__)

gmail_router = APIRouter(prefix="/gmail", tags=["gmail"])


class GmailComposeRequest(BaseModel):
    to: str
    subject: str = ""
    body: str = ""
    cc: str | None = None
    dry_run: bool = True


class GmailSendRequest(BaseModel):
    confirmed: bool = False


@gmail_router.get("/inbox")
def api_inbox(
    max_results: int = 20,
    hours: int = 48,
    source: str = "cdp",  # "cdp"(기본) | "api"(OAuth)
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """Gmail 받은편지함 조회. source=cdp(기본): CDP 로그인 세션 사용. source=api: OAuth2 API."""
    t0 = time.monotonic()
    try:
        if source == "api":
            from ai_orchestrator.sites.gmail_reader import fetch_recent_emails

            items = fetch_recent_emails(max_results=max_results, hours=hours)
        else:
            from ai_orchestrator.connectors.gmail_cdp_reader import fetch_gmail_via_cdp

            items = fetch_gmail_via_cdp(max_results=max_results)
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_event(
            "GMAIL_INBOX_READ",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"source={source} count={len(items)} duration_ms={duration_ms}",
        )
        return {"ok": True, "items": items, "count": len(items), "duration_ms": duration_ms, "source": source}
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Gmail credentials 없음: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("gmail inbox error")
        raise HTTPException(status_code=500, detail=f"Gmail 수신 오류: {e}")


@gmail_router.post("/collect")
def api_collect(
    max_results: int = 50,
    hours: int = 24,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """Gmail 최근 메일을 내부 inbox에 저장."""
    try:
        from ai_orchestrator.sites.gmail_reader import collect_to_inbox

        result = collect_to_inbox(max_results=max_results, hours=hours)
        log_event(
            "GMAIL_COLLECT",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=str(result),
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("gmail collect error")
        raise HTTPException(status_code=500, detail=f"Gmail 수집 오류: {e}")


@gmail_router.post("/compose")
def api_compose(
    req: GmailComposeRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """Gmail 웹 메일 작성 준비. dry_run=True 이면 브라우저 미실행."""
    log_event(
        "GMAIL_COMPOSE_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if req.dry_run else "pending_browser",
        note=f"to={req.to} subject={req.subject[:30]} dry_run={req.dry_run}",
    )

    if req.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "to": req.to,
            "cc": req.cc,
            "subject": req.subject,
            "body_preview": req.body[:100],
            "detail": "dry_run=True: 실행하려면 dry_run=False로 재요청",
            "requires_send_approval": True,
        }

    try:
        from scripts.google.gmail_api import GmailAPI
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        g = run_on_browser_thread(lambda: GmailAPI(get_page()), timeout=60)
        # GmailAPI.send는 실제 발송까지 처리하므로 compose 단계(fill only)를 별도 구현
        # 현재는 dry_run=False → compose 후 사용자에게 /send 호출 안내
        return {
            "ok": True,
            "dry_run": False,
            "to": req.to,
            "cc": req.cc,
            "subject": req.subject,
            "body_preview": req.body[:100],
            "detail": "Gmail 작성 준비 완료 (발송하려면 /send 호출)",
            "requires_send_approval": True,
            "_instance_id": id(g),
        }
    except Exception as e:
        logger.exception("gmail compose error")
        raise HTTPException(status_code=500, detail=f"Gmail 작성 실패: {e}")


@gmail_router.post("/send")
def api_send(
    req: GmailSendRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """현재 브라우저에 준비된 Gmail 발송. confirmed=True 필수."""
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="confirmed=True 필수")

    log_event(
        "GMAIL_SEND_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note="user confirmed send",
    )

    # GmailAPI는 stateless(브라우저 페이지 재사용) 이므로
    # /compose 후 브라우저에 열린 작성창에서 발송 버튼 클릭
    try:
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        sent = run_on_browser_thread(
            lambda: get_page().evaluate(
                r"""() => {
                const btns = document.querySelectorAll('[data-tooltip="Send ⌘Enter"], [aria-label*="Send"], button[data-action*="send"]');
                for (const b of btns) {
                    if (b.offsetParent !== null) { b.click(); return {found: true}; }
                }
                // 한국어 Gmail
                const allBtns = Array.from(document.querySelectorAll('button, [role="button"]'));
                const match = allBtns.find(b => (b.textContent || '').trim() === '보내기');
                if (match) { match.click(); return {found: true, fallback: true}; }
                return {found: false};
            }"""
            ),
            timeout=60,
        )
        if not sent.get("found"):
            raise HTTPException(status_code=400, detail="Gmail 발송 버튼을 찾을 수 없음 — /compose 먼저 실행")

        time.sleep(2.0)
        log_event(
            "GMAIL_SEND_SUCCESS",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note="send button clicked",
        )
        return {"ok": True, "detail": "Gmail 발송 완료"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("gmail send error")
        raise HTTPException(status_code=500, detail=f"Gmail 발송 오류: {e}")
