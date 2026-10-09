"""L8 — 하나팩스 API 라우터.

GET  /api/v1/hanafax/status          — 로그인 상태 + 잔액
GET  /api/v1/hanafax/queue           — 큐 목록 조회
POST /api/v1/hanafax/send            — 단건 팩스 발송 (승인 후)
POST /api/v1/hanafax/batch/plan      — 배치 dry-run 계획
POST /api/v1/hanafax/batch/execute   — 배치 실 발송 (승인 필수)

보안: 팩스 발송은 사용자 명시 승인 후에만 실행.
"""

from __future__ import annotations

import logging
import re
import sys

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ai_orchestrator.paths import repo_root
from tools.gates.auth import require_role
from tools.gates.send_approval import require_send_approval

from ..session_status_router import session_status_router  # noqa: F401 (side-effect import for type hints)

ROOT = repo_root()
sys.path.insert(0, str(ROOT))

hanafax_router = APIRouter(prefix="/hanafax", tags=["hanafax"])
logger = logging.getLogger(__name__)


def _failure_text(exc: Exception, what: str) -> str:
    """하나팩스 사이트를 읽다 난 예외를 사람이 알아볼 문장으로 바꾼다.

    브라우저(Playwright Chromium)가 설치되지 않은 PC 에서는 예외 이름이 그냥 'Error' 라 원인을 알 수 없었다
    (2026-10-04 앱 실검증: /status 는 500, /address-groups 는 "...: Error").
    """
    if "Executable doesn't exist" in str(exc):
        return f"{what}에 쓰는 브라우저(Playwright Chromium)가 이 PC 에 설치돼 있지 않습니다. 관리자가 설치해야 합니다 (playwright install chromium)."
    return f"{what} 실패: {type(exc).__name__}"


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
    confirmed: bool = False  # 사용자 명시 승인 필수
    # 사용자가 확인 단계에서 직접 입력한 승인 문구. 없거나 다르면 403.
    send_confirm: str | None = None


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

    try:
        result = test_login()
    except Exception as exc:  # noqa: BLE001 - 상태 조회는 브라우저 미설치·사이트 오류 등 어떤 실패든 500 대신 ok=False+사유 문구로 알리는 읽기 전용 점검 API(로그인 실패와 같은 규약), 발송·승인 판정과 무관
        logger.warning("하나팩스 상태 확인 실패: %s", exc)
        return HanafaxStatus(
            ok=False,
            message=_failure_text(exc, "하나팩스 상태 확인"),
            fax_number="",
            balance="",
            plan="",
            member_status="",
            new_fax_count="",
        )
    if not result["ok"]:
        return HanafaxStatus(
            ok=False, message=result["message"], fax_number="", balance="", plan="", member_status="", new_fax_count=""
        )
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
        return [
            QueueItem(
                receiver_fax=r.get("receiver_fax", ""),
                receiver_name=r.get("receiver_name", ""),
                subject=r.get("subject", ""),
                bid_name=r.get("bid_name", ""),
                status=r.get("status", "pending"),
            )
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@hanafax_router.post("/send", response_model=SendResponse)
def send_fax(body: SendRequest, _: dict = Depends(require_role("admin", "owner"))):
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="팩스 발송은 confirmed=true 승인이 필요합니다")
    from ai_orchestrator.connectors.hanafax import authorization_store as fax_store
    from ai_orchestrator.connectors.hanafax.send_policy import parse_number
    from tools.gates.gate_core import CONFIRM_TEXTS

    # 승인 문구(사용자가 직접 입력) → 번호 형식 → 수신거부 순으로 확인한다. 발송 전에 모두 끝낸다.
    require_send_approval("hanafax_send", send_confirm=body.send_confirm, expected=CONFIRM_TEXTS["hanafax_send"])
    digits = parse_number(body.receiver_fax)
    if digits is None:
        raise HTTPException(status_code=400, detail="수신 팩스번호 형식이 올바르지 않습니다")
    if digits in fax_store.opt_out_numbers():
        raise HTTPException(status_code=403, detail="수신거부 번호입니다")
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


# ── 자동 발송 승인서 (기준서: docs/specs/2026-10-02_hanafax_auto_send.md) ─────────────
# 승인서는 사람이 미리보기를 확인하고 승인해야 효력이 생기고, 승인 뒤에는 수정할 수 없다.


class FaxRecipient(BaseModel):
    fax: str
    name: str = ""


