"""
Browser Engine Routing Dispatch Dryrun Integration

preflight chain 결과를 dry-run dispatcher 응답으로 변환한다.
실제 브라우저/Playwright/API 실행 없이 응답만 반환한다.

safe_to_execute: 항상 False.
dry_run: 항상 True.
click/type/fill/submit 코드 없음.
cookie/session/token 추출 없음.
dispatcher 실제 연결 없음.
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.browser_tool.routing.browser_engine_routing_preflight_chain import (
    CHAIN_BLOCK,
    NEXT_API_CONNECTOR,
    NEXT_APPROVAL_REQUIRED,
    NEXT_BLOCKED,
    NEXT_DOMAIN_VERIFICATION_REQUIRED,
    NEXT_LOCAL_AGENT_PLAYWRIGHT_READONLY,
    NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
    NEXT_MANUAL_REVIEW_REQUIRED,
    NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT,
    evaluate_browser_engine_routing_preflight_chain,
)

# ── dispatch_decision enum ────────────────────────────────────────────────────

DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY = "DRYRUN_SERVER_PLAYWRIGHT_READONLY_READY"
DISPATCH_LOCAL_AGENT_PLAYWRIGHT_READY = "DRYRUN_LOCAL_AGENT_PLAYWRIGHT_READY"
DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED = "DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED"
DISPATCH_API_CONNECTOR_REQUIRED = "DRYRUN_API_CONNECTOR_REQUIRED"
DISPATCH_APPROVAL_REQUIRED = "DRYRUN_APPROVAL_REQUIRED"
DISPATCH_DOMAIN_VERIFICATION_REQUIRED = "DRYRUN_DOMAIN_VERIFICATION_REQUIRED"
DISPATCH_BLOCKED = "DRYRUN_BLOCKED"
DISPATCH_MANUAL_REVIEW_REQUIRED = "DRYRUN_MANUAL_REVIEW_REQUIRED"

# next_step → dispatch_decision 매핑
_NEXT_STEP_TO_DISPATCH: dict[str, str] = {
    NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT: DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY,
    NEXT_LOCAL_AGENT_PLAYWRIGHT_READONLY: DISPATCH_LOCAL_AGENT_PLAYWRIGHT_READY,
    NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT: DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    NEXT_API_CONNECTOR: DISPATCH_API_CONNECTOR_REQUIRED,
    NEXT_APPROVAL_REQUIRED: DISPATCH_APPROVAL_REQUIRED,
    NEXT_DOMAIN_VERIFICATION_REQUIRED: DISPATCH_DOMAIN_VERIFICATION_REQUIRED,
    NEXT_BLOCKED: DISPATCH_BLOCKED,
    NEXT_MANUAL_REVIEW_REQUIRED: DISPATCH_MANUAL_REVIEW_REQUIRED,
}


def build_dryrun_dispatch_context(payload: dict[str, Any]) -> dict[str, Any]:
    """
    payload → chain 결과 포함 dispatch 컨텍스트 구성.
    """
    chain_result = evaluate_browser_engine_routing_preflight_chain(payload)
    return {
        "payload": payload,
        "chain_result": chain_result,
        "dry_run": True,
    }


def build_dryrun_dispatch_response(chain_result: dict[str, Any]) -> dict[str, Any]:
    """
    chain 결과 → dry-run dispatch 응답 구성.
    실제 실행 없이 응답 구조만 반환.
    """
    next_step = chain_result.get("next_step", NEXT_BLOCKED)
    dispatch_decision = _NEXT_STEP_TO_DISPATCH.get(next_step, DISPATCH_BLOCKED)

    chain_decision = chain_result.get("chain_decision", CHAIN_BLOCK)
    safe_to_dispatch = chain_result.get("safe_to_dispatch", False)

    ok = dispatch_decision == DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY
    should_write_audit = chain_result.get("should_write_audit", False)
    block_reason = chain_result.get("block_reason", "")
    message_ko = chain_result.get("message_ko", "")

    user_message_ko = _build_user_message(dispatch_decision, message_ko)
    admin_message_ko = _build_admin_message(dispatch_decision, block_reason, message_ko)

    result: dict[str, Any] = {
        "ok": ok,
        "dry_run": True,
        "dispatch_decision": dispatch_decision,
        "chain_decision": chain_decision,
        "engine_capability": chain_result.get("engine_capability", ""),
        "routing_decision": chain_result.get("routing_decision", ""),
        "selected_engine": chain_result.get("selected_engine", "none"),
        "next_step": next_step,
        "next_step_instruction": chain_result.get("next_step_instruction", {}),
        "safe_to_dispatch": safe_to_dispatch,
        "safe_to_execute": False,
        "should_write_audit": should_write_audit,
        "block_reason": block_reason,
        "user_message_ko": user_message_ko,
        "admin_message_ko": admin_message_ko,
        "result": {
            "site_compliance_decision": chain_result.get("site_compliance_decision", "SKIPPED"),
            "server_boundary_decision": chain_result.get("server_boundary_decision", "SKIPPED"),
            "action_preflight_decision": chain_result.get("action_preflight_decision", "SKIPPED"),
            "gate_preflight_decision": chain_result.get("gate_preflight_decision", "SKIPPED"),
            "allowlist_decision": chain_result.get("allowlist_decision", "SKIPPED"),
        },
    }
    return result


def evaluate_browser_engine_routing_dispatch_dryrun(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    전체 dry-run dispatch 평가.
    preflight chain 실행 후 dispatch 응답을 구성한다.
    """
    ctx = build_dryrun_dispatch_context(payload)
    return build_dryrun_dispatch_response(ctx["chain_result"])


