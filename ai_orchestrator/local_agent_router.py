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
from urllib.parse import urlparse

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

try:
    from .browser_tool.local_agent_user_present_status_store import (
        get_user_present_status as _get_up_status,
        list_user_present_statuses as _list_up_statuses,
    )
    _UP_STATUS_STORE_AVAILABLE = True
except ImportError:
    _UP_STATUS_STORE_AVAILABLE = False

try:
    from .browser_tool.local_agent_user_present_dispatcher import (
        build_user_present_dispatch_response,
        should_dispatch_user_present_task,
    )
    _UP_DISPATCHER_AVAILABLE = True
except ImportError:
    _UP_DISPATCHER_AVAILABLE = False

# ── USER_PRESENT_TASK in-memory 전송 대기 큐 ─────────────────────────────────
# agent_id → [task_message, ...]
# WS heartbeat/pull 시 드레인하여 전송.
import threading as _threading
_up_task_queue: dict[str, list] = {}
_up_task_queue_lock = _threading.Lock()


def _enqueue_up_task(agent_id: str, task_message: dict) -> None:
    with _up_task_queue_lock:
        _up_task_queue.setdefault(agent_id, []).append(task_message)


def _drain_up_tasks(agent_id: str) -> list:
    with _up_task_queue_lock:
        tasks = _up_task_queue.pop(agent_id, [])
    return tasks

logger = logging.getLogger(__name__)

local_agent_router = APIRouter(prefix="/local-agents", tags=["local-agents"])


# ── 요청 모델 — local_agent_router_schemas 로 분리(공유 계약). 파사드 재노출 ──
from .local_agent_router_schemas import (  # noqa: E402
    AgentRegisterRequest,
    AgentTaskRequest,
    BrowserReadonlyInstructionRequest,
    AgentTaskApprovalRequest,
    CancelTaskRequest,
    IssueRegistrationCodeRequest,
    RegisterWithCodeRequest,
    CaptureScreenshotRequest,
)


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


_READONLY_WAIT_UNTIL_VALUES: frozenset[str] = frozenset({
    "domcontentloaded", "load", "networkidle",
})

_UNSAFE_BROWSER_INSTRUCTION_TERMS: frozenset[str] = frozenset({
    "click", "submit", "type", "input", "login", "sign in", "password",
    "otp", "2fa", "pay", "purchase", "buy", "send", "transfer", "delete",
    "remove", "download", "upload", "save", "register", "create account",
    "approve", "confirm", "checkout",
    "클릭", "제출", "입력", "로그인", "비밀번호", "패스워드", "인증번호",
    "결제", "구매", "송금", "전송", "삭제", "다운로드", "업로드", "저장",
    "등록", "가입", "승인", "확인", "체크아웃",
})


def _validate_readonly_browser_instruction(
    body: BrowserReadonlyInstructionRequest,
) -> tuple[str, str, str, int, int, int, str]:
    instruction = str(body.instruction or "").strip()
    if not instruction:
        raise HTTPException(
            status_code=400,
            detail={"error": "EMPTY_BROWSER_INSTRUCTION"},
        )
    if len(instruction) > 500:
        raise HTTPException(
            status_code=400,
            detail={"error": "BROWSER_INSTRUCTION_TOO_LONG"},
        )

    lowered = instruction.lower()
    blocked = next(
        (term for term in _UNSAFE_BROWSER_INSTRUCTION_TERMS if term in lowered),
        "",
    )
    if blocked:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSAFE_BROWSER_INSTRUCTION",
                "message": "readonly browser instructions cannot request input, auth, downloads, or state changes",
            },
        )

    url = str(body.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_BROWSER_URL"},
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail={"error": "URL_CREDENTIALS_NOT_ALLOWED"},
        )

    wait_until = str(body.wait_until or "domcontentloaded").strip()
    if wait_until not in _READONLY_WAIT_UNTIL_VALUES:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_WAIT_UNTIL"},
        )

    timeout_ms = max(1000, min(int(body.timeout_ms), 30000))
    max_html_chars = max(1000, min(int(body.max_html_chars), 100000))
    keep_open_ms = max(0, min(int(body.keep_open_ms), 30000))
    browser_channel = str(body.browser_channel or "chromium").strip().lower()
    if browser_channel not in {"chromium", "chrome", "msedge"}:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_BROWSER_CHANNEL"},
        )
    host = parsed.hostname or parsed.netloc
    return instruction, url, host, timeout_ms, max_html_chars, keep_open_ms, browser_channel


# ── HTTP 라우트 ──────────────────────────────────────────────────────────

# 등록 라우트군은 local_agent_router_registration 으로 분리.
# 컴포지션 루트가 include_router 로 관리(경로 동일).
from .local_agent_router_registration import registration_router as _registration_router  # noqa: E402
local_agent_router.include_router(_registration_router)