class AuthorizationCreate(BaseModel):
    name: str
    subject: str
    document_ref: str
    recipients: list[FaxRecipient] = []
    recipients_file: str | None = None  # 주소록 엑셀/CSV 경로 — 주면 수신자 목록 대신 파일에서 읽는다
    site_group: str | None = None  # 하나팩스 주소록 그룹 번호(intid) — 미리 '그룹 가져오기'를 해 둔 캐시에서 읽는다
    group_offset: int = 0  # 큰 그룹은 구간을 나눠 승인(시작 위치, 0부터)
    group_limit: int = 1000  # 한 번에 승인할 인원(최대 1000)
    exclude_already_sent: bool = True  # 예전 발송 이력에서 이미 성공한 번호 제외
    max_per_run: int | None = None  # 비우면 수신자 수만큼
    max_per_day: int | None = None
    max_total: int | None = None
    allowed_start: str = "09:00"
    allowed_end: str = "18:00"
    valid_from: str | None = None
    valid_until: str | None = None


class AuthorizationApprove(BaseModel):
    confirmed: bool = False
    start_now: bool = False  # 승인과 동시에 발송 시작(사용자가 한 번 승인하면 끝까지 자동)
    live: bool = False  # 기본 드라이런 — 실전송은 명시해야 한다


class KillSwitchRequest(BaseModel):
    on: bool


class ResolveRequest(BaseModel):
    fax: str
    outcome: str  # "sent"(실제로 발송됨) | "not_sent"(발송되지 않음)


class AttachmentCheck(BaseModel):
    path: str


class OptOutRequest(BaseModel):
    fax: str
    reason: str = ""


def _actor(user: dict) -> str:
    return str(user.get("actor") or user.get("username") or "admin")


def _auth_service():
    from ai_orchestrator.connectors.hanafax import authorization_service as service

    return service


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@hanafax_router.post("/attachments", response_model=dict)
def upload_attachment(file: UploadFile = File(...), _: dict = Depends(require_role("admin", "owner"))):
    """첨부 파일을 올려 앱 전용 폴더에 저장하고 경로를 돌려준다(pdf/docx/doc, 10MB 이하, 내용 검사)."""
    from ai_orchestrator.connectors.hanafax import attachments as limits

    data = file.file.read(limits.MAX_BYTES + 1)  # 한도 +1 바이트만 읽어 거대한 업로드가 메모리를 채우지 않게 한다
    try:
        return _auth_service().upload_attachment(file.filename or "", data)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.post("/attachments/check", response_model=dict)
def check_attachment(body: AttachmentCheck, _: dict = Depends(require_role("admin", "owner"))):
    """첨부 파일 경로를 미리 검사한다(허용 폴더·형식·크기·내용) — 승인서 만들 때와 같은 규칙."""
    try:
        return _auth_service().check_attachment(body.path)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/address-groups", response_model=list[dict])
def address_groups(_: dict = Depends(require_role("admin", "owner"))):
    """하나팩스 주소록 그룹 목록(이름·인원) — 읽기 전용."""
    try:
        return _auth_service().list_site_groups()
    except Exception as exc:  # 사이트 읽기 실패 사유를 알린다
        logger.warning("하나팩스 주소록 그룹 읽기 실패: %s", exc)
        raise HTTPException(status_code=502, detail=_failure_text(exc, "주소록 그룹 읽기")) from exc


@hanafax_router.post("/address-groups/{intid}/sync", response_model=dict)
def start_group_sync(intid: str, _: dict = Depends(require_role("admin", "owner"))):
    """그룹 연락처를 읽어 로컬 캐시에 둔다(백그라운드, 읽기 전용). 이후 승인서 생성에 site_group 으로 쓴다."""
    try:
        return _auth_service().start_group_sync(intid)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/address-groups/{intid}/sync", response_model=dict)
def group_sync_status(intid: str, _: dict = Depends(require_role("admin", "owner"))):
    try:
        return _auth_service().group_sync_status(intid)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.post("/authorizations", response_model=dict)
def create_authorization(body: AuthorizationCreate, user: dict = Depends(require_role("admin", "owner"))):
    service = _auth_service()
    try:
        row = service.create(body.model_dump(), user=_actor(user))
        return {**service.preview(row["id"]), "import_summary": row["import_summary"]}
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/authorizations", response_model=list[dict])
def list_authorizations(_: dict = Depends(require_role("admin", "owner"))):
    from ai_orchestrator.connectors.hanafax import authorization_store as fax_store

    return [
        {k: v for k, v in a.items() if k != "recipients"} | {"recipient_count": len(a["recipients"])}
        for a in fax_store.list_authorizations()
    ]


