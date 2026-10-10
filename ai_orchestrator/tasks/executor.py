import json
import logging
import time
from collections.abc import Callable

from ..connectors import playwright_connector, system_connector
from ..core.execution_limits import (
    BLOCK_TIMEOUT,
    EXEC_TIMEOUT_SEC,
    check_execution_policy,
    check_rate_limits,
    record_execution,
    run_with_timeout,
)
from ..core.models import ExecutionPlan, TaskRequest

logger = logging.getLogger(__name__)

# whitelist: 실제 실행 가능한 read-only action 만 나열
ALLOWED_ACTIONS = [
    "get_server_status",
    "fetch_web_page",
]

BLOCK_NOT_ALLOWED = "not_allowed_action"


def _default_low_worker(req: TaskRequest) -> str:
    """submit_task low 경로 stub (기존 호환). 실제 실행은 execute_task 경로에서."""
    return "DRY_RUN_ONLY"


def _fetch_web_page_audit_extras(action_type: str, result: str) -> str:
    """fetch_web_page 에 대해 감사 note 에 덧붙일 해석용 문자열 생성.

    - 차단: ` blocked_reason=<reason>`
    - 성공: ` final_url=<url> http_status=<code>`
    - 기타: 빈 문자열
    """
    if action_type != "fetch_web_page":
        return ""
    if result.startswith("BLOCKED:"):
        return f" blocked_reason={result[len('BLOCKED:') :]}"
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    raw_data = parsed.get("data")
    data: dict = raw_data if isinstance(raw_data, dict) else {}
    final_url = data.get("final_url", "")
    http_status = data.get("http_status")
    return f" final_url={final_url} http_status={http_status}"


def _dispatch_allowed_action(req: TaskRequest) -> str:
    """whitelist 기반 실제 read-only 실행 디스패처."""
    if req.action_type == "get_server_status":
        data = system_connector.get_server_status()
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False)
    if req.action_type == "fetch_web_page":
        payload = playwright_connector.fetch_web_page(req.target)
        if payload.get("status") == "error":
            err = payload.get("error") or "fetch_error"
            return f"BLOCKED:{err}"
        return json.dumps(payload, ensure_ascii=False)
    # whitelist 검사를 통과했지만 디스패처에 경로가 없는 경우(방어)
    return f"BLOCKED:{BLOCK_NOT_ALLOWED}"


def execute(
    plan: ExecutionPlan,
    req: TaskRequest | None = None,
    risk_level: str = "",
    worker: Callable[[TaskRequest], str] | None = None,
    timeout_sec: int | None = None,
) -> str:
    """실행 디스패치. req/risk_level 을 전달하면 low 경로에 rate+timeout 적용.

    기존 콜러(execute(plan) 단독 호출)는 이전과 동일 동작.
    medium/high/critical 경로는 기존 그대로.
    """
    if not plan.allowed:
        reasons = "; ".join(plan.blocked_reasons)
        logger.warning("실행 차단 | task=%s | reasons=%s", plan.task_id, reasons)
        return f"BLOCKED: {reasons}"

    if plan.requires_approval:
        logger.info("실행 보류 — 승인 대기 | task=%s", plan.task_id)
        return "PENDING_APPROVAL"

    # 여기부터 allowed & !requires_approval → low 인라인 경로
    if req is None or risk_level != "low":
        # 리밋 미적용 (기존 호출 호환)
        logger.info("드라이런 실행 | task=%s", plan.task_id)
        return "DRY_RUN_ONLY"

    # low 경로: rate limit 체크
    allowed, reason = check_rate_limits(req)
    if not allowed:
        status = f"BLOCKED:{reason}"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            note=f"limit_hit={reason}",
        )
        logger.warning("실행 리밋 차단 | task=%s | reason=%s", req.task_id, reason)
        return status

    # 타임아웃 적용 실제 실행
    t = timeout_sec if timeout_sec is not None else EXEC_TIMEOUT_SEC
    w = worker or _default_low_worker
    t0 = time.time()
    try:
        result = run_with_timeout(lambda: w(req), t)
        duration_ms = int((time.time() - t0) * 1000)
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=result,
            risk_level=risk_level,
            duration_ms=duration_ms,
        )
        logger.info("low 실행 완료 | task=%s | %dms | %s", req.task_id, duration_ms, result)
        return result
    except TimeoutError:
        duration_ms = int((time.time() - t0) * 1000)
        status = f"BLOCKED:{BLOCK_TIMEOUT}"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            duration_ms=duration_ms,
            note=f"timeout={t}s",
        )
        logger.warning("low 실행 타임아웃 | task=%s | limit=%ds", req.task_id, t)
        return status


