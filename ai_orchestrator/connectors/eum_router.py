"""EUM 영업메일 엔드포인트 (/api/v1/eum/*).

흐름: 신규현장(WEBMAN370M00) 전수 수집 → 영업메일 타겟 선별/초안 생성 → 하이웍스로 1건씩 발송.
발송은 confirmed=True 필수 (외부 메일 — 자동 일괄발송 금지, 1건씩 승인).

L8 Server API 계층. 실제 수집/메일 로직은 scripts/eum, scripts/hiworks 에 위임.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

eum_router = APIRouter(prefix="/eum", tags=["eum"])

_ROOT = Path(__file__).resolve().parents[2]
_TARGETS_LATEST = _ROOT / "data" / "eum_sales_mail_targets_latest.json"


def _ensure_root_on_path() -> None:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


class CollectRequest(BaseModel):
    max_pages: int = 20


class SendRequest(BaseModel):
    to: str
    subject: str
    body: str
    confirmed: bool = False


@eum_router.post("/sales-mail/collect")
def collect_and_prepare(
    req: CollectRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """신규현장 전수 수집(WEBMAN370M00) + 영업메일 타겟 선별/초안 생성.

    EUM 로그인 세션(CDP)이 있어야 한다. 표시개수 100 + 페이지네이션으로 전수 수집.
    """
    t0 = time.monotonic()
    try:
        _ensure_root_on_path()
        from scripts.eum.install_targets import collect_all_install_targets
        from scripts.eum.sales_mail import prepare_sales_mail
        from scripts.site_access import open_site

        page = open_site("eum")
        collected = collect_all_install_targets(page, max_pages=req.max_pages)
        prep = prepare_sales_mail()
        log_event(
            "EUM_SALES_COLLECT",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"sites={collected.get('total')} targets={prep.get('selected_targets')}",
        )
        return {
            "ok": True,
            "collected_sites": collected.get("total", 0),
            "pages_visited": collected.get("pages_visited", 0),
            "eligible_targets": prep.get("eligible_targets", 0),
            "selected_targets": prep.get("selected_targets", 0),
            "duration_ms": int((time.monotonic() - t0) * 1000),
        }
    except Exception as e:
        logger.exception("eum collect error")
        raise HTTPException(status_code=500, detail=f"EUM 수집 실패: {e}")


@eum_router.get("/sales-mail/targets")
def get_targets(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """선별된 영업메일 타겟 + 초안 조회 (최신 준비 결과)."""
    if not _TARGETS_LATEST.exists():
        return {"ok": False, "error": "no_data", "hint": "먼저 수집(collect) 실행", "targets": []}
    try:
        data = json.loads(_TARGETS_LATEST.read_text(encoding="utf-8"))
        targets = data.get("targets", []) if isinstance(data, dict) else (data or [])
        return {
            "ok": True,
            "targets": targets,
            "count": len(targets),
            "prepared_at": data.get("timestamp", "") if isinstance(data, dict) else "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"타겟 로드 실패: {e}")


@eum_router.post("/sales-mail/send")
def send_one(
    req: SendRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """영업메일 1건 하이웍스 발송. confirmed=True 필수 (오발송 방지)."""
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="confirmed=True 필수 (외부 메일 — 1건씩 승인 발송)")
    if not req.to or "@" not in req.to:
        raise HTTPException(status_code=400, detail="수신 이메일이 올바르지 않습니다")
    try:
        _ensure_root_on_path()
        from scripts.hiworks.mail import fill_compose, send_mail
        from scripts.web_connector import get_page

        page = get_page()
        fill_compose(page, to=req.to, subject=req.subject, body=req.body)
        result = send_mail(page)
        ok = bool(result.get("success"))
        log_event(
            "EUM_SALES_MAIL_SEND",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok" if ok else "error",
            note=f"to={req.to} subject={req.subject[:30]}",
        )
        if ok:
            return {"ok": True, "to": req.to, **result}
        raise HTTPException(status_code=500, detail=result.get("error_msg", "발송 실패"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("eum send error")
        raise HTTPException(status_code=500, detail=f"발송 오류: {e}")