@hanafax_router.get("/authorizations/{auth_id}", response_model=dict)
def get_authorization(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    try:
        return _auth_service().preview(auth_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@hanafax_router.post("/authorizations/{auth_id}/approve", response_model=dict)
def approve_authorization(
    auth_id: str, body: AuthorizationApprove, user: dict = Depends(require_role("admin", "owner"))
):
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="승인은 confirmed=true (미리보기 확인 후)가 필요합니다")
    try:
        service = _auth_service()
        service.approve(auth_id, user=_actor(user), live=body.live)
        if body.start_now:
            service.run_now(auth_id)
        return service.preview(auth_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.post("/authorizations/{auth_id}/revoke", response_model=dict)
def revoke_authorization(auth_id: str, user: dict = Depends(require_role("admin", "owner"))):
    try:
        service = _auth_service()
        service.revoke(auth_id, user=_actor(user))
        return service.preview(auth_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@hanafax_router.post("/authorizations/{auth_id}/run", response_model=dict)
def run_authorization(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    """승인된 승인서를 지금 발송한다(백그라운드). 승인 전·취소·정지 상태면 정책이 거부한다."""
    try:
        return _auth_service().run_now(auth_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/authorizations/{auth_id}/run", response_model=dict)
def run_status(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    return _auth_service().run_status(auth_id)


@hanafax_router.post("/authorizations/{auth_id}/preview", response_model=dict)
def start_preview(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    """하나팩스 접수 화면에 채워 보는 미리보기를 만든다(백그라운드, 전송하지 않음). 보기는 사용자의 선택."""
    try:
        return _auth_service().start_preview(auth_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/authorizations/{auth_id}/preview", response_model=dict)
def preview_status(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    return _auth_service().preview_status(auth_id)


@hanafax_router.get("/authorizations/{auth_id}/preview.png")
def preview_image(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    from fastapi.responses import FileResponse

    path = _auth_service().preview_image_path(auth_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="미리보기 이미지가 없습니다")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@hanafax_router.get("/kill-switch", response_model=dict)
def kill_switch_state(_: dict = Depends(require_role("admin", "owner"))):
    from ai_orchestrator.connectors.hanafax import authorization_store as fax_store

    return {"kill_switch": fax_store.kill_switch_on()}


@hanafax_router.post("/authorizations/{auth_id}/reconcile", response_model=dict)
def start_reconcile(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    """하나팩스 전송결과와 대조해 접수된 건의 최종 성공/실패를 확정한다(읽기 전용, 백그라운드)."""
    try:
        return _auth_service().start_reconcile(auth_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/authorizations/{auth_id}/reconcile", response_model=dict)
def reconcile_status(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    return _auth_service().reconcile_status(auth_id)


@hanafax_router.post("/authorizations/{auth_id}/resolve", response_model=dict)
def resolve_pending(auth_id: str, body: ResolveRequest, user: dict = Depends(require_role("admin", "owner"))):
    """'확인 필요' 번호를 사람이 하나팩스 발송 내역에서 확인한 뒤 해소한다(발송됨/발송되지 않음)."""
    try:
        return _auth_service().resolve_pending(auth_id, body.fax, body.outcome, user=_actor(user))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.get("/authorizations/{auth_id}/log", response_model=list[dict])
def authorization_log(auth_id: str, _: dict = Depends(require_role("admin", "owner"))):
    return _auth_service().send_log(auth_id)


@hanafax_router.post("/kill-switch", response_model=dict)
def kill_switch(body: KillSwitchRequest, user: dict = Depends(require_role("admin", "owner"))):
    """전역 정지 — 켜면 모든 자동 발송이 즉시 멈춘다."""
    return _auth_service().set_kill_switch(body.on, user=_actor(user))


@hanafax_router.post("/opt-out", response_model=dict)
def add_opt_out(body: OptOutRequest, user: dict = Depends(require_role("admin", "owner"))):
    try:
        return {"masked": _auth_service().add_opt_out(body.fax, reason=body.reason, user=_actor(user))}
    except ValueError as exc:
        raise _bad_request(exc) from exc


@hanafax_router.post("/batch/plan", response_model=BatchPlan)
def batch_plan(body: BatchExecuteRequest, _: dict = Depends(require_role("admin", "owner"))):
    from scripts.hanafax.batch import build_batch_plan

    plan = build_batch_plan(limit=body.limit, delay_seconds=body.delay_seconds)
    items = [
        BatchPlanItem(
            index=i + 1,
            receiver_fax=r.get("receiver_fax", ""),
            receiver_name=r.get("receiver_name", ""),
            subject=r.get("subject", ""),
        )
        for i, r in enumerate(plan.get("items", []))
    ]
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
