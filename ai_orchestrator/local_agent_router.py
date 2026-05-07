"""로컬 에이전트 등록·조회·작업 큐 API (Stage 1/2).

엔드포인트:
  POST /api/v1/local-agents/register                    (admin/owner)
  GET  /api/v1/local-agents                             (admin/owner/viewer)
  POST /api/v1/local-agents/{agent_id}/tasks            (admin/owner)
  GET  /api/v1/local-agents/{agent_id}/tasks            (admin/owner/viewer)
  GET  /api/v1/local-agents/{agent_id}/tasks/{task_id}  (admin/owner/viewer)
  WS   /api/v1/local-agents/ws                          (device_token 인증)

작업 흐름:
  - low + 서버 자동완료 (ping/system_info/list_allowed_apps) → status=completed
  - low + PC 의존 (open_url) → status=queued → (WS) delivered → running → completed/failed
  - medium (list_files_readonly) → status=queued → (WS) delivered → running → completed/failed
  - high (capture_screenshot) → issue_token_for_dev_reg + status=waiting_approval
    (Stage 2 에서도 실제 실행은 하지 않음 — 에이전트가 NOT_IMPLEMENTED_STAGE2 반환)

보안:
  - device_token 원문은 register 응답에 1회만 노출
  - params 의 민감 키는 등록 시점에 제거 (registry._strip_sensitive)
  - audit log 에 token 원문 / device_token 원문 절대 기록 금지
  - WS 인증 실패는 로그에 agent_id / 원인 코드만, token 원문은 기록/반영 금지
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Query,
    WebSocket, WebSocketDisconnect,
)
from pydantic import BaseModel

from .auth import require_role
from .audit_logger import log_event
from .approval import issue_token_for_dev_reg, approve_token, reject_token
from . import local_agent_registry as _reg
from . import local_agent_diagnostics
from . import registration_codes as _regcodes
from . import local_agent_audit_builders as _audit
from . import local_agent_router_guards as _guards
from . import local_agent_audit_event_policy as _policy

try:
    from .browser_tool.local_agent_user_present_status_handler import (
        handle_user_present_status_event as _handle_up_status_event,
    )
    _UP_STATUS_HANDLER_AVAILABLE = True
except ImportError:
    _UP_STATUS_HANDLER_AVAILABLE = False

logger = logging.getLogger(__name__)

local_agent_router = APIRouter(prefix="/local-agents", tags=["local-agents"])


# ── 요청 모델 ────────────────────────────────────────────────────────────

class AgentRegisterRequest(BaseModel):
    host: str = ""
    os_name: str = ""
    version: str = "0.1.0"


class AgentTaskRequest(BaseModel):
    action: str
    params: dict = {}


class AgentTaskApprovalRequest(BaseModel):
    token_id: str
    reason: str = ""


class CancelTaskRequest(BaseModel):
    reason: str = ""


class IssueRegistrationCodeRequest(BaseModel):
    label: str
    expires_in_minutes: int = _regcodes.DEFAULT_TTL_MINUTES
    allowed_actions: list[str] = []
    note: str = ""
    smoke_test: bool = False  # smoke test marker for cleanup eligibility


class RegisterWithCodeRequest(BaseModel):
    registration_code: str
    host: str = ""
    os_name: str = ""
    version: str = "0.1.0"


class CaptureScreenshotRequest(BaseModel):
    """운영자 capture_screenshot 요청 body.

    - dry_run 기본값은 True. 생략/빈 body/{} 는 모두 dry_run=True 로 처리.
    - dry_run=False 는 명시적으로 false 를 전달한 경우에만 적용.
    - reason/note 는 감사 메모용 텍스트 (민감값 제거 로직을 거친 뒤 저장).
    """
    dry_run: bool = True
    reason: str = ""
    note: str = ""


def _capture_approval_note(task, agent_id: str, dry_run: bool) -> str:
    """CAPTURE_SCREENSHOT_APPROVAL_REQUESTED audit 용 note — reason/note 축약 포함.

    token 원문 / 파일명 / 전체 경로는 포함하지 않는다. reason/note 는 이미
    enqueue_task 단계에서 민감값 제거 후 저장되며, 본 함수는 추가 축약만 한다.
    """
    parts = [f"agent_id={agent_id}", f"dry_run={dry_run}"]
    try:
        params = task.params if task is not None else None
    except Exception:
        params = None
    if isinstance(params, dict):
        raw_reason = params.get("reason")
        if raw_reason:
            parts.append(f"reason={str(raw_reason)[:100]}")
        raw_note = params.get("note")
        if raw_note:
            parts.append(f"note={str(raw_note)[:100]}")
    return " ".join(parts)


# ── HTTP 라우트 ──────────────────────────────────────────────────────────

@local_agent_router.post("/register")
def register_local_agent(
    body: AgentRegisterRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """새 로컬 에이전트 등록. agent_id + device_token 발급.

    device_token 은 응답에 1회만 노출되며 서버는 SHA-256 해시만 저장한다.
    """
    actor = user["actor"]
    role = user["role"]
    result = _reg.register_agent(
        host=body.host, os_name=body.os_name, version=body.version,
        requested_by=actor,
    )

    # 감사 로그: token 원문 / 해시 모두 기록 금지. token_hash prefix 만 식별자로.
    log_event(
        "LOCAL_AGENT_REGISTERED", result.agent.agent_id,
        actor=actor, role=role,
        note=f"host={result.agent.host} os={result.agent.os_name} "
             f"ver={result.agent.version}",
    )

    return {
        "agent_id": result.agent.agent_id,
        "device_token": result.device_token,  # 1회 노출, 클라이언트 책임 보관
        "host": result.agent.host,
        "os_name": result.agent.os_name,
        "version": result.agent.version,
        "registered_at": result.agent.registered_at,
    }


# ── registration-code (REGCODE-1) ───────────────────────────────────────

# allowed_actions 검증: ACTION_RISK 키 중 high-risk 직접 실행계열은 제외.
# (open_url_execute 는 별도 승인 흐름 — 등록코드 scope 에 직접 부여 금지)
_REGCODE_ALLOWED_ACTIONS: frozenset[str] = frozenset(
    set(_reg.ACTION_RISK.keys()) - {"open_url_execute"}
)


@local_agent_router.post("/registration-codes")
def issue_registration_code(
    body: IssueRegistrationCodeRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """admin/owner 가 1회용 등록코드 발급.

    응답에 registration_code 평문은 1회만 노출되며, 이후 어떤 조회 endpoint
    에서도 평문을 반환하지 않는다. 서버는 SHA-256(salt+code) 만 영속화한다.
    """
    actor = user["actor"]
    role = user["role"]

    # allowed_actions 검증 — 미등록 액션은 400.
    invalid = [a for a in (body.allowed_actions or [])
               if str(a).strip().lower() not in _REGCODE_ALLOWED_ACTIONS]
    if invalid:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_ALLOWED_ACTIONS",
            "message": f"unsupported actions: {invalid}",
        })

    try:
        result = _regcodes.issue_code(
            label=body.label,
            expires_in_minutes=body.expires_in_minutes,
            allowed_actions=body.allowed_actions,
            note=body.note,
            issued_by=actor,
            issuer_role=role,
            smoke_test=body.smoke_test,
        )
    except _regcodes.InvalidTTLError as e:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_TTL", "message": str(e),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_REQUEST", "message": str(e),
        })

    # 감사 로그 — code 원문/hash/salt 절대 기록 금지. code_id 만.
    log_event(
        "REGISTRATION_CODE_ISSUED", result.code.code_id,
        actor=actor, role=role,
        note=f"label={result.code.label} expires_at={result.code.expires_at} "
             f"actions={','.join(result.code.allowed_actions) or '-'}",
    )

    return {
        "code_id": result.code.code_id,
        "registration_code": result.registration_code,  # 1회 노출
        "label": result.code.label,
        "allowed_actions": list(result.code.allowed_actions),
        "expires_at": result.code.expires_at,
        "created_at": result.code.created_at,
        "smoke_test": result.code.smoke_test,
    }


@local_agent_router.get("/registration-codes")
def list_registration_codes(
    user: dict = Depends(require_role("admin", "owner")),
):
    """등록코드 목록. 평문/hash/salt 노출 금지."""
    return {"codes": _regcodes.list_codes()}


@local_agent_router.post("/registration-codes/{code_id}/revoke")
def revoke_registration_code(
    code_id: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    actor = user["actor"]
    role = user["role"]
    rec = _regcodes.revoke_code(code_id, actor=actor)
    if rec is None:
        raise HTTPException(status_code=404, detail={
            "code": "NOT_FOUND", "message": "registration_code not found",
        })
    log_event(
        "REGISTRATION_CODE_REVOKED", code_id,
        actor=actor, role=role,
        note=f"label={rec.label}",
    )
    return rec.to_safe()


@local_agent_router.post("/register-with-code")
def register_with_code(body: RegisterWithCodeRequest):
    """Basic Auth 없이 1회용 등록코드로 agent 등록.

    실패는 모두 400 + generic message — 외부에서 만료/사용/폐기/오타를
    구분할 수 없게 한다. audit 에는 reason 분류만 별도 기록.
    """
    try:
        rec = _regcodes.consume_code(body.registration_code)
    except _regcodes.CodeExchangeError as e:
        # audit 에는 reason 만, code 원문은 절대 기록 금지.
        log_event(
            "REGISTRATION_CODE_EXCHANGE_FAILED", "-",
            actor="agent", role="-",
            decision=e.reason,
            note="register-with-code rejected",
        )
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_REGISTRATION_CODE",
            "message": _regcodes.INVALID_CODE_MESSAGE,
        })

    result = _reg.register_agent(
        host=body.host, os_name=body.os_name, version=body.version,
        requested_by=f"registration_code:{rec.code_id}",
        smoke_test=rec.smoke_test,
    )
    _regcodes.attach_used_agent(rec.code_id, result.agent.agent_id)

    log_event(
        "REGISTRATION_CODE_USED", rec.code_id,
        actor="agent", role="-",
        note=f"agent_id={result.agent.agent_id} label={rec.label}",
    )
    log_event(
        "LOCAL_AGENT_REGISTERED", result.agent.agent_id,
        actor=f"registration_code:{rec.code_id}", role="-",
        note=f"host={result.agent.host} os={result.agent.os_name} "
             f"ver={result.agent.version}",
    )

    return {
        "agent_id": result.agent.agent_id,
        "device_token": result.device_token,  # 1회 노출
        "host": result.agent.host,
        "os_name": result.agent.os_name,
        "version": result.agent.version,
        "registered_at": result.agent.registered_at,
        "code_id": rec.code_id,
        "label": rec.label,
        "allowed_actions": list(rec.allowed_actions),
        "smoke_test": result.agent.smoke_test,
    }


@local_agent_router.get("")
def list_local_agents(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    return {"agents": _reg.list_agents()}


@local_agent_router.get("/diagnostics")
def get_local_agents_diagnostics(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    """Local agent 운영 진단 정보 (read-only).

    agent/task 상태 집계, 민감정보 제외 (token_id, raw params, raw audit, raw html/url/secret 등).
    allowlist field만 반환 (counts, status, timestamps).
    """
    with _reg._lock:
        diagnostics = local_agent_diagnostics.build_local_agent_diagnostics()
    return diagnostics


@local_agent_router.post("/{agent_id}/tasks")
def submit_local_agent_task(
    agent_id: str,
    body: AgentTaskRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """로컬 에이전트에게 작업 큐잉.

    - 미등록 agent_id → 404
    - 미등록 액션(delete_file/upload_file/modify_file/execute_shell …) → 400
    - high risk → 승인 토큰 발행 + status=waiting_approval
    """
    actor = user["actor"]
    role = user["role"]

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type=body.action, actor=actor, role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND",
                    "message": f"미등록 에이전트: {agent_id}"},
        )

    try:
        task = _reg.enqueue_task(
            agent_id=agent_id,
            action=body.action,
            params=body.params,
            requested_by=actor,
        )
    except _reg.UnknownActionError as e:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type=str(body.action), actor=actor, role=role,
            note=f"agent_id={agent_id} reason=UNKNOWN_ACTION",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_ACTION", "message": str(e)},
        )

    # high risk → 승인 토큰 발행 + waiting_approval 이벤트
    if task.risk_level == "high":
        token = issue_token_for_dev_reg(
            task_id=task.task_id,
            requested_by=actor,
            risk_level=task.risk_level,
            ttl_minutes=30,
        )
        _reg.attach_token(task.task_id, token.token_id, token.public_id)
        log_event(
            "LOCAL_AGENT_TASK_WAITING_APPROVAL", task.task_id,
            risk_level=task.risk_level,
            action_type=task.action,
            actor=actor, role=role,
            token_id=token.token_id,
            note=f"agent_id={agent_id}",
        )
        if _guards.is_capture_screenshot_task(task):
            log_event(
                "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED", task.task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor, role=role,
                token_id=token.token_id,
                note=_capture_approval_note(
                    task, agent_id, _guards.task_is_dry_run(task),
                ),
            )
    else:
        log_event(
            "LOCAL_AGENT_TASK_QUEUED", task.task_id,
            risk_level=task.risk_level,
            action_type=task.action,
            actor=actor, role=role,
            note=f"agent_id={agent_id} status={task.status}",
        )
        if task.status == "completed":
            log_event(
                "LOCAL_AGENT_TASK_COMPLETED", task.task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor="system",
                note=f"agent_id={agent_id}",
            )

    return _reg.get_task(agent_id, task.task_id).to_safe()


@local_agent_router.post("/{agent_id}/capture-screenshot")
def create_capture_screenshot_request(
    agent_id: str,
    body: CaptureScreenshotRequest | None = Body(default=None),
    user: dict = Depends(require_role("admin", "owner")),
):
    """운영자가 생성하는 capture_screenshot 요청 진입점.

    동작:
      - body 누락 / {} / reason 만 포함 → dry_run=True (기본값).
      - dry_run=False 는 body 에 명시적으로 false 를 담은 경우에만 적용되고,
        task 는 기존대로 waiting_approval 상태로 시작 + 승인 토큰 발행.
      - params.options.dry_run 에만 값을 저장하고, reason/note 는 별도 키로
        enqueue_task 의 민감값 제거 필터를 거친 뒤 보존된다.

    응답:
      task_id / agent_id / action / status / dry_run / approval_required 만 포함.
      승인 토큰 원문, device_token, 로컬 경로, 이미지 파일명 등은 절대 포함하지 않는다.
    """
    actor = user["actor"]
    role = user["role"]
    req = body if body is not None else CaptureScreenshotRequest()
    dry_run = bool(req.dry_run)

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type="capture_screenshot", actor=actor, role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND",
                    "message": f"미등록 에이전트: {agent_id}"},
        )

    # reason/note 는 메모용 텍스트로만 보관. 길이를 제한해 로그 비대화를 방지.
    params: dict = {"options": {"dry_run": dry_run}}
    if req.reason:
        params["reason"] = req.reason[:200]
    if req.note:
        params["note"] = req.note[:500]

    task = _reg.enqueue_task(
        agent_id=agent_id,
        action="capture_screenshot",
        params=params,           # _strip_sensitive 는 enqueue_task 내부에서 적용
        requested_by=actor,
    )

    # 운영자 요청임을 명시하는 감사 이벤트 — approval token 원문/전체 경로/파일명
    # 어느 것도 기록하지 않는다.
    log_event(
        "CAPTURE_SCREENSHOT_REQUEST_CREATED", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        note=(f"agent_id={agent_id} dry_run={dry_run}"
              + (f" reason={req.reason[:100]}" if req.reason else "")),
    )

    # 기존 승인 흐름 재사용 — 토큰 발행 + 기존 감사 이벤트(두 종) 그대로.
    token = issue_token_for_dev_reg(
        task_id=task.task_id,
        requested_by=actor,
        risk_level=task.risk_level,
        ttl_minutes=30,
    )
    _reg.attach_token(task.task_id, token.token_id, token.public_id)
    log_event(
        "LOCAL_AGENT_TASK_WAITING_APPROVAL", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        token_id=token.token_id,
        note=f"agent_id={agent_id}",
    )
    log_event(
        "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        token_id=token.token_id,
        note=_capture_approval_note(task, agent_id, dry_run),
    )

    return {
        "task_id": task.task_id,
        "agent_id": agent_id,
        "action": "capture_screenshot",
        "status": "waiting_approval",
        "dry_run": dry_run,
        "approval_required": True,
    }


class OpenUrlExecuteRequest(BaseModel):
    """승인형 actual open_url 실행 요청 body.

    - url: 열 URL (http/https 만 허용, query string 은 저장 시 제거)
    - reason: 감사 메모용 텍스트
    dry_run=false 직접 open_url 요청은 별도 endpoint 로 거부된다.
    이 endpoint 를 통해서만 open_url_execute task 가 생성된다.
    """
    url: str
    reason: str = ""


@local_agent_router.post("/{agent_id}/open-url-execution-request")
def create_open_url_execute_request(
    agent_id: str,
    body: OpenUrlExecuteRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """운영자가 승인형 actual open_url 실행을 요청하는 진입점.

    동작:
      - open_url_execute task 를 waiting_approval 상태로 생성.
      - approval token 발행 + task 에 attach.
      - 승인 전에는 agent 에 deliver 되지 않음.
      - URL query string 은 저장/응답 시 제거.
      - token 원문은 응답에 포함하지 않음.
    """
    from urllib.parse import urlparse, urlunparse

    actor = user["actor"]
    role = user["role"]

    url = (body.url or "").strip()
    if not url:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_URL", "message": "url 은 필수입니다"},
        )

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "URL_SCHEME_NOT_ALLOWED",
                "message": f"http/https 만 허용됩니다: {parsed.scheme!r}",
            },
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_URL", "message": "유효하지 않은 URL"},
        )

    # query string 제거 후 normalized URL 만 저장
    normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    agent = _reg.get_agent(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND", "message": f"agent_id={agent_id}"},
        )

    task = _reg.enqueue_task(
        agent_id=agent_id,
        action="open_url_execute",
        params={"url": normalized_url},
        requested_by=actor,
    )

    token = issue_token_for_dev_reg(
        task_id=task.task_id,
        requested_by=actor,
        risk_level=task.risk_level,
        ttl_minutes=30,
    )
    _reg.attach_token(task.task_id, token.token_id, token.public_id)

    log_event(
        "LOCAL_AGENT_TASK_WAITING_APPROVAL", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        token_id=token.token_id,
        note=(
            f"agent_id={agent_id} url_host={parsed.netloc}"
            + (f" reason={body.reason[:100]}" if body.reason else "")
        ),
    )
    log_event(
        "OPEN_URL_EXECUTE_APPROVAL_REQUESTED", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        token_id=token.token_id,
        note=f"agent_id={agent_id} url_host={parsed.netloc} normalized_url={normalized_url}",
    )

    return {
        "task_id": task.task_id,
        "agent_id": agent_id,
        "action": "open_url_execute",
        "status": "waiting_approval",
        "url_host": parsed.netloc,
        "approval_required": True,
    }


_CANCEL_REASON_MAX_LEN = 200


@local_agent_router.post("/{agent_id}/tasks/{task_id}/cancel")
def cancel_local_agent_task(
    agent_id: str,
    task_id: str,
    body: CancelTaskRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """task 취소.

    - queued / waiting_approval → 즉시 cancelled
    - delivered / running → cancel_requested (agent에 취소 신호 필요)
    - completed / failed / rejected / cancelled / cancel_requested → 409
    - reason > 200자 → 400
    """
    actor = user["actor"]
    role = user["role"]
    reason = body.reason or ""

    if len(reason) > _CANCEL_REASON_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail={"error": "REASON_TOO_LONG",
                    "message": f"reason 은 최대 {_CANCEL_REASON_MAX_LEN}자입니다"},
        )

    # 취소 전 현재 상태 보존 (audit용)
    existing = _reg.get_task(agent_id, task_id)
    if existing is None:
        log_event(
            "LOCAL_AGENT_TASK_CANCEL_REQUESTED", task_id,
            actor=actor, role=role,
            note=f"agent_id={agent_id} reason=TASK_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    previous_status = existing.status

    try:
        task, cancel_action = _reg.cancel_task(
            agent_id, task_id,
            actor=actor,
            reason=reason,
        )
    except _reg.CancelNotAllowedError as e:
        raise HTTPException(
            status_code=409,
            detail={"error": "CANCEL_NOT_ALLOWED", "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND", "message": str(e)},
        )

    audit_event = (
        "LOCAL_AGENT_TASK_CANCELLED"
        if cancel_action == "cancelled"
        else "LOCAL_AGENT_TASK_CANCEL_REQUESTED"
    )
    log_event(
        audit_event, task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        note=(
            f"agent_id={agent_id}"
            f" previous_status={previous_status}"
            f" next_status={task.status}"
            f" requested_by={actor}"
            f" reason_len={len(reason)}"
        ),
    )

    return {
        "task": task.to_safe(),
        "cancel_action": cancel_action,
    }


@local_agent_router.post("/{agent_id}/tasks/{task_id}/approve")
def approve_local_agent_task(
    agent_id: str,
    task_id: str,
    body: AgentTaskApprovalRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """high risk 작업(capture_screenshot 등)을 승인하여 queued 로 전환.

    - ApprovalToken 검증 → approve_token()
    - waiting_approval → queued (registry.mark_approved)
    - 이미 결정된 작업은 현재 상태를 그대로 반환 (재승인 방지).
    """
    actor = user["actor"]
    role = user["role"]
    token_id = (body.token_id or "").strip()

    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )

    if not token_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_TOKEN_ID",
                    "message": "token_id 가 필요합니다"},
        )

    if task.risk_level != "high":
        # 승인 자체가 의미 없는 작업 — 혼동 방지로 400
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_APPROVABLE",
                    "message": "high risk 가 아닌 작업은 승인 대상이 아닙니다"},
        )

    # 재실행 방지: 이미 결정된 작업은 새 승인을 받지 않는다.
    if task.status != "waiting_approval":
        log_event(
            "LOCAL_AGENT_TASK_APPROVAL_REPLAYED", task_id,
            actor=actor, role=role,
            note=f"agent_id={agent_id} current_status={task.status}",
        )
        return task.to_safe()

    token, status = approve_token(token_id, task_id, actor, role)
    log_event(
        _policy.APPROVE_AUDIT_EVENT.get(status, "APPROVAL_DENIED"),
        task_id, actor=actor, role=role,
        decision=status, risk_level=token.risk_level,
        action_type=task.action,
        note=_audit.build_approval_note(agent_id, token.public_id),
    )

    if status == "approved":
        updated = _reg.mark_approved(task_id, actor)
        if updated is None:
            # mark_approved 가 task 를 못 찾은 비정상 케이스
            raise HTTPException(status_code=404,
                                detail={"error": "TASK_NOT_FOUND"})
        if _guards.is_capture_screenshot_task(updated):
            log_event(
                "CAPTURE_SCREENSHOT_APPROVED", task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor=actor, role=role,
                note=_audit.build_screenshot_approval_note(
                    agent_id, _guards.task_is_dry_run(updated),
                    approval_public_id=token.public_id,
                ),
            )
        return updated.to_safe()

    if status == "expired":
        # 토큰 만료 → 작업도 rejected 로 종결
        _reg.mark_expired(task_id)
        if _guards.is_capture_screenshot_task(task):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED", task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor, role=role,
                decision="expired",
                note=f"agent_id={agent_id} approval_public_id={token.public_id}" if token.public_id else f"agent_id={agent_id}",
            )

    http_code = _policy.APPROVE_STATUS_HTTP.get(status, 400)
    raise HTTPException(status_code=http_code,
                        detail={"error": status.upper(), "status": status})


@local_agent_router.post("/{agent_id}/tasks/{task_id}/reject")
def reject_local_agent_task(
    agent_id: str,
    task_id: str,
    body: AgentTaskApprovalRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """high risk 작업을 거절. 작업은 rejected 상태로 종결되어 WS 로 전달되지 않는다."""
    actor = user["actor"]
    role = user["role"]
    token_id = (body.token_id or "").strip()
    reason = (body.reason or "").strip()

    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    if not token_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_TOKEN_ID",
                    "message": "token_id 가 필요합니다"},
        )
    if task.risk_level != "high":
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_APPROVABLE",
                    "message": "high risk 가 아닌 작업은 거절 대상이 아닙니다"},
        )

    if task.status != "waiting_approval":
        log_event(
            "LOCAL_AGENT_TASK_APPROVAL_REPLAYED", task_id,
            actor=actor, role=role,
            note=f"agent_id={agent_id} current_status={task.status}",
        )
        return task.to_safe()

    token, status = reject_token(token_id, task_id, actor, role, reason=reason)
    log_event(
        _policy.REJECT_AUDIT_EVENT.get(status, "APPROVAL_REJECTED"),
        task_id, actor=actor, role=role,
        decision=status, risk_level=token.risk_level,
        action_type=task.action,
        note=f"agent_id={agent_id}" + (f" reason={reason}" if reason else "") + (f" approval_public_id={token.public_id}" if token.public_id else ""),
    )
    if status == "rejected":
        updated = _reg.mark_rejected(task_id, actor, reason=reason)
        if updated is None:
            raise HTTPException(status_code=404,
                                detail={"error": "TASK_NOT_FOUND"})
        if _guards.is_capture_screenshot_task(updated):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED", task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor=actor, role=role,
                decision="rejected",
                note=f"agent_id={agent_id}" + (f" reason={reason}" if reason else "") + (f" approval_public_id={token.public_id}" if token.public_id else ""),
            )
        return updated.to_safe()

    if status == "expired":
        _reg.mark_expired(task_id)
        if _guards.is_capture_screenshot_task(task):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED", task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor, role=role,
                decision="expired",
                note=f"agent_id={agent_id} approval_public_id={token.public_id}" if token.public_id else f"agent_id={agent_id}",
            )

    http_code = _policy.REJECT_STATUS_HTTP.get(status, 400)
    raise HTTPException(status_code=http_code,
                        detail={"error": status.upper(), "status": status})


class AgentCleanupRequest(BaseModel):
    """agent cleanup 요청."""
    dry_run: bool = True
    force: bool = False
    confirm: Optional[str] = None


@local_agent_router.post("/{agent_id}/cleanup")
def cleanup_local_agent(
    agent_id: str,
    body: AgentCleanupRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """smoke-test agent cleanup endpoint.

    dry_run=true (기본): preview만 반환, 실제 삭제 안 함
    force=true + confirm 정확 일치: 실제 cleanup 수행

    Response:
    {
        "agent_id": str,
        "dry_run": bool,
        "eligible": bool,
        "reason": str,
        "status": "preview" | "cleaned" | "error",
        "deleted": bool,
        "task_count": int
    }
    """
    actor = user.get("name", "system") if user else "system"

    result = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=body.dry_run,
        force=body.force,
        confirm=body.confirm,
        actor=actor,
    )

    # 실제 cleanup 수행 시 audit log 기록
    if result.get("deleted"):
        log_event(
            "LOCAL_AGENT_CLEANUP", agent_id,
            actor=actor,
            role=user.get("role", "") if user else "",
            note=(
                f"status=cleanup_success"
                f" task_count={result.get('task_count', 0)}"
                f" tasks_deleted={result.get('tasks_deleted', 0)}"
            ),
        )

    return result


@local_agent_router.get("/{agent_id}/tasks")
def list_local_agent_tasks(
    agent_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    if status is not None and status not in _reg.KNOWN_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_STATUS",
                    "message": f"알 수 없는 status: {status}"},
        )
    tasks = _reg.list_tasks_for_agent(agent_id, status=status, limit=limit)
    return {
        "agent_id": agent_id,
        "total": len(tasks),
        "tasks": [t.to_list_safe() for t in tasks],
    }


@local_agent_router.get("/{agent_id}/tasks/{task_id}")
def get_local_agent_task(
    agent_id: str,
    task_id: str,
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    return task.to_safe()


# ── WebSocket (Stage 2) ────────────────────────────────────────────────
#
# 인증 흐름:
#   1. 클라이언트가 연결 후 첫 메시지로 {"type":"auth","agent_id","device_token"} 전송
#   2. 서버는 authenticate_agent() 로 검증. 실패 시 즉시 close(4401) — 이후 통신 없음
#   3. 성공 시 agent_id 소유 큐의 queued 작업을 모두 push (mark_delivered)
#
# 허용 메시지 타입 (클라→서버):
#   - auth       (1회만)
#   - heartbeat  → heartbeat_ack + 신규 queued 작업 push
#   - pull       → 신규 queued 작업 push
#   - running    {task_id}
#   - result     {task_id, success, summary, error_code, error}
#
# 서버→클라:
#   - auth_ok   {agent_id}
#   - task      {task}                 (queued → delivered 로 전환된 작업)
#   - running_ack {task_id}
#   - result_ack  {task_id, status}
#   - idle       (keepalive timeout)
#   - error      {error, message}
#
# 보안:
#   - device_token 원문은 authenticate_agent() 의 로컬 변수로만 존재, 로그 금지
#   - agent_id 불일치 (auth 이후 message 의 agent_id 가 다름) 는 error 응답
#   - high risk 작업은 애초에 status=waiting_approval 로 큐에 남아있지 않으므로
#     WS 로 전달되지 않는다 (queued 상태만 전달).

_WS_RECV_TIMEOUT_SEC = 30  # keepalive/idle push 주기


def _safe_str(value) -> str:
    return "" if value is None else str(value)


async def _push_queued(ws: WebSocket, agent_id: str) -> int:
    """해당 에이전트의 queued 작업을 모두 delivered 로 전환하며 push. 전송 개수 반환."""
    pending = _reg.list_pending_for_agent(agent_id)
    sent = 0
    for t in pending:
        updated = _reg.mark_delivered(agent_id, t.task_id)
        if updated is None or updated.status != "delivered":
            continue
        await ws.send_json({
            "type": "task",
            "task": updated.to_dispatch(),
        })
        log_event(
            "LOCAL_AGENT_TASK_DELIVERED", updated.task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-dispatch",
            note=f"agent_id={agent_id}",
        )
        sent += 1
    return sent


async def _handle_result(ws: WebSocket, agent_id: str, msg: dict) -> None:
    task_id = _safe_str(msg.get("task_id"))
    if not task_id:
        await ws.send_json({
            "type": "error", "error": "MISSING_TASK_ID",
            "message": "result 메시지에 task_id 가 없습니다",
        })
        return

    existing = _reg.get_task(agent_id, task_id)
    if existing is None:
        # 다른 agent 의 task_id 를 주장하거나 존재하지 않는 작업 — 거절
        await ws.send_json({
            "type": "error", "error": "TASK_NOT_FOUND",
            "task_id": task_id,
        })
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", task_id,
            actor="ws-dispatch",
            note=f"agent_id={agent_id} reason=UNKNOWN_TASK_IN_RESULT",
        )
        return

    success = bool(msg.get("success", False))
    summary = _safe_str(msg.get("summary"))[:500]
    error = _safe_str(msg.get("error"))[:500]
    error_code = _safe_str(msg.get("error_code"))[:80]
    raw_observe = msg.get("observe_summary")
    observe_summary = raw_observe if isinstance(raw_observe, dict) else None
    raw_audit = msg.get("audit_summary")
    audit_summary = raw_audit if isinstance(raw_audit, dict) else None
    raw_data = msg.get("data")
    result_data = raw_data if isinstance(raw_data, dict) else None

    updated = _reg.apply_result(
        agent_id=agent_id, task_id=task_id,
        success=success, summary=summary, error=error, error_code=error_code,
        observe_summary=observe_summary,
        audit_summary=audit_summary,
        data=result_data,
    )
    if updated is None:
        await ws.send_json({
            "type": "error", "error": "TASK_NOT_FOUND", "task_id": task_id,
        })
        return

    if updated.status == "completed":
        log_event(
            "LOCAL_AGENT_TASK_COMPLETED", task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            note=f"agent_id={agent_id}",
        )
        if _guards.is_capture_screenshot_task(updated):
            dry = _guards.task_is_dry_run(updated)
            # summary 도 fallback 으로 검사 — task.params 가 어떤 이유로 손실돼도
            # client 가 보낸 summary 접두("dry_run:true") 로 분기할 수 있다.
            if not dry and updated.result_summary.startswith("dry_run:true"):
                dry = True
            log_event(
                ("CAPTURE_SCREENSHOT_DRY_RUN_COMPLETED"
                 if dry else "CAPTURE_SCREENSHOT_COMPLETED"),
                task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor="ws-agent",
                note=f"agent_id={agent_id}",
            )
    elif updated.status == "failed":
        log_event(
            "LOCAL_AGENT_TASK_FAILED", task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            decision=error_code or "failed",
            note=f"agent_id={agent_id}",
        )
        if _guards.is_capture_screenshot_task(updated):
            log_event(
                "CAPTURE_SCREENSHOT_FAILED", task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor="ws-agent",
                decision=error_code or "failed",
                note=f"agent_id={agent_id}",
            )

    await ws.send_json({
        "type": "result_ack",
        "task_id": task_id,
        "status": updated.status,
    })


async def _handle_running(ws: WebSocket, agent_id: str, msg: dict) -> None:
    task_id = _safe_str(msg.get("task_id"))
    if not task_id:
        await ws.send_json({
            "type": "error", "error": "MISSING_TASK_ID",
        })
        return
    updated = _reg.mark_running(agent_id, task_id)
    if updated is None:
        await ws.send_json({
            "type": "error", "error": "TASK_NOT_FOUND", "task_id": task_id,
        })
        return
    if updated.status == "running":
        log_event(
            "LOCAL_AGENT_TASK_RUNNING", task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            note=f"agent_id={agent_id}",
        )
    await ws.send_json({
        "type": "running_ack", "task_id": task_id, "status": updated.status,
    })


@local_agent_router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    """로컬 에이전트 WebSocket 엔드포인트.

    - 최초 메시지로 auth 를 받아 device_token 을 검증한다.
    - 인증 실패 시 code=4401 로 close. HTTP 상태/본문 노출 없음.
    - 이후 heartbeat / pull / running / result 메시지를 처리.
    - 민감한 device_token 원문은 로컬 변수 범위를 벗어나지 않는다.
    """
    await websocket.accept()
    agent_id: str = ""
    try:
        # 1) 인증 메시지 수신 (10초 내)
        try:
            auth_msg = await asyncio.wait_for(
                websocket.receive_json(), timeout=10.0,
            )
        except asyncio.TimeoutError:
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED", "local-agent",
                actor="ws-dispatch", note="reason=AUTH_TIMEOUT",
            )
            await websocket.close(code=4401)
            return
        except WebSocketDisconnect:
            return

        if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth":
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED", "local-agent",
                actor="ws-dispatch", note="reason=AUTH_MESSAGE_REQUIRED",
            )
            await websocket.close(code=4401)
            return

        claimed_agent_id = _safe_str(auth_msg.get("agent_id"))
        device_token = _safe_str(auth_msg.get("device_token"))
        # device_token 원문을 로그에 남기지 않기 위해 별도 변수 없이 바로 전달
        authed = _reg.authenticate_agent(claimed_agent_id, device_token)
        # 참조 제거 (메모리상 흔적 최소화)
        device_token = ""
        if authed is None:
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED",
                claimed_agent_id or "local-agent",
                actor="ws-dispatch",
                note=f"agent_id={claimed_agent_id or '-'} reason=BAD_CREDENTIALS",
            )
            await websocket.close(code=4401)
            return

        agent_id = authed.agent_id
        now_connected = _reg._now_iso()
        _reg.set_agent_connected(agent_id, now_connected)
        log_event(
            "LOCAL_AGENT_WS_CONNECTED", agent_id,
            actor="ws-dispatch",
            note=f"host={authed.host} ver={authed.version}",
        )
        await websocket.send_json({
            "type": "auth_ok",
            "agent_id": agent_id,
        })

        # 2) 초기 큐 드레인
        await _push_queued(websocket, agent_id)

        # 3) 메시지 루프
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=_WS_RECV_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                # 유휴 — 신규 큐 작업 push + keepalive
                _reg.set_agent_last_seen(agent_id)
                await _push_queued(websocket, agent_id)
                expired = _reg.expire_stale_tasks()
                for t in expired:
                    log_event(
                        "LOCAL_AGENT_TASK_TIMEOUT", t.task_id,
                        actor="ws-timeout",
                        note=(
                            f"agent_id={t.agent_id}"
                            f" failure_reason={t.failure_reason}"
                            f" status=failed"
                            f" timed_out_at={t.timed_out_at}"
                        ),
                    )
                try:
                    await websocket.send_json({"type": "idle"})
                except Exception:
                    raise WebSocketDisconnect()
                continue

            if not isinstance(msg, dict):
                await websocket.send_json({
                    "type": "error", "error": "INVALID_MESSAGE",
                })
                continue

            # auth 이후 메시지의 agent_id 는 반드시 일치해야 한다.
            msg_agent_id = _safe_str(msg.get("agent_id"))
            if msg_agent_id and msg_agent_id != agent_id:
                await websocket.send_json({
                    "type": "error", "error": "AGENT_ID_MISMATCH",
                })
                continue

            mtype = _safe_str(msg.get("type"))
            if mtype == "heartbeat":
                _reg.set_agent_last_seen(agent_id)
                await websocket.send_json({"type": "heartbeat_ack"})
                await _push_queued(websocket, agent_id)
            elif mtype == "pull":
                await _push_queued(websocket, agent_id)
            elif mtype == "running":
                _reg.set_agent_last_seen(agent_id)
                await _handle_running(websocket, agent_id, msg)
            elif mtype == "result":
                _reg.set_agent_last_seen(agent_id)
                await _handle_result(websocket, agent_id, msg)
                await _push_queued(websocket, agent_id)
            elif mtype == "user_present_status":
                _reg.set_agent_last_seen(agent_id)
                if _UP_STATUS_HANDLER_AVAILABLE:
                    _result = _handle_up_status_event(msg)
                    await websocket.send_json({
                        "type": "user_present_status_ack",
                        "ok": _result.get("ok", False),
                        "workflow_run_id": _result.get("workflow_run_id", ""),
                        "accepted_status": _result.get("accepted_status"),
                        "safe_to_execute": False,
                        "error": _result.get("error", ""),
                    })
                else:
                    await websocket.send_json({
                        "type": "error", "error": "USER_PRESENT_HANDLER_UNAVAILABLE",
                    })
            elif mtype == "user_present_ack":
                # 로컬 Agent의 USER_PRESENT_TASK 수신 확인 — 로그만
                _reg.set_agent_last_seen(agent_id)
            elif mtype == "auth":
                # 재인증 요청은 거절 (이미 인증된 세션)
                await websocket.send_json({
                    "type": "error", "error": "ALREADY_AUTHENTICATED",
                })
            else:
                await websocket.send_json({
                    "type": "error", "error": "UNKNOWN_MESSAGE_TYPE",
                    "received": mtype[:40],
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("agent websocket 예외: %s", e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if agent_id:
            _reg.set_agent_disconnected(agent_id)
            failed_on_disconnect = _reg.fail_active_tasks_for_agent(agent_id)
            for t in failed_on_disconnect:
                log_event(
                    "LOCAL_AGENT_TASK_FAILED", t.task_id,
                    risk_level=t.risk_level,
                    action_type=t.action,
                    actor="ws-disconnect",
                    decision="failed",
                    note=(
                        f"agent_id={agent_id}"
                        f" failure_reason={t.failure_reason}"
                        f" status=failed"
                    ),
                )
            log_event(
                "LOCAL_AGENT_WS_DISCONNECTED", agent_id,
                actor="ws-dispatch",
            )


__all__ = ["local_agent_router"]
