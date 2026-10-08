"""
Browser Engine Routing Preflight Chain

engine_capability 분류와 routing policy 결정을 기존 preflight chain 앞단에 연결한다.
분류 결과에 따라 필요한 체인 단계만 수행하고 불필요한 단계는 건너뛴다.

safe_to_execute: 항상 False.
click/type/fill/submit 코드 없음.
cookie/session/token 추출 없음.
인증서 비밀번호/OTP 입력 코드 없음.
dispatcher 실제 연결 없음.
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
    evaluate_server_browser_allowed,
)
from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance
from ai_orchestrator.browser_tool.preflight.action_registry_preflight import (
    evaluate_action_registry_preflight,
)
from ai_orchestrator.browser_tool.preflight.allowlist_preflight import evaluate_allowlist_preflight
from ai_orchestrator.browser_tool.preflight.gate_approval_preflight import (
    evaluate_gate_approval_preflight,
)
from ai_orchestrator.browser_tool.routing.browser_engine_capability_classifier import (
    ENGINE_API_CONNECTOR_REQUIRED,
    ENGINE_AUTOMATION_BLOCKED,
    ENGINE_LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED,
    ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    ENGINE_NEEDS_MANUAL_REVIEW,
    classify_browser_engine_capability,
)
from ai_orchestrator.browser_tool.routing.browser_engine_routing_policy import (
    evaluate_browser_engine_routing,
)

# ── next_step 허용값 ──────────────────────────────────────────────────────────

NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT = "SERVER_PLAYWRIGHT_READONLY_PREFLIGHT"
NEXT_LOCAL_AGENT_PLAYWRIGHT_READONLY = "LOCAL_AGENT_PLAYWRIGHT_READONLY"
NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT = "LOCAL_SYSTEM_BROWSER_USER_PRESENT"
NEXT_API_CONNECTOR = "API_CONNECTOR"
NEXT_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
NEXT_DOMAIN_VERIFICATION_REQUIRED = "DOMAIN_VERIFICATION_REQUIRED"
NEXT_BLOCKED = "BLOCKED"
NEXT_MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"

# ── chain_decision 허용값 ─────────────────────────────────────────────────────

CHAIN_PROCEED = "PROCEED"
CHAIN_ROUTE_API_CONNECTOR = "ROUTE_API_CONNECTOR"
CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER = "ROUTE_LOCAL_SYSTEM_BROWSER"
CHAIN_BLOCK = "BLOCK"
CHAIN_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
CHAIN_DOMAIN_VERIFICATION_REQUIRED = "DOMAIN_VERIFICATION_REQUIRED"
CHAIN_MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"

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

# ── fallback 허용 failure_reason ─────────────────────────────────────────────

_FALLBACK_ALLOWED_REASONS: frozenset[str] = frozenset(
    {
        "runtime_error",
        "network_timeout",
        "browser_not_available",
    }
)

_FALLBACK_BLOCKED_REASONS: frozenset[str] = frozenset(
    {
        "policy_blocked",
        "domain_blocked",
        "auth_required",
        "otp_required",
        "certificate_required",
        "captcha_required",
    }
)


def build_routing_preflight_chain_context(payload: dict[str, Any]) -> dict[str, Any]:
    """
    routing preflight chain 평가를 위한 컨텍스트를 구성한다.
    classifier와 routing policy를 실행하고 결과를 통합한다.
    """
    classification = classify_browser_engine_capability(payload)
    routing = evaluate_browser_engine_routing(payload)

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
        "approval_id": payload.get("approval_id", ""),
        "approval_required": payload.get("approval_required", False),
        "tenant_id": payload.get("tenant_id", ""),
        "user_id": payload.get("user_id", ""),
        "site_id": payload.get("site_id", ""),
        "dry_run": payload.get("dry_run", True),
        "engine_capability": classification["engine_capability"],
        "recommended_route": classification["recommended_route"],
        "routing_decision": routing["routing_decision"],
        "selected_engine": routing["selected_engine"],
        "server_playwright_first_allowed": routing["server_playwright_first_allowed"],
        "local_agent_fallback_allowed": routing["local_agent_fallback_allowed"],
        "routing_block_reason": routing["block_reason"],
        "routing_user_present_required": routing["user_present_required"],
        "routing_api_connector_required": routing["api_connector_required"],
        "routing_automation_blocked": routing["automation_blocked"],
        "routing_manual_review_required": routing["manual_review_required"],
    }


def _chain(ctx: dict[str, Any], chain_decision: str, next_step: str, **fields: Any) -> dict[str, Any]:
    """ctx 의 engine/routing/selected_engine 을 채워 _make_chain_result 를 호출한다."""
    return _make_chain_result(
        chain_decision=chain_decision,
        engine_capability=ctx["engine_capability"],
        routing_decision=ctx["routing_decision"],
        selected_engine=ctx["selected_engine"],
        next_step=next_step,
        **fields,
    )


# engine capability → (chain_decision, next_step, block_reason, ctx.routing_block_reason 우선 여부,
#                      message_ko, should_write_audit)  — 3단계 조기 라우팅
_ENGINE_EARLY_ROUTES: dict[str, tuple[str, str, str, bool, str, bool]] = {
    ENGINE_AUTOMATION_BLOCKED: (
        CHAIN_BLOCK, NEXT_BLOCKED, "AUTOMATION_BLOCKED", True,
        "자동화가 차단된 사이트입니다.", True,
    ),
    ENGINE_NEEDS_MANUAL_REVIEW: (
        CHAIN_MANUAL_REVIEW_REQUIRED, NEXT_MANUAL_REVIEW_REQUIRED, "NEEDS_MANUAL_REVIEW", True,
        "수동 실사 및 사용자 승인이 필요합니다.", False,
    ),
    ENGINE_API_CONNECTOR_REQUIRED: (
        CHAIN_ROUTE_API_CONNECTOR, NEXT_API_CONNECTOR, "", False,
        "공식 API/OAuth 경로로 처리합니다.", False,
    ),
    ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED: (
        CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER, NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT, "", False,
        "사용자 직접 브라우저 접근이 필요합니다.", False,
    ),
    ENGINE_LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED: (
        CHAIN_PROCEED, NEXT_LOCAL_AGENT_PLAYWRIGHT_READONLY, "", False,
        "로컬 Agent Playwright read-only 라우팅.", False,
    ),
}


def _early_stage_result(ctx: dict[str, Any], operation_type: str) -> dict[str, Any] | None:
    """1~3단계: production_mode → type/submit → engine capability 조기 라우팅 (순서 고정)."""
    # ── 1단계: production_mode → 즉시 BLOCK ──────────────────────────────────
    if ctx["production_mode"] is True:
        return _chain(
            ctx, CHAIN_BLOCK, NEXT_BLOCKED,
            block_reason="production_mode=true: 모든 preflight chain 차단.",
            message_ko="production_mode=true: 브라우저 preflight chain 차단.",
            should_write_audit=True,
        )

    # ── 2단계: type/submit → 즉시 BLOCK ──────────────────────────────────────
    if operation_type in _BLOCKED_OPERATIONS:
        return _chain(
            ctx, CHAIN_BLOCK, NEXT_BLOCKED,
            block_reason=f"operation_type={operation_type}: 자동 실행 route 금지.",
            message_ko=f"{operation_type} 자동 실행은 preflight chain에서 차단됩니다.",
            should_write_audit=True,
        )

    # ── 3단계: engine capability 기반 조기 라우팅 ────────────────────────────
    route = _ENGINE_EARLY_ROUTES.get(ctx["engine_capability"])
    if route is None:
        return None
    chain_decision, next_step, reason, use_routing_reason, message_ko, audit = route
    block_reason = (ctx["routing_block_reason"] or reason) if use_routing_reason else reason
    return _chain(
        ctx, chain_decision, next_step,
        block_reason=block_reason, message_ko=message_ko, should_write_audit=audit,
    )


def _is_domainless_allowed_url(target_domain: str, target_url: str) -> bool:
    """about:blank / data: URL처럼 도메인이 없는 허용 URL 여부."""
    return not target_domain and (
        not target_url or target_url == "about:blank" or target_url.startswith("data:")
    )


def _site_compliance_stage(ctx: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """4a. site_compliance_policy. (compliance_decision, 조기 종료 결과 또는 None)."""
    # about:blank / data: URL처럼 도메인이 없는 허용 URL은 site_compliance 건너뜀
    target_domain = ctx["target_domain"]
    target_url = ctx["target_url"]

    if _is_domainless_allowed_url(target_domain, target_url):
        compliance_decision = "ALLOW_BROWSER_READONLY"
        compliance_result: dict[str, Any] = {"compliance_decision": compliance_decision}
    else:
        compliance_result = evaluate_site_compliance(
            {
                "target_domain": target_domain,
                "target_url": target_url,
                "operation_type": ctx["operation_type"],
                "production_mode": ctx["production_mode"],
            }
        )
        compliance_decision = compliance_result.get("compliance_decision", "BLOCK")

    if compliance_decision == "REQUIRE_API_CONNECTOR":
        return compliance_decision, _chain(
            ctx, CHAIN_ROUTE_API_CONNECTOR, NEXT_API_CONNECTOR,
            site_compliance_decision=compliance_decision,
            block_reason="site_compliance: API connector 필요.",
            message_ko="사이트 정책상 공식 API/OAuth 경로가 필요합니다.",
            should_write_audit=False,
        )

    if compliance_decision == "BLOCK":
        return compliance_decision, _chain(
            ctx, CHAIN_BLOCK, NEXT_BLOCKED,
            site_compliance_decision=compliance_decision,
            block_reason=compliance_result.get("block_reason") or "SITE_COMPLIANCE_BLOCKED",
            message_ko=compliance_result.get("message_ko") or "사이트 정책상 차단되었습니다.",
            should_write_audit=True,
        )

    if compliance_decision == "REQUIRE_USER_PRESENT_LOCAL":
        return compliance_decision, _chain(
            ctx, CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER, NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
            site_compliance_decision=compliance_decision,
            block_reason="",
            message_ko="사이트 정책상 사용자 직접 접근이 필요합니다.",
            should_write_audit=False,
        )

    return compliance_decision, None


def _boundary_allowed_result() -> dict[str, Any]:
    return {
        "server_browser_decision": "SERVER_BROWSER_ALLOWED_READONLY",
        "server_browser_allowed": True,
        "block_reason": "",
        "message_ko": "",
    }


def _evaluate_boundary(ctx: dict[str, Any]) -> dict[str, Any]:
    """서버 브라우저 경계 정책 평가 결과 dict (server_browser_decision/allowed 포함)."""
    target_domain = ctx["target_domain"]
    target_url = ctx["target_url"]

    # about:blank / data: URL은 engine capability 분류에서 이미 허용 판정받음 → 건너뜀
    if _is_domainless_allowed_url(target_domain, target_url):
        return _boundary_allowed_result()

    # SERVER_PLAYWRIGHT_READONLY_ALLOWED인 경우 URL 기반 정책으로 확인
    # (category 기반 classify는 미분류 허용 URL을 차단하므로 URL 정책 우선 사용)
    from ai_orchestrator.browser_tool.worker.policy import evaluate_server_browser_url_policy  # lazy import

    url_policy = evaluate_server_browser_url_policy(
        target_url,
        metadata={"production_mode": ctx["production_mode"]},
    )
    if url_policy["allowed"]:
        return _boundary_allowed_result()

    # URL 정책에서 차단 → category 기반으로 추가 확인
    return evaluate_server_browser_allowed(
        {
            "site_category": ctx["site_category"],
            "target_domain": target_domain,
            "target_url": target_url,
            "execution_location": "server_browser",
            "requested_runtime": "server_playwright",
            "production_mode": ctx["production_mode"],
        }
    )


def _server_boundary_stage(ctx: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """4b. server_browser_boundary_policy. (boundary_decision, 조기 종료 결과 또는 None)."""
    boundary_result = _evaluate_boundary(ctx)
    boundary_decision = boundary_result.get("server_browser_decision", "BLOCK")
    boundary_allowed = boundary_result.get("server_browser_allowed", False)

    if boundary_allowed:
        return boundary_decision, None

    exec_loc = boundary_result.get("execution_location_required", "BLOCKED")
    if exec_loc == "API_ONLY":
        return boundary_decision, _chain(
            ctx, CHAIN_ROUTE_API_CONNECTOR, NEXT_API_CONNECTOR,
            server_boundary_decision=boundary_decision,
            block_reason=boundary_result.get("block_reason") or "SERVER_BOUNDARY_API_REQUIRED",
            message_ko="서버 경계 정책상 API 경로가 필요합니다.",
            should_write_audit=False,
        )
    if exec_loc == "USER_PRESENT_ONLY":
        return boundary_decision, _chain(
            ctx, CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER, NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
            server_boundary_decision=boundary_decision,
            block_reason="",
            message_ko="서버 경계 정책상 사용자 직접 접근이 필요합니다.",
            should_write_audit=False,
        )
    return boundary_decision, _chain(
        ctx, CHAIN_BLOCK, NEXT_BLOCKED,
        server_boundary_decision=boundary_decision,
        block_reason=boundary_result.get("block_reason") or "SERVER_BOUNDARY_BLOCKED",
        message_ko=boundary_result.get("message_ko") or "서버 브라우저 경계 정책상 차단.",
        should_write_audit=True,
    )


def _approval_preflight_payload(ctx: dict[str, Any]) -> dict[str, Any]:
    """action registry / gate approval preflight 공통 입력."""
    return {
        "workflow_run_id": ctx["workflow_run_id"],
        "workflow_id": ctx["workflow_id"],
        "action_name": ctx["action_name"] or "browser.inspect",
        "operation_type": ctx["operation_type"] or "read",
        "approval_required": ctx["approval_required"],
        "approval_id": ctx["approval_id"],
        "tenant_id": ctx["tenant_id"],
        "user_id": ctx["user_id"],
        "site_id": ctx["site_id"],
        "target_domain": ctx["target_domain"],
        "production_mode": ctx["production_mode"],
        "dry_run": ctx["dry_run"],
    }


def _action_registry_stage(
    ctx: dict[str, Any], compliance_decision: str, boundary_decision: str
) -> tuple[str, dict[str, Any] | None]:
    """4c. action_registry_preflight. (action_decision, 조기 종료 결과 또는 None)."""
    action_result = evaluate_action_registry_preflight(_approval_preflight_payload(ctx))
    action_decision = action_result.get("preflight_decision", "BLOCK")
    prior = {
        "site_compliance_decision": compliance_decision,
        "server_boundary_decision": boundary_decision,
        "action_preflight_decision": action_decision,
    }

    if action_decision in ("REQUIRE_APPROVAL", "BLOCK", "DENY_BY_DEFAULT"):
        if action_decision == "REQUIRE_APPROVAL":
            return action_decision, _chain(
                ctx, CHAIN_APPROVAL_REQUIRED, NEXT_APPROVAL_REQUIRED,
                block_reason=action_result.get("block_reason") or "APPROVAL_REQUIRED",
                message_ko="승인이 필요합니다.",
                should_write_audit=True,
                **prior,
            )
        return action_decision, _chain(
            ctx, CHAIN_BLOCK, NEXT_BLOCKED,
            block_reason=action_result.get("block_reason") or "ACTION_REGISTRY_BLOCKED",
            message_ko=action_result.get("message_ko") or "액션 레지스트리 정책상 차단.",
            should_write_audit=True,
            **prior,
        )

    # 도메인 검증 필요 여부 확인
    if action_result.get("needs_domain_verification"):
        return action_decision, _chain(
            ctx, CHAIN_DOMAIN_VERIFICATION_REQUIRED, NEXT_DOMAIN_VERIFICATION_REQUIRED,
            block_reason="DOMAIN_VERIFICATION_REQUIRED",
            message_ko="도메인 실사 및 승인이 필요합니다.",
            should_write_audit=True,
            **prior,
        )
    return action_decision, None


def _gate_approval_stage(
    ctx: dict[str, Any], compliance_decision: str, boundary_decision: str, action_decision: str
) -> tuple[str, dict[str, Any] | None]:
    """4d. gate_approval_preflight. (gate_decision, 조기 종료 결과 또는 None)."""
    gate_result = evaluate_gate_approval_preflight(_approval_preflight_payload(ctx))
    gate_decision = gate_result.get("preflight_decision", "BLOCK")
    prior = {
        "site_compliance_decision": compliance_decision,
        "server_boundary_decision": boundary_decision,
        "action_preflight_decision": action_decision,
        "gate_preflight_decision": gate_decision,
    }

    if gate_decision in ("REQUIRE_APPROVAL", "BLOCK", "DENY_BY_DEFAULT"):
        if gate_decision == "REQUIRE_APPROVAL":
            return gate_decision, _chain(
                ctx, CHAIN_APPROVAL_REQUIRED, NEXT_APPROVAL_REQUIRED,
                block_reason=gate_result.get("block_reason") or "APPROVAL_REQUIRED",
                message_ko="게이트 승인이 필요합니다.",
                should_write_audit=True,
                **prior,
            )
        return gate_decision, _chain(
            ctx, CHAIN_BLOCK, NEXT_BLOCKED,
            block_reason=gate_result.get("block_reason") or "GATE_BLOCKED",
            message_ko=gate_result.get("message_ko") or "게이트 승인 정책상 차단.",
            should_write_audit=True,
            **prior,
        )
    return gate_decision, None


def evaluate_browser_engine_routing_preflight_chain(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    engine capability 분류 → routing policy → site compliance →
    server boundary → action registry → gate approval → allowlist
    순서로 preflight chain을 수행한다.

    반환 필드:
    - chain_decision, engine_capability, routing_decision, selected_engine
    - site_compliance_decision, server_boundary_decision
    - action_preflight_decision, gate_preflight_decision, allowlist_decision
    - next_step, next_step_instruction
    - safe_to_dispatch, safe_to_execute
    - should_write_audit, block_reason, message_ko
    """
    ctx = build_routing_preflight_chain_context(payload)
    operation_type = (ctx["operation_type"] or "").lower()

    # ── 1~3단계: production / type·submit / engine capability 조기 라우팅 ────
    early = _early_stage_result(ctx, operation_type)
    if early is not None:
        return early

    # ── 4단계: SERVER_PLAYWRIGHT_READONLY_ALLOWED → 기존 preflight chain 수행 ─
    compliance_decision, early = _site_compliance_stage(ctx)
    if early is not None:
        return early

    boundary_decision, early = _server_boundary_stage(ctx)
    if early is not None:
        return early

    action_decision, early = _action_registry_stage(ctx, compliance_decision, boundary_decision)
    if early is not None:
        return early

    gate_decision, early = _gate_approval_stage(ctx, compliance_decision, boundary_decision, action_decision)
    if early is not None:
        return early

    # 4e. allowlist_preflight
    allowlist_result = evaluate_allowlist_preflight(
        {
            "workflow_run_id": ctx["workflow_run_id"],
            "workflow_id": ctx["workflow_id"],
            "action_name": ctx["action_name"] or "browser.inspect",
            "operation_type": ctx["operation_type"] or "read",
            "target_url": ctx["target_url"],
            "target_domain": ctx["target_domain"],
            "production_mode": ctx["production_mode"],
            "dry_run": ctx["dry_run"],
            "action_registry_preflight_decision": action_decision,
            "gate_preflight_decision": gate_decision,
        }
    )
    allowlist_decision = allowlist_result.get("allowlist_decision", "BLOCK")
    prior = {
        "site_compliance_decision": compliance_decision,
        "server_boundary_decision": boundary_decision,
        "action_preflight_decision": action_decision,
        "gate_preflight_decision": gate_decision,
        "allowlist_decision": allowlist_decision,
    }

    if allowlist_decision == "BLOCK":
        return _chain(
            ctx, CHAIN_BLOCK, NEXT_BLOCKED,
            block_reason=allowlist_result.get("block_reason") or "ALLOWLIST_BLOCKED",
            message_ko=allowlist_result.get("message_ko") or "allowlist 정책상 차단.",
            should_write_audit=True,
            **prior,
        )

    # ── 5단계: 모든 체인 통과 → SERVER_PLAYWRIGHT_READONLY_PREFLIGHT ──────────
    return _chain(
        ctx, CHAIN_PROCEED, NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT,
        block_reason="",
        message_ko="모든 preflight 체인 통과. 서버 Playwright read-only 대기.",
        should_write_audit=False,
        **prior,
    )


