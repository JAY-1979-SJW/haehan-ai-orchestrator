"""
Local Agent User-Present Task Dispatcher

routing dry-run 결과가 DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED일 때
서버가 연결된 로컬 Agent로 USER_PRESENT_TASK를 능동적으로 push하기 위한
dispatch context/request/response 빌더.

실제 WebSocket 송신 없음.
safe_to_execute: 항상 False.
click/type/fill/submit 코드 없음.
cookie/session/token 저장·전송 금지.
raw target_url 금지.
"""

from __future__ import annotations

from typing import Any

try:
    from ai_orchestrator.browser_tool.routing.browser_engine_routing_dispatch_dryrun import (
        DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    )
except ImportError:
    DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED = (
        "DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED"
    )

try:
    from ai_orchestrator.contracts.user_present_ws_contract import (
        MSG_USER_PRESENT_TASK,
        build_user_present_ws_task_message,
        sanitize_user_present_ws_payload,
    )
except ImportError:
    MSG_USER_PRESENT_TASK = "USER_PRESENT_TASK"

    def build_user_present_ws_task_message(payload: dict[str, Any]) -> dict[str, Any]:
        return {"message_type": MSG_USER_PRESENT_TASK, **payload, "safe_to_execute": False}

    def sanitize_user_present_ws_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k != "target_url"}

# ── dispatch 금지 decision ────────────────────────────────────────────────────

_NO_DISPATCH_DECISIONS: frozenset[str] = frozenset({
    "DRYRUN_SERVER_PLAYWRIGHT_READONLY_READY",
    "DRYRUN_LOCAL_AGENT_PLAYWRIGHT_READY",
    "DRYRUN_API_CONNECTOR_REQUIRED",
    "DRYRUN_APPROVAL_REQUIRED",
    "DRYRUN_DOMAIN_VERIFICATION_REQUIRED",
    "DRYRUN_BLOCKED",
    "DRYRUN_MANUAL_REVIEW_REQUIRED",
})

# ── dispatch request 필수 필드 ────────────────────────────────────────────────

_REQUIRED_DISPATCH_FIELDS: tuple[str, ...] = (
    "workflow_run_id",
    "tenant_id",
    "user_id",
    "site_id",
    "dryrun_result",
)


def should_dispatch_user_present_task(dryrun_result: dict[str, Any]) -> bool:
    """
    dryrun_result의 dispatch_decision이 USER_PRESENT_REQUIRED일 때만 True.
    """
    return (
        dryrun_result.get("dispatch_decision")
        == DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    )


def build_user_present_dispatch_context(payload: dict[str, Any]) -> dict[str, Any]:
    """
    dryrun_result + agent 선택 정보 → dispatch context.
    safe_to_execute=False 항상.
    """
    dryrun_result = payload.get("dryrun_result", {})
    return {
        "workflow_run_id": payload.get("workflow_run_id", ""),
        "tenant_id": payload.get("tenant_id", ""),
        "user_id": payload.get("user_id", ""),
        "site_id": payload.get("site_id", ""),
        "site_category": payload.get("site_category", ""),
        "target_domain": payload.get("target_domain", ""),
        "target_url_redacted": payload.get("target_url_redacted", ""),
        "target_url_hash": payload.get("target_url_hash", ""),
        "auth_method_label": payload.get("auth_method_label", ""),
        "selected_agent_id": payload.get("selected_agent_id", ""),
        "dryrun_result": dryrun_result,
        "dispatch_eligible": should_dispatch_user_present_task(dryrun_result),
        "safe_to_execute": False,
    }


def build_user_present_task_from_dryrun(dryrun_result: dict[str, Any]) -> dict[str, Any]:
    """
    dryrun_result → USER_PRESENT_TASK message payload.
    next_step_instruction에서 필드를 추출하여 메시지를 구성한다.
    """
    instruction = dryrun_result.get("next_step_instruction", {})
    payload: dict[str, Any] = {
        "workflow_run_id": dryrun_result.get("workflow_run_id", ""),
        "workflow_id": dryrun_result.get("workflow_id", ""),
        "tenant_id": dryrun_result.get("tenant_id", "") or instruction.get("tenant_id", ""),
        "user_id": dryrun_result.get("user_id", "") or instruction.get("user_id", ""),
        "site_id": dryrun_result.get("site_id", "") or instruction.get("site_id", ""),
        "site_category": instruction.get("site_category", ""),
        "target_domain": instruction.get("target_domain", ""),
        "target_url_redacted": instruction.get("target_url_redacted", ""),
        "target_url_hash": instruction.get("target_url_hash", ""),
        "auth_method_label": instruction.get("auth_method_label", ""),
        "user_message_ko": dryrun_result.get("user_message_ko", "사용자 직접 인증이 필요합니다."),
        "required_user_actions": instruction.get("required_user_actions", ["직접 인증 후 완료 클릭"]),
        "blocked_ai_actions": instruction.get("blocked_ai_actions", ["자동 입력 금지"]),
        "safe_to_execute": False,
    }
    sanitized = sanitize_user_present_ws_payload(payload)
    return build_user_present_ws_task_message(sanitized)


def validate_user_present_dispatch_request(payload: dict[str, Any]) -> list[str]:
    """
    dispatch request 필수 필드 + 정책 검증.
    오류 목록 반환 (비어있으면 유효).
    """
    errors: list[str] = []

    for field in _REQUIRED_DISPATCH_FIELDS:
        if not payload.get(field):
            errors.append(f"필수 필드 누락: {field}")

    dryrun_result = payload.get("dryrun_result", {})
    if not should_dispatch_user_present_task(dryrun_result):
        decision = dryrun_result.get("dispatch_decision", "")
        errors.append(
            f"dispatch_decision이 USER_PRESENT_REQUIRED가 아님: {decision}"
        )

    if not payload.get("selected_agent_id"):
        errors.append("AGENT_SELECTION_REQUIRED: selected_agent_id 없음")

    if payload.get("safe_to_execute") is True:
        errors.append("safe_to_execute는 항상 False여야 한다")

    return errors


def build_user_present_dispatch_response(payload: dict[str, Any]) -> dict[str, Any]:
    """
    dispatch 요청을 검증하고 dispatch response를 구성한다.
    실제 WebSocket 송신 없음.
    """
    errors = validate_user_present_dispatch_request(payload)
    if errors:
        return {
            "ok": False,
            "dispatched": False,
            "workflow_run_id": payload.get("workflow_run_id", ""),
            "selected_agent_id": payload.get("selected_agent_id", ""),
            "dispatch_decision": payload.get("dryrun_result", {}).get("dispatch_decision", ""),
            "safe_to_execute": False,
            "errors": errors,
            "message_ko": f"dispatch 검증 실패: {errors[0]}",
        }

    dryrun_result = payload.get("dryrun_result", {})
    task_message = build_user_present_task_from_dryrun({
        **dryrun_result,
        "workflow_run_id": payload.get("workflow_run_id", ""),
        "workflow_id": payload.get("workflow_id", ""),
        "tenant_id": payload.get("tenant_id", ""),
        "user_id": payload.get("user_id", ""),
        "site_id": payload.get("site_id", ""),
    })

    return {
        "ok": True,
        "dispatched": True,
        "workflow_run_id": payload.get("workflow_run_id", ""),
        "selected_agent_id": payload.get("selected_agent_id", ""),
        "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
        "task_message": task_message,
        "safe_to_execute": False,
        "message_ko": "USER_PRESENT_TASK dispatch 준비 완료 (실제 송신 없음).",
    }