@local_agent_router.get("")
def list_local_agents(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    return {"agents": _reg.list_agents()}


# 진단 라우트군(/diagnostics 등 read-only)은 local_agent_router_query 로 분리.
# 컴포지션 루트가 include_router 로 관리(경로 동일).
from .local_agent_router_query import query_router as _query_router  # noqa: E402
local_agent_router.include_router(_query_router)


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


@local_agent_router.post("/{agent_id}/browser-readonly-instructions")
def submit_browser_readonly_instruction(
    agent_id: str,
    body: BrowserReadonlyInstructionRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """Queue an approved-user browser instruction as a readonly local task."""
    actor = user["actor"]
    role = user["role"]

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_BROWSER_READONLY_INSTRUCTION_REJECTED",
            "local-agent",
            action_type="web_open_url_readonly",
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND",
                    "message": f"unknown local agent: {agent_id}"},
        )

    instruction, url, host, timeout_ms, max_html_chars, keep_open_ms, browser_channel = (
        _validate_readonly_browser_instruction(body)
    )
    background_approved = bool(body.allow_background) and not bool(body.visible_browser)
    params = {
        "url": url,
        "wait_until": body.wait_until,
        "timeout_ms": timeout_ms,
        "max_html_chars": max_html_chars,
        "headless": background_approved,
        "background_approved": background_approved,
        "keep_open_ms": keep_open_ms,
        "browser_channel": browser_channel,
        "user_instruction": instruction,
        "source": "approved_user_instruction",
    }

    try:
        task = _reg.enqueue_task(
            agent_id=agent_id,
            action="web_open_url_readonly",
            params=params,
            requested_by=actor,
        )
    except _reg.UnknownActionError as e:
        log_event(
            "LOCAL_AGENT_BROWSER_READONLY_INSTRUCTION_REJECTED",
            "local-agent",
            action_type="web_open_url_readonly",
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=UNKNOWN_ACTION",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_ACTION", "message": str(e)},
        )

    log_event(
        "LOCAL_AGENT_BROWSER_READONLY_INSTRUCTION_QUEUED",
        task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
        note=(
            f"agent_id={agent_id} url_host={host} "
            f"instruction_len={len(instruction)} visible_browser={bool(body.visible_browser)} "
            f"allow_background={bool(body.allow_background)} "
            f"keep_open_ms={keep_open_ms} browser_channel={browser_channel} status={task.status}"
        ),
    )

    return {
        "task_id": task.task_id,
        "agent_id": task.agent_id,
        "action": task.action,
        "status": task.status,
        "risk_level": task.risk_level,
        "requested_by": actor,
        "instruction_accepted": True,
        "url_host": host,
        "visible_browser": bool(body.visible_browser),
        "allow_background": bool(body.allow_background),
        "background_approved": background_approved,
        "keep_open_ms": keep_open_ms,
        "browser_channel": browser_channel,
    }


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


class UserPresentDispatchRequest(BaseModel):
    """USER_PRESENT_TASK dispatch 요청 body."""
    workflow_run_id: str
    workflow_id: str = ""
    tenant_id: str
    user_id: str
    site_id: str
    site_category: str = ""
    target_domain: str = ""
    target_url_redacted: str = ""
    target_url_hash: str = ""
    auth_method_label: str = ""
    selected_agent_id: str
    dryrun_result: dict = {}


@local_agent_router.get("/user-present-status/{workflow_run_id}")
def get_user_present_status_record(
    workflow_run_id: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    """workflow_run_id 기준 USER_PRESENT_STATUS 수신 기록 조회."""
    if not _UP_STATUS_STORE_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "STATUS_STORE_UNAVAILABLE"})
    record = _get_up_status(workflow_run_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "workflow_run_id": workflow_run_id},
        )
    return {"ok": True, "safe_to_execute": False, "record": record}


@local_agent_router.get("/{agent_id}/user-present-statuses")
def list_agent_user_present_statuses(
    agent_id: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    """agent_id 기준 USER_PRESENT_STATUS 수신 목록 조회."""
    if not _UP_STATUS_STORE_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "STATUS_STORE_UNAVAILABLE"})
    records = _list_up_statuses(agent_id=agent_id)
    return {"ok": True, "safe_to_execute": False, "agent_id": agent_id, "records": records, "total": len(records)}