def validate_dryrun_dispatch_result(result: dict[str, Any]) -> list[str]:
    """
    dry-run dispatch 결과의 필수 필드 및 정책 준수를 검증한다.
    """
    errors: list[str] = []

    required_fields = [
        "ok",
        "dry_run",
        "dispatch_decision",
        "chain_decision",
        "engine_capability",
        "routing_decision",
        "selected_engine",
        "next_step",
        "next_step_instruction",
        "safe_to_dispatch",
        "safe_to_execute",
        "should_write_audit",
        "block_reason",
        "user_message_ko",
        "admin_message_ko",
        "result",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("dry_run") is not True:
        errors.append("dry_run은 항상 True여야 한다")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    valid_dispatch_decisions = {
        DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY,
        DISPATCH_LOCAL_AGENT_PLAYWRIGHT_READY,
        DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
        DISPATCH_API_CONNECTOR_REQUIRED,
        DISPATCH_APPROVAL_REQUIRED,
        DISPATCH_DOMAIN_VERIFICATION_REQUIRED,
        DISPATCH_BLOCKED,
        DISPATCH_MANUAL_REVIEW_REQUIRED,
    }
    if result.get("dispatch_decision") not in valid_dispatch_decisions:
        errors.append(f"유효하지 않은 dispatch_decision: {result.get('dispatch_decision')}")

    return errors


def _build_user_message(dispatch_decision: str, message_ko: str) -> str:
    _user_messages: dict[str, str] = {
        DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY: "서버 Playwright read-only 준비 완료 (dry-run).",
        DISPATCH_LOCAL_AGENT_PLAYWRIGHT_READY: "로컬 Agent Playwright read-only 준비 완료 (dry-run).",
        DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED: "사용자 직접 브라우저 접근이 필요합니다.",
        DISPATCH_API_CONNECTOR_REQUIRED: "공식 API/OAuth 경로로 처리합니다.",
        DISPATCH_APPROVAL_REQUIRED: "승인이 필요합니다. 담당자에게 승인 요청을 보냈습니다.",
        DISPATCH_DOMAIN_VERIFICATION_REQUIRED: "도메인 실사 및 승인이 필요합니다.",
        DISPATCH_BLOCKED: "요청이 차단되었습니다.",
        DISPATCH_MANUAL_REVIEW_REQUIRED: "수동 실사 및 승인이 필요합니다.",
    }
    return _user_messages.get(dispatch_decision, message_ko or "처리 결과를 확인하세요.")


def _build_admin_message(dispatch_decision: str, block_reason: str, message_ko: str) -> str:
    base = _build_user_message(dispatch_decision, message_ko)
    if block_reason:
        return f"{base} [사유: {block_reason}]"
    return base