def build_next_step_instruction(result: dict[str, Any]) -> dict[str, Any]:
    """
    chain 결과에서 다음 단계 실행 지침을 구성한다.
    secret/token/cookie/session 포함 금지.
    """
    next_step = result.get("next_step", NEXT_BLOCKED)
    return {
        "next_step": next_step,
        "chain_decision": result.get("chain_decision", CHAIN_BLOCK),
        "engine_capability": result.get("engine_capability", ""),
        "routing_decision": result.get("routing_decision", ""),
        "selected_engine": result.get("selected_engine", "none"),
        "safe_to_dispatch": result.get("safe_to_dispatch", False),
        "safe_to_execute": False,
        "block_reason": result.get("block_reason", ""),
        "message_ko": result.get("message_ko", ""),
        "should_write_audit": result.get("should_write_audit", False),
    }


def validate_routing_preflight_chain_result(result: dict[str, Any]) -> list[str]:
    """
    chain 결과의 필수 필드 및 정책 준수를 검증한다.
    """
    errors: list[str] = []

    required_fields = [
        "chain_decision",
        "engine_capability",
        "routing_decision",
        "selected_engine",
        "site_compliance_decision",
        "server_boundary_decision",
        "action_preflight_decision",
        "gate_preflight_decision",
        "allowlist_decision",
        "next_step",
        "next_step_instruction",
        "safe_to_dispatch",
        "safe_to_execute",
        "should_write_audit",
        "block_reason",
        "message_ko",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    valid_next_steps = {
        NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT,
        NEXT_LOCAL_AGENT_PLAYWRIGHT_READONLY,
        NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
        NEXT_API_CONNECTOR,
        NEXT_APPROVAL_REQUIRED,
        NEXT_DOMAIN_VERIFICATION_REQUIRED,
        NEXT_BLOCKED,
        NEXT_MANUAL_REVIEW_REQUIRED,
    }
    if result.get("next_step") not in valid_next_steps:
        errors.append(f"유효하지 않은 next_step: {result.get('next_step')}")

    valid_chain_decisions = {
        CHAIN_PROCEED,
        CHAIN_ROUTE_API_CONNECTOR,
        CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER,
        CHAIN_BLOCK,
        CHAIN_APPROVAL_REQUIRED,
        CHAIN_DOMAIN_VERIFICATION_REQUIRED,
        CHAIN_MANUAL_REVIEW_REQUIRED,
    }
    if result.get("chain_decision") not in valid_chain_decisions:
        errors.append(f"유효하지 않은 chain_decision: {result.get('chain_decision')}")

    return errors


def _make_chain_result(  # noqa: PLR0913 - 내부 체인 결과 dict 생성 헬퍼, 필드 나열형
    chain_decision: str,
    engine_capability: str,
    routing_decision: str,
    selected_engine: str,
    next_step: str,
    site_compliance_decision: str = "SKIPPED",
    server_boundary_decision: str = "SKIPPED",
    action_preflight_decision: str = "SKIPPED",
    gate_preflight_decision: str = "SKIPPED",
    allowlist_decision: str = "SKIPPED",
    block_reason: str = "",
    message_ko: str = "",
    should_write_audit: bool = False,
) -> dict[str, Any]:
    safe_to_dispatch = chain_decision == CHAIN_PROCEED and next_step == NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT
    result: dict[str, Any] = {
        "chain_decision": chain_decision,
        "engine_capability": engine_capability,
        "routing_decision": routing_decision,
        "selected_engine": selected_engine,
        "site_compliance_decision": site_compliance_decision,
        "server_boundary_decision": server_boundary_decision,
        "action_preflight_decision": action_preflight_decision,
        "gate_preflight_decision": gate_preflight_decision,
        "allowlist_decision": allowlist_decision,
        "next_step": next_step,
        "safe_to_dispatch": safe_to_dispatch,
        "safe_to_execute": False,
        "should_write_audit": should_write_audit,
        "block_reason": block_reason,
        "message_ko": message_ko,
    }
    result["next_step_instruction"] = build_next_step_instruction(result)
    return result
