"""L8 — 하나팩스 API 라우터.

GET  /api/v1/hanafax/status          — 로그인 상태 + 잔액
GET  /api/v1/hanafax/queue           — 큐 목록 조회
POST /api/v1/hanafax/send            — 단건 팩스 발송 (승인 후)
POST /api/v1/hanafax/batch/plan      — 배치 dry-run 계획
POST /api/v1/hanafax/batch/execute   — 배치 실 발송 (승인 필수)

보안: 팩스 발송은 사용자 명시 승인 후에만 실행.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .session_status_router import session_status_router  # noqa: F401 (side-effect import for type hints)
from ..auth import require_role

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

hanafax_router = APIRouter(prefix="/hanafax", tags=["hanafax"])


# ── 모델 ─────────────────────────────────────────────────────────────────────

class HanafaxStatus(BaseModel):
    ok: bool
    message: str
    fax_number: str
    balance: str
    plan: str
    member_status: str
    new_fax_count: str


class QueueItem(BaseModel):
    receiver_fax: str
    receiver_name: str
    subject: str
    bid_name: str
    status: str


class SendRequest(BaseModel):
    receiver_fax: str
    subject: str
    body: str
    receiver_name: str = ""
    confirmed: bool = False   # 사용자 명시 승인 필수


class SendResponse(BaseModel):
    ok: bool
    message: str
    job_id: str | None = None
    simulated: bool = False


class BatchPlanItem(BaseModel):
    index: int
    receiver_fax: str
    receiver_name: str
    subject: str


class BatchPlan(BaseModel):
    total: int
    items: list[BatchPlanItem]
    dry_run: bool


class BatchExecuteRequest(BaseModel):
    confirmed: bool = False
    confirm_text: str = ""
    limit: int = 10
    delay_seconds: int = 30


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _parse_status(info: str) -> dict:
    """하나팩스 info 텍스트에서 주요 정보 추출."""
    def _find(keywords: list[str]) -> str:
        for kw in keywords:
            for line in info.splitlines():
                if kw in line:
                    return line.strip()
        return ""

    fax_line = _find(["02-", "031-", "032-", "051-", "053-", "062-", "042-", "0"])
    # 팩스번호 패턴 추출
    fax_match = re.search(r"0\d{1,2}-\d{3,4}-\d{4}", info)
    fax_number = fax_match.group(0) if fax_match else ""

    balance_match = re.search(r"전송잔액\s*[ㅣ|]\s*([\d,]+)원", info)
    balance = balance_match.group(1) + "원" if balance_match else ""

    plan_match = re.search(r"요금제\s*[ㅣ|]\s*([^\n]+)", info)
    plan = plan_match.group(1).strip() if plan_match else ""

    status_match = re.search(r"회원상태\s*[ㅣ|]\s*([^\n]+)", info)
    member_status = status_match.group(1).strip() if status_match else ""

    fax_count_match = re.search(r"새팩스\s*[ㅣ|]\s*(\d+)건", info)
    new_fax_count = fax_count_match.group(1) + "건" if fax_count_match else "0건"

    return {
        "fax_number": fax_number,
        "balance": balance,
        "plan": plan,
        "member_status": member_status,
        "new_fax_count": new_fax_count,
    }


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@hanafax_router.get("/status", response_model=HanafaxStatus)
def get_status(_: dict = Depends(require_role("admin", "owner"))):
    from scripts.hanafax.auth import test_login
    result = test_login()
    if not result["ok"]:
        return HanafaxStatus(ok=False, message=result["message"],
                             fax_number="", balance="", plan="", member_status="", new_fax_count="")
    info = result.get("info", "")
    parsed = _parse_status(info)
    return HanafaxStatus(ok=True, message="로그인 성공", **parsed)


@hanafax_router.get("/queue", response_model=list[QueueItem])
def get_queue(_: dict = Depends(require_role("admin", "owner"))):
    from scripts.hanafax.batch import DEFAULT_QUEUE, load_queue
    if not DEFAULT_QUEUE.exists():
        return []
    try:
        rows = load_queue(limit=50)
        return [QueueItem(
            receiver_fax=r.get("receiver_fax", ""),
            receiver_name=r.get("receiver_name", ""),
            subject=r.get("subject", ""),
            bid_name=r.get("bid_name", ""),
            status=r.get("status", "pending"),
        ) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hanafax_router.post("/send", response_model=SendResponse)
def send_fax(body: SendRequest, _: dict = Depends(require_role("admin", "owner"))):
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="팩스 발송은 confirmed=true 승인이 필요합니다")
    from scripts.hanafax.sender import send_fax as _send
    result = _send(
        receiver_fax=body.receiver_fax,
        subject=body.subject,
        body=body.body,
        receiver_name=body.receiver_name,
    )
    return SendResponse(
        ok=result["success"],
        message=result["message"],
        job_id=result.get("job_id"),
        simulated=result.get("simulated", False),
    )


@hanafax_router.post("/batch/plan", response_model=BatchPlan)
def batch_plan(body: BatchExecuteRequest, _: dict = Depends(require_role("admin", "owner"))):
    from scripts.hanafax.batch import build_batch_plan
    plan = build_batch_plan(limit=body.limit, delay_seconds=body.delay_seconds)
    items = [BatchPlanItem(
        index=i + 1,
        receiver_fax=r.get("receiver_fax", ""),
        receiver_name=r.get("receiver_name", ""),
        subject=r.get("subject", ""),
    ) for i, r in enumerate(plan.get("queue", []))]
    return BatchPlan(total=len(items), items=items, dry_run=True)


@hanafax_router.post("/batch/execute", response_model=dict)
def batch_execute(body: BatchExecuteRequest, _: dict = Depends(require_role("admin", "owner"))):
    from scripts.hanafax.batch import APPROVAL_CONFIRM_TEXT, build_batch_plan, execute_batch
    if not body.confirmed or body.confirm_text != APPROVAL_CONFIRM_TEXT:
        raise HTTPException(
            status_code=400,
            detail=f"실 발송은 confirmed=true + confirm_text='{APPROVAL_CONFIRM_TEXT}' 필요",
        )
    plan = build_batch_plan(limit=body.limit, delay_seconds=body.delay_seconds)
    result = execute_batch(plan)
    return {"ok": True, "sent": result.get("sent", 0), "failed": result.get("failed", 0)}
