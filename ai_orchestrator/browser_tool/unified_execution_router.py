"""
통합 브라우저 실행 라우터 (Unified Browser Execution Router)

사이트별 전용 도구를 만들지 않는다.
모든 사이트(나라장터/홈택스/은행/카드/보험/일반 웹)는 공통 실행 엔진을 사용한다.
사이트별 차이는 domain profile과 security signal로만 관리한다.

실행 흐름:
1. task 입력 검증
2. domain profile 조회
3. execution location 1차 분류
4. SERVER_FIRST면 서버 실행 시도 (dry-run 또는 실제)
5. 서버 결과 + security signal 분석
6. 성공이면 safe result 반환
7. fallback 필요하면 local_agent_handoff 생성
8. USER_DIRECT_ONLY면 사용자 직접 수행 안내
9. BLOCKED면 차단 사유 반환

보안 고정 원칙:
- 쿠키/session/password/OTP/인증서 수집 없음
- 투찰/서명/결제/제출 자동화 없음
- wildcard domain 허용 없음
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.browser_tool.execution_location_policy import (
    BLOCKED,
    LOCAL_REQUIRED,
    SERVER_FIRST,
    SERVER_ONLY,
    SERVER_TO_LOCAL_FALLBACK,
    USER_DIRECT_ONLY,
    classify_execution_location,
)
from ai_orchestrator.browser_tool.domain_profile_registry import (
    get_domain_profile,
)
from ai_orchestrator.browser_tool.security_signal_detector import (
    detect_from_result,
)
from ai_orchestrator.browser_tool.fallback_decision_engine import (
    BLOCK,
    COMPLETE_ON_SERVER,
    HANDOFF_TO_LOCAL_AGENT,
    REQUIRE_USER_DIRECT_ACTION,
    RETRY_ON_SERVER,
    decide_fallback,
)
from ai_orchestrator.browser_tool.local_agent_handoff import (
    build_local_agent_handoff,
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
    validate_task_input,
    build_safe_task,
)


def route_browser_task(
    task: dict[str, Any],
    server_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    통합 실행 라우터 메인 함수.

    task를 받아 실행 위치를 결정하고, safe result 또는 local_agent_handoff를 반환한다.

    server_result가 None이면 dry-run 모드(실행 위치 분류만 수행).
    server_result가 있으면 fallback 판정까지 수행.
    """
    task_id = task.get("task_id", "")

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

    # 6. LOCAL_REQUIRED (처음부터 로컬)
    if location == LOCAL_REQUIRED:
        handoff = build_local_agent_handoff(
            task=safe_task,
            fallback_reason=location_result["reason"],
        )
        return build_safe_result(
            task_id=task_id,
            ok=True,
            execution_used=EXEC_LOCAL_AGENT,
            final_status=STATUS_LOCAL_HANDOFF_CREATED,
            message_ko=handoff["user_message_ko"],
            extra={"local_agent_handoff": handoff},
        )

    # 7. SERVER_ONLY (dry-run)
    if location == SERVER_ONLY:
        if server_result is None:
            return build_safe_result(
                task_id=task_id,
                ok=True,
                execution_used=EXEC_SERVER_BROWSER,
                final_status=STATUS_SUCCESS,
                message_ko="서버 내부에서 처리합니다.",
                extra={"execution_location": SERVER_ONLY, "dryrun": True},
            )

    # 8. SERVER_FIRST / SERVER_TO_LOCAL_FALLBACK
    # server_result가 없으면 dry-run 모드
    if server_result is None:
        return build_safe_result(
            task_id=task_id,
            ok=True,
            execution_used=EXEC_SERVER_BROWSER,
            final_status=STATUS_SUCCESS,
            message_ko="서버에서 실행합니다.",
            extra={
                "execution_location": location,
                "dryrun": True,
                "domain_profile_category": profile.get("category"),
                "fallback_allowed": location_result["fallback_allowed"],
            },
        )

    # 9. 서버 결과 분석 (server_result 있는 경우)
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
    location_result = classify_execution_location({
        **build_safe_task(task),
        "site_category": profile.get("category", ""),
    })
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
        except Exception:
            pass
    return ""
