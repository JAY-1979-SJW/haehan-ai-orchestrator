"""네이버 메일 엔드포인트 (/api/v1/naver-mail/*).

- GET  /inbox      : 받은편지함 목록 (read-only, 브라우저 불필요 — DB/파일 캐시)
- POST /compose    : 메일 작성 준비 (브라우저 자동화, 사용자 승인 필요)
- POST /send       : 작성된 메일 발송 (사용자 명시 승인 + 추가 확인 필수)

보안 원칙:
  - /compose, /send 는 매번 사용자 명시 승인 필요 (CLAUDE.md 메일 전송 정책)
  - cookie/session 값 응답 금지
  - dry_run=True(기본) 이면 브라우저 자동화 미실행, 작성 정보만 반환
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

naver_mail_router = APIRouter(prefix="/naver-mail", tags=["naver-mail"])


# ── 스키마 ────────────────────────────────────────────────────────────────────


class MailComposeRequest(BaseModel):
    to: str  # 수신인 (콤마 구분 다중)
    cc: str | None = None
    subject: str = ""
    body: str = ""
    dry_run: bool = True  # True=자동화 미실행, False=실제 브라우저 실행


class MailComposeResponse(BaseModel):
    ok: bool
    dry_run: bool
    to: str
    cc: str | None
    subject: str
    body_preview: str  # 본문 앞 100자
    detail: str = ""
    requires_send_approval: bool = True


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@naver_mail_router.post("/compose")
def api_compose(
    req: MailComposeRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> MailComposeResponse:
    """메일 작성 준비.

    dry_run=True(기본): 브라우저 미실행, 작성 정보만 검증·반환.
    dry_run=False: 네이버 메일 작성 페이지에 실제로 필드를 채워 준비 상태로 대기.
    발송(send)은 별도 /send 엔드포인트 + 사용자 명시 승인 필요.
    """
    t0 = time.monotonic()
    body_preview = req.body[:100] if req.body else ""

    log_event(
        "NAVER_MAIL_COMPOSE_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if req.dry_run else "pending_browser",
        note=f"to={req.to} subject={req.subject[:30]} dry_run={req.dry_run}",
    )

    if req.dry_run:
        return MailComposeResponse(
            ok=True,
            dry_run=True,
            to=req.to,
            cc=req.cc,
            subject=req.subject,
            body_preview=body_preview,
            detail="dry_run=True: 브라우저 자동화 미실행. 실행하려면 dry_run=False로 재요청.",
            requires_send_approval=True,
        )

    # dry_run=False: 실제 브라우저 자동화
    try:
        from scripts.naver.mail import compose as naver_compose
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        result = run_on_browser_thread(
            lambda: naver_compose(
                page=get_page(),
                to=req.to,
                cc=req.cc,
                subject=req.subject,
                body=req.body,
                send=False,
            ),
            timeout=180,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_event(
            "NAVER_MAIL_COMPOSE_DONE",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"to={req.to} chips={result.get('final_chip_count')} duration_ms={duration_ms}",
        )
        return MailComposeResponse(
            ok=True,
            dry_run=False,
            to=req.to,
            cc=req.cc,
            subject=req.subject,
            body_preview=body_preview,
            detail=f"브라우저 작성 완료. 수신인 {result.get('final_chip_count', 0)}명. 발송하려면 /send 호출.",
            requires_send_approval=True,
        )
    except Exception as e:
        logger.exception("naver mail compose error")
        raise HTTPException(status_code=500, detail=f"작성 실패: {e}")


class MailSendRequest(BaseModel):
    confirmed: bool = False  # 사용자가 UI에서 "발송 확인" 버튼을 눌렀는지 여부


@naver_mail_router.post("/send")
def api_send(
    req: MailSendRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """현재 브라우저에 열려 있는 작성 메일 발송.

    반드시 /compose (dry_run=False) 이후에 호출해야 함.
    confirmed=True 여야 실제 발송 진행.
    """
    if not req.confirmed:
        raise HTTPException(
            status_code=400,
            detail="confirmed=True 로 사용자 명시 승인 후 재요청하세요.",
        )

    log_event(
        "NAVER_MAIL_SEND_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note="user confirmed send",
    )

    try:
        from scripts.naver.mail import send_mail
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        result = run_on_browser_thread(lambda: send_mail(get_page()), timeout=120)
        if result.get("success"):
            log_event(
                "NAVER_MAIL_SEND_SUCCESS",
                task_id="-",
                actor=user["actor"],
                role=user["role"],
                decision="ok",
                note=f"recipient={result.get('recipient')} subject={result.get('subject', '')[:30]}",
            )
            return {"ok": True, "detail": "발송 완료", **result}
        else:
            raise HTTPException(status_code=500, detail=result.get("error_msg", "발송 실패"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("naver mail send error")
        raise HTTPException(status_code=500, detail=f"발송 오류: {e}")
