"""local_agent 브라우저 라우트군 — browser-readonly / capture-screenshot / open-url.

leaf 서브라우터. 컴포지션 루트(local_agent_router)가 include_router 로 관리.
공유 leaf(validation/up_queue) + 계약(schemas)만 사용, sibling 직접 결합 없음.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from ..registry import facade as _reg
from ...audit.audit_logger import log_event
from tools.gates.approval import issue_token_for_dev_reg
from tools.gates.auth import require_role
from .schemas import (
    BrowserReadonlyInstructionRequest,
    CaptureScreenshotRequest,
)
from .validation import (
    _capture_approval_note,
    _validate_readonly_browser_instruction,
)

browser_router = APIRouter()


@browser_router.post("/{agent_id}/browser-readonly-instructions")
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
            detail={"error": "AGENT_NOT_FOUND", "message": f"unknown local agent: {agent_id}"},
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
        ) from e

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


@browser_router.post("/{agent_id}/capture-screenshot")
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
            "LOCAL_AGENT_TASK_REJECTED",
            "local-agent",
            action_type="capture_screenshot",
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND", "message": f"미등록 에이전트: {agent_id}"},
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
        params=params,  # _strip_sensitive 는 enqueue_task 내부에서 적용
        requested_by=actor,
    )

    # 운영자 요청임을 명시하는 감사 이벤트 — approval token 원문/전체 경로/파일명
    # 어느 것도 기록하지 않는다.
    log_event(
        "CAPTURE_SCREENSHOT_REQUEST_CREATED",
        task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
        note=(f"agent_id={agent_id} dry_run={dry_run}" + (f" reason={req.reason[:100]}" if req.reason else "")),
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
        "LOCAL_AGENT_TASK_WAITING_APPROVAL",
        task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
        token_id=token.token_id,
        note=f"agent_id={agent_id}",
    )
    log_event(
        "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED",
        task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
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


@browser_router.post("/{agent_id}/open-url-execution-request")
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
        "LOCAL_AGENT_TASK_WAITING_APPROVAL",
        task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
        token_id=token.token_id,
        note=(
            f"agent_id={agent_id} url_host={parsed.netloc}" + (f" reason={body.reason[:100]}" if body.reason else "")
        ),
    )
    log_event(
        "OPEN_URL_EXECUTE_APPROVAL_REQUESTED",
        task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
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