def execute_task(
    req: TaskRequest,
    risk_level: str,
    *,
    worker: Callable[[TaskRequest], str] | None = None,
    timeout_sec: int | None = None,
) -> str:
    """승인형 실제 실행 경로.

    규칙:
    - high/critical 은 여기까지 오면 안 된다 (planner/router 에서 차단). 방어적 조기 return.
    - medium: 호출 전에 승인이 완료되어 있어야 한다 (호출자 책임).
    - low: 재검증 후 직접 실행 (일반적으로는 submit_task 에서 이미 실행되므로 이 경로는 재실행 시에만 사용).

    기존 execute() 의 rate_limit(action/user) 에 더해,
    승인형 신규 정책(task cooldown / user 5min / 야간 차단)을 함께 적용한다.
    """
    if risk_level in ("high", "critical"):
        status = f"BLOCKED:{risk_level}_not_allowed"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            note="high/critical 실행 금지",
        )
        logger.warning("execute_task 차단 | task=%s | risk=%s", req.task_id, risk_level)
        return status

    # 기존 action/user 60s 리밋
    allowed, reason = check_rate_limits(req)
    if not allowed:
        status = f"BLOCKED:{reason}"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            note=f"limit_hit={reason}",
        )
        return status

    # 신규 승인형 정책 (task cooldown / user 5min / night)
    allowed, reason = check_execution_policy(req)
    if not allowed:
        status = f"BLOCKED:{reason}"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            note=f"policy_hit={reason}",
        )
        logger.warning("execute_task 정책 차단 | task=%s | reason=%s", req.task_id, reason)
        return status

    # whitelist 검사: 지정된 read-only action 만 실행 허용.
    # 외부에서 worker 를 명시적으로 주입한 경우(테스트/예외 루트)는 통과.
    if worker is None and req.action_type not in ALLOWED_ACTIONS:
        status = f"BLOCKED:{BLOCK_NOT_ALLOWED}"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            note=f"action_not_whitelisted={req.action_type}",
        )
        logger.warning("execute_task whitelist 차단 | task=%s | action=%s", req.task_id, req.action_type)
        return status

    t = timeout_sec if timeout_sec is not None else EXEC_TIMEOUT_SEC
    w = worker or _dispatch_allowed_action
    t0 = time.time()
    try:
        result = run_with_timeout(lambda: w(req), t)
        duration_ms = int((time.time() - t0) * 1000)
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=result,
            risk_level=risk_level,
            duration_ms=duration_ms,
            note=(
                f"approved_execution execution_type=REAL "
                f"action={req.action_type} target={req.target}" + _fetch_web_page_audit_extras(req.action_type, result)
            ),
        )
        logger.info("execute_task 완료 | task=%s | %dms | %s", req.task_id, duration_ms, result)
        return result
    except TimeoutError:
        duration_ms = int((time.time() - t0) * 1000)
        status = f"BLOCKED:{BLOCK_TIMEOUT}"
        record_execution(
            req.task_id,
            req.action_type,
            req.requested_by,
            status=status,
            risk_level=risk_level,
            duration_ms=duration_ms,
            note=f"timeout={t}s",
        )
        return status
