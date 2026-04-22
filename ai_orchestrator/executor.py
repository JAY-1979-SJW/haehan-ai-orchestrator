import logging
import time
from typing import Callable, Optional

from .models import ExecutionPlan, TaskRequest
from .execution_limits import (
    check_rate_limits, record_execution, run_with_timeout,
    BLOCK_RATE_ACTION, BLOCK_RATE_USER, BLOCK_TIMEOUT,
    EXEC_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


def _default_low_worker(req: TaskRequest) -> str:
    """실제 실행 엔진 도입 전까지의 low 인라인 stub."""
    return "DRY_RUN_ONLY"


def execute(
    plan: ExecutionPlan,
    req: Optional[TaskRequest] = None,
    risk_level: str = "",
    worker: Optional[Callable[[TaskRequest], str]] = None,
    timeout_sec: Optional[int] = None,
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
        record_execution(req.task_id, req.action_type, req.requested_by,
                         status=status, risk_level=risk_level,
                         note=f"limit_hit={reason}")
        logger.warning("실행 리밋 차단 | task=%s | reason=%s", req.task_id, reason)
        return status

    # 타임아웃 적용 실제 실행
    t = timeout_sec if timeout_sec is not None else EXEC_TIMEOUT_SEC
    w = worker or _default_low_worker
    t0 = time.time()
    try:
        result = run_with_timeout(lambda: w(req), t)
        duration_ms = int((time.time() - t0) * 1000)
        record_execution(req.task_id, req.action_type, req.requested_by,
                         status=result, risk_level=risk_level,
                         duration_ms=duration_ms)
        logger.info("low 실행 완료 | task=%s | %dms | %s",
                    req.task_id, duration_ms, result)
        return result
    except TimeoutError:
        duration_ms = int((time.time() - t0) * 1000)
        status = f"BLOCKED:{BLOCK_TIMEOUT}"
        record_execution(req.task_id, req.action_type, req.requested_by,
                         status=status, risk_level=risk_level,
                         duration_ms=duration_ms, note=f"timeout={t}s")
        logger.warning("low 실행 타임아웃 | task=%s | limit=%ds", req.task_id, t)
        return status
