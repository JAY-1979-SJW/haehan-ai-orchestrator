"""하이웍스 메일 엔드포인트 (/api/v1/hiworks-mail/*).

- GET  /inbox   : POP3 수신 (환경변수 설정 필요)
- POST /compose : 작성 준비 (브라우저 자동화, dry_run 지원)
- POST /send    : 발송 (confirmed=True 필수)
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.gates.auth import require_role
from ai_orchestrator.gates.send_approval import require_send_approval

from ..audit_logger import log_event

logger = logging.getLogger(__name__)

hiworks_mail_router = APIRouter(prefix="/hiworks-mail", tags=["hiworks-mail"])


class HWMailComposeRequest(BaseModel):
    to: str
    subject: str = ""
    body: str = ""
    dry_run: bool = True


HIWORKS_SEND_CONFIRM_TEXT = "HIWORKS_APPROVED_SEND"


class HWMailSendRequest(BaseModel):
    confirmed: bool = False
    # 사용자가 확인 단계에서 직접 입력한 승인 문구(HIWORKS_SEND_CONFIRM_TEXT). 없거나 다르면 403.
    send_confirm: str | None = None


@hiworks_mail_router.get("/inbox")
def api_inbox(
    limit: int = 20,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """하이웍스 POP3 받은편지함 (환경변수 HIWORKS_MAIL_ACCOUNT/PASSWORD 필요)."""
    t0 = time.monotonic()
    try:
        import importlib.util
        from pathlib import Path

        # hiworks_mail_reader.py 위치를 견고하게 해석: 프로젝트/번들 루트 → CWD 순.
        # (CWD 상대경로만 쓰면 번들 실행 시 CWD가 달라 FileNotFound 발생)
        _cands = [
            Path(__file__).resolve().parents[2] / "hiworks_mail_reader.py",
            Path.cwd() / "hiworks_mail_reader.py",
            Path("hiworks_mail_reader.py"),
        ]
        reader_path = next((p for p in _cands if p.exists()), None)
        if reader_path is None:
            raise FileNotFoundError("hiworks_mail_reader.py 없음 (번들 누락)")
        spec = importlib.util.spec_from_file_location("hiworks_mail_reader", str(reader_path))
        if not spec or not spec.loader:
            raise ImportError("hiworks_mail_reader.py 로드 불가")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        items = mod.fetch_recent_mails(limit=limit)
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_event(
            "HIWORKS_MAIL_INBOX_READ",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"count={len(items)} duration_ms={duration_ms}",
        )
        return {"ok": True, "items": items, "count": len(items), "duration_ms": duration_ms}
    except Exception as e:
        logger.exception("hiworks inbox error")
        raise HTTPException(status_code=500, detail=f"하이웍스 수신 오류: {e}") from e


@hiworks_mail_router.post("/compose")
def api_compose(
    req: HWMailComposeRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """하이웍스 메일 작성 준비. dry_run=True 이면 브라우저 미실행."""
    log_event(
        "HIWORKS_MAIL_COMPOSE_REQUESTED",
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
            "subject": req.subject,
            "body_preview": req.body[:100],
            "detail": "dry_run=True: 실행하려면 dry_run=False로 재요청",
            "requires_send_approval": True,
        }

    try:
        from scripts.hiworks.mail import fill_compose
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        result = run_on_browser_thread(
            lambda: fill_compose(get_page(), to=req.to, subject=req.subject, body=req.body),
            timeout=120,
        )
        return {
            "ok": True,
            "dry_run": False,
            "to": req.to,
            "subject": req.subject,
            "body_preview": req.body[:100],
            "detail": "작성 완료. 발송하려면 /send 호출.",
            "requires_send_approval": True,
            **result,
        }
    except Exception as e:
        logger.exception("hiworks compose error")
        raise HTTPException(status_code=500, detail=f"작성 실패: {e}") from e


@hiworks_mail_router.post("/send")
def api_send(
    req: HWMailSendRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """현재 브라우저에 열린 하이웍스 작성 메일 발송. confirmed=True 필수."""
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="confirmed=True 필수")
    # 수신자는 브라우저 작성창 안에 있어 여기서 알 수 없으므로 수신거부 대조는 못 한다 — 승인 문구만 확인.
    require_send_approval("mail_send", send_confirm=req.send_confirm, expected=HIWORKS_SEND_CONFIRM_TEXT)

    log_event(
        "HIWORKS_MAIL_SEND_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note="user confirmed send",
    )

    try:
        from scripts.hiworks.mail import send_mail
        from scripts.web_connector import get_page, run_on_browser_thread

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        result = run_on_browser_thread(lambda: send_mail(get_page()), timeout=120)
        if result.get("success"):
            log_event(
                "HIWORKS_MAIL_SEND_SUCCESS",
                task_id="-",
                actor=user["actor"],
                role=user["role"],
                decision="ok",
                note=f"detail={result.get('detail', '')}",
            )
            return {"ok": True, **result}
        raise HTTPException(status_code=500, detail=result.get("error_msg", "발송 실패"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("hiworks send error")
        raise HTTPException(status_code=500, detail=f"발송 오류: {e}") from e