@local_agent_router.post("/{agent_id}/user-present-dispatch")
def dispatch_user_present_task(
    agent_id: str,
    body: UserPresentDispatchRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """routing dry-run 결과가 USER_PRESENT_REQUIRED일 때 USER_PRESENT_TASK를 agent에 전송 예약.

    실제 WebSocket 송신은 다음 heartbeat/pull 시 수행.
    safe_to_execute=False 항상.
    """
    actor = user["actor"]
    role = user["role"]

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type="user_present_dispatch", actor=actor, role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND", "message": f"미등록 에이전트: {agent_id}"},
        )

    if not _UP_DISPATCHER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={"error": "DISPATCHER_UNAVAILABLE", "message": "dispatcher 모듈 없음"},
        )

    payload = {
        "workflow_run_id": body.workflow_run_id,
        "workflow_id": body.workflow_id,
        "tenant_id": body.tenant_id,
        "user_id": body.user_id,
        "site_id": body.site_id,
        "site_category": body.site_category,
        "target_domain": body.target_domain,
        "target_url_redacted": body.target_url_redacted,
        "target_url_hash": body.target_url_hash,
        "auth_method_label": body.auth_method_label,
        "selected_agent_id": body.selected_agent_id,
        "dryrun_result": body.dryrun_result,
    }

    result = build_user_present_dispatch_response(payload)
    if not result.get("ok"):
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type="user_present_dispatch", actor=actor, role=role,
            note=f"agent_id={agent_id} errors={result.get('errors', [])}",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "DISPATCH_VALIDATION_FAILED", "message": result.get("message_ko", "")},
        )

    task_message = result.get("task_message", {})
    task_message["safe_to_execute"] = False
    _enqueue_up_task(agent_id, task_message)

    log_event(
        "LOCAL_AGENT_USER_PRESENT_TASK_DISPATCHED", body.workflow_run_id,
        actor=actor, role=role,
        note=f"agent_id={agent_id} site_id={body.site_id}",
    )

    return {
        "ok": True,
        "dispatched": True,
        "workflow_run_id": body.workflow_run_id,
        "agent_id": agent_id,
        "dispatch_decision": result.get("dispatch_decision", ""),
        "safe_to_execute": False,
        "message_ko": result.get("message_ko", ""),
    }


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
    """해당 에이전트의 queued 작업을 최대 1개 delivered 로 전환하며 push. 전송 개수 반환."""
    # A single local-agent WebSocket session is sequential:
    # task -> running_ack -> result -> next task.
    if _reg.get_active_task_count(agent_id) > 0:
        return 0
    pending = _reg.list_pending_for_agent(agent_id)
    sent = 0
    for t in pending[:1]:
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


async def _push_user_present_tasks(ws: WebSocket, agent_id: str) -> int:
    """USER_PRESENT_TASK 전송 대기 큐를 드레인하여 push. 전송 개수 반환."""
    tasks = _drain_up_tasks(agent_id)
    for task_msg in tasks:
        await ws.send_json({
            "type": "user_present_task",
            "task": task_msg,
        })
    return len(tasks)


async def _send_task_blocked(
    ws: WebSocket,
    *,
    task_id: str = "",
    workflow_run_id: str = "",
    reason: str = "",
    message_ko: str = "",
) -> None:
    """정책/dispatcher 차단을 클라이언트에 통지한다.

    task_blocked 는 실행 명령이 아닌 상태/사유 통지 메시지다.
    UI 측에서 차단 사유를 사용자에게 표시할 수 있도록 한다.
    민감 필드(token/cookie/authorization 등)는 포함 금지.
    """
    try:
        await ws.send_json({
            "type": "task_blocked",
            "task_id": _safe_str(task_id)[:80],
            "workflow_run_id": _safe_str(workflow_run_id)[:120],
            "reason": _safe_str(reason)[:80],
            "message_ko": _safe_str(message_ko)[:200],
            "safe_to_execute": False,
        })
    except Exception:
        pass


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

    # 멱등 보강: 이미 최종 상태인 task 에 대한 result 재수신은 상태 재변경/이벤트
    # 재발행 없이 ack 만 반환한다. result_ack 손실로 인한 재실행을 방지한다.
    _FINAL_RESULT_STATES = ("completed", "failed", "rejected", "cancelled")
    if existing.status in _FINAL_RESULT_STATES:
        await ws.send_json({
            "type": "result_ack",
            "task_id": task_id,
            "status": existing.status,
            "idempotent": True,
        })
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
                await _push_user_present_tasks(websocket, agent_id)
            elif mtype == "pull":
                await _push_queued(websocket, agent_id)
                await _push_user_present_tasks(websocket, agent_id)
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
                    _result = _handle_up_status_event(msg, agent_id=agent_id)
                    await websocket.send_json({
                        "type": "user_present_status_ack",
                        "ok": _result.get("ok", False),
                        "workflow_run_id": _result.get("workflow_run_id", ""),
                        "accepted_status": _result.get("accepted_status"),
                        "safe_to_execute": False,
                        "received_at": _result.get("received_at", ""),
                        "error": _result.get("error", ""),
                    })
                    # 정책상 BLOCKED 로 수렴된 경우 클라이언트에 차단 사유를 추가 통지.
                    if _result.get("accepted_status") == "BLOCKED":
                        await _send_task_blocked(
                            websocket,
                            workflow_run_id=_safe_str(_result.get("workflow_run_id", "")),
                            reason=_safe_str(_result.get("block_reason", "POLICY_BLOCKED")),
                            message_ko=_safe_str(_result.get("message_ko", "")),
                        )
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
