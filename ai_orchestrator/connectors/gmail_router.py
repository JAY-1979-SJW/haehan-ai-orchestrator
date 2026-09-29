"""Gmail 엔드포인트 (/api/v1/gmail/*).

- GET  /inbox           : Gmail API 수신 (OAuth2 credentials 필요)
- POST /collect         : 최근 메일 inbox 저장
- POST /compose         : Gmail 웹 작성 (브라우저 자동화, dry_run 지원)
- POST /reply           : 특정 메일에 회신 초안 작성 (dry_run 지원)
- POST /ai-draft-unread : 안 읽은 메일을 AI(헤드리스 Claude Code)로 요약+회신초안 생성 (읽기전용)
- POST /send            : 발송 (confirmed=True 필수, /compose 또는 /reply 다음에 호출)
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


class GmailReplyRequest(BaseModel):
    mail_index: int
    body: str
    reply_all: bool = False
    dry_run: bool = True


class GmailAiDraftRequest(BaseModel):
    limit: int = 5  # 처리할 안읽은 메일 수 상한(응답 파싱 안정성을 위해 작게 유지)


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


@gmail_router.post("/reply")
def api_reply(
    req: GmailReplyRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """특정 메일(mail_index, /ai-draft-unread 또는 GmailAPI.list_inbox 기준)에 회신 초안
    작성. dry_run=True(기본)면 브라우저 미실행. 실제 발송은 이 다음에 /send(confirmed=True)
    별도 호출 필요 — 이 엔드포인트 자체는 발송하지 않는다(GmailAPI.reply는 초안만 채움)."""
    log_event(
        "GMAIL_REPLY_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if req.dry_run else "pending_browser",
        note=f"mail_index={req.mail_index} dry_run={req.dry_run}",
    )

    if req.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "mail_index": req.mail_index,
            "body_preview": req.body[:200],
            "detail": "dry_run=True: 실행하려면 dry_run=False로 재요청",
            "requires_send_approval": True,
        }

    try:
        from scripts.google.gmail_api import GmailAPI
        from scripts.web_connector import get_page, run_on_browser_thread

        result = run_on_browser_thread(
            lambda: GmailAPI(get_page()).reply(req.mail_index, req.body, req.reply_all),
            timeout=60,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=f"회신 초안 작성 실패: {result.get('error')}")
        return {
            "ok": True,
            "dry_run": False,
            "mail_index": req.mail_index,
            "detail": "회신 초안 작성 완료 (발송하려면 /send 호출)",
            "requires_send_approval": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("gmail reply error")
        raise HTTPException(status_code=500, detail=f"Gmail 회신 실패: {e}")


@gmail_router.post("/ai-draft-unread")
def api_ai_draft_unread(
    req: GmailAiDraftRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """안 읽은 메일을 읽어 AI(run_claude_agent, 헤드리스 Claude Code)로 요약+회신초안 생성.

    읽기전용 — 이 엔드포인트는 발송 능력이 전혀 없다(local_agent.actions.action_run_claude_agent
    를 allowed_tools 없이 호출해 순수 텍스트 생성만 시킨다 — MCP 도구 호출 자체가 불가능한
    구조적 안전장치, 프롬프트 준수에 기대지 않음). 결과 초안은 /reply(dry_run) 로 미리보기 후
    /send(confirmed=True) 를 사람이 별도로 눌러야 실제 발송된다.
    """
    limit = max(1, min(req.limit, 10))
    t0 = time.monotonic()

    try:
        from scripts.google.gmail_api import GmailAPI
        from scripts.web_connector import get_page, run_on_browser_thread

        def _collect() -> list[dict]:
            g = GmailAPI(get_page())
            rows = g.list_inbox(limit=30)
            unread_rows = [r for r in rows if r.get("unread")][:limit]
            collected = []
            for r in unread_rows:
                detail = g.read(r["index"])
                if detail.get("ok"):
                    collected.append(
                        {
                            "mail_index": r["index"],
                            "from": detail.get("sender_preview") or r.get("from_preview", ""),
                            "subject": detail.get("subject_preview") or r.get("subject_preview", ""),
                            "body": detail.get("body_preview", ""),
                        }
                    )
            return collected

        mails = run_on_browser_thread(_collect, timeout=120)
    except Exception as e:
        logger.exception("gmail ai-draft collect error")
        raise HTTPException(status_code=500, detail=f"메일 수집 오류: {e}")

    if not mails:
        return {"ok": True, "items": [], "count": 0, "duration_ms": int((time.monotonic() - t0) * 1000)}

    import json as _json

    from local_agent.actions import action_run_claude_agent

    mail_block = "\n\n".join(
        f"[{m['mail_index']}] 발신: {m['from']}\n제목: {m['subject']}\n본문: {m['body'][:600]}" for m in mails
    )
    prompt = (
        "다음은 Gmail 안 읽은 메일 목록이다. 각 메일에 대해 1) 한국어 한 줄 요약, "
        "2) 회신이 필요한지(needs_reply), 3) 필요하면 정중한 한국어 회신 초안(3~5문장)을 작성해라. "
        "광고/뉴스레터/알림성 메일은 needs_reply=false, draft_reply는 빈 문자열로. "
        "다른 설명 없이 아래 JSON 배열 형식으로만 답하라(마크다운 코드블록 금지):\n"
        '[{"mail_index": 0, "summary": "...", "needs_reply": true, "draft_reply": "..."}]\n\n'
        f"{mail_block}"
    )

    result = action_run_claude_agent({"prompt": prompt, "timeout": 180, "max_budget_usd": 1.0})
    if not result.success:
        raise HTTPException(status_code=502, detail=f"AI 초안 생성 실패: {result.error}")

    raw = result.data.get("result", "")
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("[") : cleaned.rfind("]") + 1]
    try:
        drafts = _json.loads(cleaned)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"AI 응답 파싱 실패: {raw[:200]}")

    by_index = {m["mail_index"]: m for m in mails}
    items = []
    for d in drafts if isinstance(drafts, list) else []:
        idx = d.get("mail_index")
        base = by_index.get(idx, {})
        items.append(
            {
                "mail_index": idx,
                "from": base.get("from", ""),
                "subject": base.get("subject", ""),
                "summary": d.get("summary", ""),
                "needs_reply": bool(d.get("needs_reply")),
                "draft_reply": d.get("draft_reply", ""),
            }
        )

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "GMAIL_AI_DRAFT_UNREAD",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(items)} duration_ms={duration_ms} cost_usd={result.data.get('cost_usd')}",
    )
    return {"ok": True, "items": items, "count": len(items), "duration_ms": duration_ms}


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
