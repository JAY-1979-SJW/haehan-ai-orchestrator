"""
Browser Engine Routing Policy

engine_capability 분류 결과를 기반으로 실제 실행 경로를 결정한다.
무조건 Playwright 먼저 시도하는 구조를 금지하고,
정책 기반으로 엔진을 라우팅한다.

safe_to_execute: 항상 False.
click/type/fill/submit 코드 없음.
cookie/session/token 추출 없음.
인증서 비밀번호/OTP 입력 코드 없음.
dispatcher/task_executor 실제 연결 없음.
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.browser_tool.routing.browser_engine_capability_classifier import (
    ENGINE_API_CONNECTOR_REQUIRED,
    ENGINE_AUTOMATION_BLOCKED,
    ENGINE_LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED,
    ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED,
    classify_browser_engine_capability,
)

# ── routing_decision 값 ───────────────────────────────────────────────────────

ROUTING_SERVER_PLAYWRIGHT_READONLY = "ROUTE_SERVER_PLAYWRIGHT_READONLY"
ROUTING_LOCAL_AGENT_PLAYWRIGHT_READONLY = "ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY"
ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT = "ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT"
ROUTING_API_CONNECTOR = "ROUTE_API_CONNECTOR"
ROUTING_BLOCK = "BLOCK"
ROUTING_MANUAL_REVIEW = "MANUAL_REVIEW"

# ── selected_engine 값 ────────────────────────────────────────────────────────

ENGINE_SEL_SERVER_PLAYWRIGHT = "server_playwright"
ENGINE_SEL_LOCAL_AGENT_PLAYWRIGHT = "local_agent_playwright"
ENGINE_SEL_LOCAL_SYSTEM_BROWSER = "local_system_browser"
ENGINE_SEL_API_CONNECTOR = "api_connector"
ENGINE_SEL_NONE = "none"

# ── fallback 허용 failure_reason ─────────────────────────────────────────────

_FALLBACK_ALLOWED_FAILURE_REASONS: frozenset[str] = frozenset(
    {
        "runtime_error",
        "network_timeout",
        "browser_not_available",
    }
)

# ── fallback 금지 failure_reason ─────────────────────────────────────────────

_FALLBACK_BLOCKED_FAILURE_REASONS: frozenset[str] = frozenset(
    {
        "policy_blocked",
        "domain_blocked",
        "auth_required",
        "otp_required",
        "certificate_required",
        "captcha_required",
    }
)

# ── type/submit operation 자동 실행 금지 ──────────────────────────────────────

_BLOCKED_OPERATIONS: frozenset[str] = frozenset(
    {
        "type",
        "submit",
        "fill",
        "click_submit",
        "auto_login",
        "execute_type",
        "execute_submit",
        "plan_type",
        "plan_submit",
    }
)


def build_engine_routing_context(payload: dict[str, Any]) -> dict[str, Any]:
    """
    라우팅 컨텍스트를 구성한다.
    classifier 분류를 실행하고, 결과를 라우팅 판정 입력으로 반환한다.
    """
    classification = classify_browser_engine_capability(payload)
    return {
        "workflow_run_id": payload.get("workflow_run_id", ""),
        "workflow_id": payload.get("workflow_id", ""),
        "site_category": payload.get("site_category", ""),
        "target_domain": payload.get("target_domain", ""),
        "target_url": payload.get("target_url", ""),
        "operation_type": payload.get("operation_type", ""),
        "action_name": payload.get("action_name", ""),
        "production_mode": payload.get("production_mode", False),
        "failure_reason": payload.get("failure_reason", ""),
        "engine_capability": classification["engine_capability"],
        "recommended_route": classification["recommended_route"],
        "server_playwright_allowed": classification["server_playwright_allowed"],
        "local_agent_playwright_allowed": classification["local_agent_playwright_allowed"],
        "local_system_browser_required": classification["local_system_browser_required"],
        "api_connector_required": classification["api_connector_required"],
        "user_present_required": classification["user_present_required"],
        "automation_blocked": classification["automation_blocked"],
        "fallback_allowed": classification["fallback_allowed"],
        "fallback_route": classification["fallback_route"],
        "classification_block_reason": classification["block_reason"],
        "classification_message_ko": classification["message_ko"],
    }


def evaluate_browser_engine_routing(payload: dict[str, Any]) -> dict[str, Any]:
    """
    engine_capability 분류 결과를 기반으로 라우팅 결정을 내린다.

    반환 필드:
    - routing_decision, selected_engine
    - server_playwright_first_allowed, local_agent_fallback_allowed
    - api_connector_required, user_present_required
    - manual_review_required, automation_blocked
    - block_reason, safe_to_dispatch, safe_to_execute
    - message_ko
    """
    ctx = build_engine_routing_context(payload)

    # production_mode → BLOCK
    if ctx["production_mode"] is True:
        return _make_routing(
            routing_decision=ROUTING_BLOCK,
            selected_engine=ENGINE_SEL_NONE,
            block_reason="production_mode=true: 모든 라우팅 차단.",
            message_ko="production_mode=true: 브라우저 엔진 라우팅 차단.",
        )

    # type/submit operation → BLOCK
    operation_type = (ctx["operation_type"] or "").lower()
    if operation_type in _BLOCKED_OPERATIONS:
        return _make_routing(
            routing_decision=ROUTING_BLOCK,
            selected_engine=ENGINE_SEL_NONE,
            block_reason=f"operation_type={operation_type}: 자동 실행 route 금지.",
            message_ko=f"{operation_type} 자동 실행은 라우팅이 금지됩니다.",
        )

    engine = ctx["engine_capability"]

    if engine == ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED:
        return _make_routing(
            routing_decision=ROUTING_SERVER_PLAYWRIGHT_READONLY,
            selected_engine=ENGINE_SEL_SERVER_PLAYWRIGHT,
            server_playwright_first_allowed=True,
            local_agent_fallback_allowed=True,
            block_reason="",
            message_ko="서버 Playwright read-only 라우팅.",
        )

    if engine == ENGINE_LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED:
        return _make_routing(
            routing_decision=ROUTING_LOCAL_AGENT_PLAYWRIGHT_READONLY,
            selected_engine=ENGINE_SEL_LOCAL_AGENT_PLAYWRIGHT,
            server_playwright_first_allowed=False,
            block_reason="",
            message_ko="로컬 Agent Playwright read-only 라우팅.",
        )

    if engine == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED:
        return _make_routing(
            routing_decision=ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
            selected_engine=ENGINE_SEL_LOCAL_SYSTEM_BROWSER,
            server_playwright_first_allowed=False,
            user_present_required=True,
            block_reason=ctx["classification_block_reason"],
            message_ko=ctx["classification_message_ko"] or "사용자 직접 브라우저 접근이 필요합니다.",
        )

    if engine == ENGINE_API_CONNECTOR_REQUIRED:
        return _make_routing(
            routing_decision=ROUTING_API_CONNECTOR,
            selected_engine=ENGINE_SEL_API_CONNECTOR,
            server_playwright_first_allowed=False,
            api_connector_required=True,
            block_reason=ctx["classification_block_reason"],
            message_ko=ctx["classification_message_ko"] or "공식 API/OAuth 경로를 사용해야 합니다.",
        )

    if engine == ENGINE_AUTOMATION_BLOCKED:
        return _make_routing(
            routing_decision=ROUTING_BLOCK,
            selected_engine=ENGINE_SEL_NONE,
            automation_blocked=True,
            block_reason=ctx["classification_block_reason"],
            message_ko=ctx["classification_message_ko"] or "자동화가 차단된 사이트입니다.",
        )

    # NEEDS_MANUAL_REVIEW
    return _make_routing(
        routing_decision=ROUTING_MANUAL_REVIEW,
        selected_engine=ENGINE_SEL_NONE,
        manual_review_required=True,
        block_reason=ctx["classification_block_reason"],
        message_ko=ctx["classification_message_ko"] or "수동 실사 및 사용자 승인이 필요합니다.",
    )


def should_attempt_server_playwright_first(payload: dict[str, Any]) -> bool:
    """
    서버 Playwright를 우선 시도해야 하는지 판정한다.

    True인 경우: SERVER_PLAYWRIGHT_READONLY_ALLOWED 사이트이고
    production_mode가 아니고 type/submit operation이 아닌 경우.
    """
    ctx = build_engine_routing_context(payload)
    if ctx["production_mode"] is True:
        return False
    operation_type = (ctx.get("operation_type") or "").lower()
    if operation_type in _BLOCKED_OPERATIONS:
        return False
    return ctx["engine_capability"] == ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED


def should_fallback_to_local_agent(
    payload: dict[str, Any],
    failure_reason: str | None = None,
) -> bool:
    """
    로컬 Agent로 fallback해야 하는지 판정한다.

    조건:
    - server_playwright_first_allowed=True인 사이트
    - failure_reason이 runtime_error / network_timeout / browser_not_available
    - failure_reason이 policy_blocked/auth_required 등이면 False
    """
    ctx = build_engine_routing_context(payload)

    if ctx["engine_capability"] != ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED:
        return False

    reason = (failure_reason or payload.get("failure_reason") or "").lower()

    if reason in _FALLBACK_BLOCKED_FAILURE_REASONS:
        return False

    if reason in _FALLBACK_ALLOWED_FAILURE_REASONS:
        return True

    return False


def validate_browser_engine_routing_result(result: dict[str, Any]) -> list[str]:
    """
    라우팅 결정 결과의 필수 필드 및 정책 준수를 검증한다.
    """
    errors: list[str] = []

    required_fields = [
        "routing_decision",
        "selected_engine",
        "server_playwright_first_allowed",
        "local_agent_fallback_allowed",
        "api_connector_required",
        "user_present_required",
        "manual_review_required",
        "automation_blocked",
        "block_reason",
        "safe_to_dispatch",
        "safe_to_execute",
        "message_ko",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    valid_decisions = {
        ROUTING_SERVER_PLAYWRIGHT_READONLY,
        ROUTING_LOCAL_AGENT_PLAYWRIGHT_READONLY,
        ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
        ROUTING_API_CONNECTOR,
        ROUTING_BLOCK,
        ROUTING_MANUAL_REVIEW,
    }
    if result.get("routing_decision") not in valid_decisions:
        errors.append(f"유효하지 않은 routing_decision: {result.get('routing_decision')}")

    valid_engines = {
        ENGINE_SEL_SERVER_PLAYWRIGHT,
        ENGINE_SEL_LOCAL_AGENT_PLAYWRIGHT,
        ENGINE_SEL_LOCAL_SYSTEM_BROWSER,
        ENGINE_SEL_API_CONNECTOR,
        ENGINE_SEL_NONE,
    }
    if result.get("selected_engine") not in valid_engines:
        errors.append(f"유효하지 않은 selected_engine: {result.get('selected_engine')}")

    return errors


def _make_routing(  # noqa: PLR0913 - 내부 라우팅 결과 dict 생성 헬퍼, 필드 나열형
    routing_decision: str,
    selected_engine: str,
    server_playwright_first_allowed: bool = False,
    local_agent_fallback_allowed: bool = False,
    api_connector_required: bool = False,
    user_present_required: bool = False,
    manual_review_required: bool = False,
    automation_blocked: bool = False,
    block_reason: str = "",
    message_ko: str = "",
) -> dict[str, Any]:
    safe_to_dispatch = routing_decision in (
        ROUTING_SERVER_PLAYWRIGHT_READONLY,
        ROUTING_LOCAL_AGENT_PLAYWRIGHT_READONLY,
    )
    return {
        "routing_decision": routing_decision,
        "selected_engine": selected_engine,
        "server_playwright_first_allowed": server_playwright_first_allowed,
        "local_agent_fallback_allowed": local_agent_fallback_allowed,
        "api_connector_required": api_connector_required,
        "user_present_required": user_present_required,
        "manual_review_required": manual_review_required,
        "automation_blocked": automation_blocked or (routing_decision == ROUTING_BLOCK),
        "block_reason": block_reason,
        "safe_to_dispatch": safe_to_dispatch,
        "safe_to_execute": False,
        "message_ko": message_ko,
    }
