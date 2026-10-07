"""
통합 브라우저 실행 라우터 (Unified Browser Execution Router)

외부 웹 작업은 LOCAL_BROWSER_DEFAULT로 기본 처리한다.
서버에서 외부 사이트 브라우저 원격 접속을 시도하지 않는다.

실행 흐름:
1. task 입력 검증
2. domain profile 조회
3. execution location 1차 분류
4. BLOCKED → 차단 사유 반환
5. USER_DIRECT_ONLY → 사용자 직접 수행 안내
6. LOCAL_BROWSER_DEFAULT → local_agent_handoff 즉시 생성 (서버 시도 없음)
7. SERVER_ALLOWED → 서버 실행 (내부/공개 API만)
8. server_result 있는 경우 → 신호 분석 → fallback 판정
9. 안전성 검증 후 반환

보안 고정 원칙:
- 쿠키/session/password/OTP/인증서 수집 없음
- 투찰/서명/결제/제출 자동화 없음
- wildcard domain 허용 없음
- 서버 브라우저로 나라장터/홈택스/은행/카드/보험 접속 금지
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
    get_domain_profile,
)
from ai_orchestrator.browser_tool.policy.security_signal_detector import (
    detect_from_result,
)
from ai_orchestrator.browser_tool.routing.execution_location_policy import (
    BLOCKED,
    LOCAL_BROWSER_DEFAULT,
    LOCAL_REQUIRED,
    SERVER_ONLY,
    USER_DIRECT_ONLY,
    classify_execution_location,
)
from ai_orchestrator.browser_tool.routing.fallback_decision_engine import (
    COMPLETE_ON_SERVER,
    HANDOFF_TO_LOCAL_AGENT,
    REQUIRE_USER_DIRECT_ACTION,
    RETRY_ON_SERVER,
    decide_fallback,
)
from ai_orchestrator.browser_tool.routing.local_agent_handoff import (
    build_local_agent_handoff,
    handoff_to_task_protocol,
    validate_handoff_payload,
)
from ai_orchestrator.browser_tool.unified_browser_safe_result import (
    EXEC_BLOCKED,
    EXEC_LOCAL_AGENT,
    EXEC_SERVER_BROWSER,
    EXEC_USER_DIRECT,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_LOCAL_HANDOFF_CREATED,
    STATUS_SUCCESS,
    STATUS_USER_ACTION_REQUIRED,
    build_safe_result,
    validate_safe_result,
)
from ai_orchestrator.browser_tool.unified_browser_task_schema import (
    build_safe_task,
    validate_task_input,
)

logger = logging.getLogger(__name__)


def _server_external_web_block(task: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    """runtime_context=server 에서 외부 웹 action 이면 BLOCKED 결과, 아니면 None."""
    from ai_orchestrator.server.execution_location_guard import (
        BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION,
        LOCAL_AGENT_REQUIRED,
        classify_execution_location_for_server,
    )

    cls = classify_execution_location_for_server(task)
    if cls["execution_location"] == LOCAL_AGENT_REQUIRED:
        r = build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used="BLOCKED",
            final_status="BLOCKED",
            fallback_reason=BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION,
            message_ko="외부 웹사이트 작업은 사용자 PC 로컬 에이전트에서 실행해야 합니다.",
        )
        # status / blocked_reason 키 별칭
        r["status"] = "BLOCKED"
        r["blocked_reason"] = BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION
        # build_safe_result가 누락한 safe fields 보강 — 항상 False 강제
        r.setdefault("storage_state_exported", False)
        r.setdefault("server_browser_used", False)
        return r
    return None


def _build_result_for_decision(
    decision: str,
    fallback: dict[str, Any],
    safe_task: dict[str, Any],
    task_id: str,
    signals: list[str],
) -> dict[str, Any]:
    """fallback 판정(decision)에 따른 safe result 생성."""
    if decision == COMPLETE_ON_SERVER:
        result = build_safe_result(
            task_id=task_id,
            ok=True,
            execution_used=EXEC_SERVER_BROWSER,
            final_status=STATUS_SUCCESS,
            security_signals=signals,
            message_ko=fallback["user_message_ko"],
        )

    elif decision == RETRY_ON_SERVER:
        result = build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_SERVER_BROWSER,
            final_status=STATUS_FAILED,
            security_signals=signals,
            fallback_reason=fallback["reason"],
            message_ko=fallback["user_message_ko"],
        )

    elif decision == HANDOFF_TO_LOCAL_AGENT:
        handoff = build_local_agent_handoff(
            task=safe_task,
            fallback_reason=fallback["reason"],
        )
        result = build_safe_result(
            task_id=task_id,
            ok=True,
            execution_used=EXEC_LOCAL_AGENT,
            final_status=STATUS_LOCAL_HANDOFF_CREATED,
            security_signals=signals,
            fallback_reason=fallback["reason"],
            message_ko=handoff["user_message_ko"],
            extra={"local_agent_handoff": handoff},
        )

    elif decision == REQUIRE_USER_DIRECT_ACTION:
        result = build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_USER_DIRECT,
            final_status=STATUS_USER_ACTION_REQUIRED,
            security_signals=signals,
            message_ko=fallback["user_message_ko"],
        )

    else:  # BLOCK
        result = build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_BLOCKED,
            final_status=STATUS_BLOCKED,
            security_signals=signals,
            message_ko=fallback["user_message_ko"],
            extra={"block_reason": fallback["reason"]},
        )

    return result


def _local_handoff_result(
    safe_task: dict[str, Any],
    task_id: str,
    location_result: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """LOCAL_BROWSER_DEFAULT/LOCAL_REQUIRED → 서버 시도 없이 즉시 local handoff 결과."""
    handoff = build_local_agent_handoff(
        task=safe_task,
        fallback_reason=location_result["reason"],
    )
    violations = validate_handoff_payload(handoff)
    if violations:
        return build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_BLOCKED,
            final_status=STATUS_BLOCKED,
            message_ko=f"handoff 안전성 위반: {violations}",
        )
    # task_protocol 형태로 변환하여 server task queue 전달 준비
    task_proto = handoff_to_task_protocol(handoff, task_id=task_id)
    return build_safe_result(
        task_id=task_id,
        ok=True,
        execution_used=EXEC_LOCAL_AGENT,
        final_status=STATUS_LOCAL_HANDOFF_CREATED,
        message_ko=handoff["user_message_ko"],
        extra={
            "local_agent_handoff": handoff,
            "local_playwright_task": task_proto,
            "execution_location": LOCAL_BROWSER_DEFAULT,
            "domain_profile_category": profile.get("category"),
        },
    )


def route_browser_task(
    task: dict[str, Any],
    server_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    통합 실행 라우터 메인 함수.

    외부 웹 task는 local_agent_handoff를 즉시 생성한다.
    서버 실행은 SERVER_ALLOWED(내부/공개 API)만 허용한다.

    server_result가 None이면 dry-run 모드.
    server_result가 있으면 fallback 판정까지 수행.

    runtime_context: "server" | "local_agent" — server에서 외부 URL은 즉시 BLOCKED.
    """
    task_id = task.get("task_id", "")
    runtime_context = (task.get("runtime_context") or "").lower()

    # runtime_context guard — server에서 외부 URL action은 즉시 차단
    if runtime_context == "server":
        blocked = _server_external_web_block(task, task_id)
        if blocked is not None:
            return blocked

    # 1. task 입력 검증
    validation = validate_task_input(task)
    if not validation["valid"]:
        return build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_BLOCKED,
            final_status=STATUS_BLOCKED,
            message_ko=f"입력 검증 실패: {'; '.join(validation['violations'])}",
        )

    safe_task = build_safe_task(task)

    # 2. domain profile 조회
    domain = _extract_domain(task)
    profile = get_domain_profile(domain)

    # 3. execution location 1차 분류
    location_result = classify_execution_location({**safe_task, "site_category": profile.get("category", "")})
    location = location_result["execution_location"]

    # 4. BLOCKED
    if location == BLOCKED:
        return build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_BLOCKED,
            final_status=STATUS_BLOCKED,
            message_ko=location_result["user_message_ko"],
            extra={"block_reason": location_result["reason"]},
        )

    # 5. USER_DIRECT_ONLY
    if location == USER_DIRECT_ONLY:
        return build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_USER_DIRECT,
            final_status=STATUS_USER_ACTION_REQUIRED,
            message_ko=location_result["user_message_ko"],
        )

    # 6. LOCAL_BROWSER_DEFAULT (레거시 LOCAL_REQUIRED 포함) → 서버 시도 없이 즉시 handoff
    if location in (LOCAL_BROWSER_DEFAULT, LOCAL_REQUIRED):
        return _local_handoff_result(safe_task, task_id, location_result, profile)

    # 7. SERVER_ONLY (내부 전용)
    if location == SERVER_ONLY and server_result is None:
        return build_safe_result(
            task_id=task_id,
            ok=True,
            execution_used=EXEC_SERVER_BROWSER,
            final_status=STATUS_SUCCESS,
            message_ko="서버 내부에서 처리합니다.",
            extra={"execution_location": SERVER_ONLY, "dryrun": True},
        )

    # 8. SERVER_ALLOWED / SERVER_FIRST (내부/공개 API)
    if server_result is None:
        return build_safe_result(
            task_id=task_id,
            ok=True,
            execution_used=EXEC_SERVER_BROWSER,
            final_status=STATUS_SUCCESS,
            message_ko="서버에서 처리합니다.",
            extra={
                "execution_location": location,
                "dryrun": True,
                "domain_profile_category": profile.get("category"),
                "fallback_allowed": location_result["fallback_allowed"],
            },
        )

    # 9. 서버 결과 분석
    sig_result = detect_from_result(server_result)
    signals = sig_result.get("signals", [])
    http_status = int(server_result.get("http_status") or server_result.get("status_code") or 200)

    fallback = decide_fallback(
        task=safe_task,
        domain_profile=profile,
        server_result=server_result,
        security_signals=signals,
        http_status=http_status,
        error_type=server_result.get("error_type") or server_result.get("error") or "",
    )

    decision = fallback["decision"]

    result = _build_result_for_decision(decision, fallback, safe_task, task_id, signals)

    # 10. safe result 검증
    violations = validate_safe_result(result)
    if violations:
        return build_safe_result(
            task_id=task_id,
            ok=False,
            execution_used=EXEC_BLOCKED,
            final_status=STATUS_BLOCKED,
            message_ko=f"결과 안전성 검증 실패: {violations}",
        )

    return result


def classify_task_only(task: dict[str, Any]) -> dict[str, Any]:
    """
    실제 실행 없이 실행 위치만 분류한다. (dry-run)
    """
    domain = _extract_domain(task)
    profile = get_domain_profile(domain)
    location_result = classify_execution_location(
        {
            **build_safe_task(task),
            "site_category": profile.get("category", ""),
        }
    )
    return {
        "task_id": task.get("task_id", ""),
        "execution_location": location_result["execution_location"],
        "reason": location_result["reason"],
        "fallback_allowed": location_result["fallback_allowed"],
        "user_message_ko": location_result["user_message_ko"],
        "domain_profile_category": profile.get("category"),
        "domain_profile_login_execution": profile.get("login_execution"),
    }


def _extract_domain(task: dict[str, Any]) -> str:
    """task에서 domain을 추출한다."""
    if task.get("domain"):
        return task["domain"].lower().strip()
    url = task.get("target_url") or ""
    if url:
        try:
            return urlparse(url).netloc.lower()
        except Exception as exc:  # noqa: BLE001
            logger.debug("대상 URL 도메인 추출 실패(무시): %s", type(exc).__name__)
            pass
    return ""
