"""
실행 엔진 (6단계) — 승인 이후 실제 task 실행 처리
low / medium 만 실행. high / critical 은 승인돼도 실행 금지.
결과는 logs/execution.jsonl 에 append 기록 (10MB × 10 rotation).
"""
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

import approval_manager
import task_store
from approval_manager import build_execution_plan, is_token_valid
from logger import get_logger
from whitelist_executor import execute_allowed

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_EXEC_LOG_PATH = os.path.join(_BASE_DIR, "logs", "execution.jsonl")

_BLOCKED_LEVELS = {"high", "critical"}

log = get_logger("executor")

# ── execution.jsonl rotating writer ──────────────────────────────────────────

_exec_logger: logging.Logger | None = None


class _ExecJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _get_exec_logger() -> logging.Logger:
    global _exec_logger
    if _exec_logger is not None:
        return _exec_logger
    os.makedirs(os.path.dirname(_EXEC_LOG_PATH), exist_ok=True)
    lg = logging.getLogger("orchestrator.execution_jsonl")
    # 재초기화 시 기존 핸들러 제거 (경로 변경 반영)
    for h in lg.handlers[:]:
        h.close()
        lg.removeHandler(h)
    fh = RotatingFileHandler(
        _EXEC_LOG_PATH,
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    fh.setFormatter(_ExecJsonFormatter())
    lg.addHandler(fh)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    _exec_logger = lg
    return _exec_logger


def _log_execution(task_id: str, status: str, duration_ms: float, error: str = None) -> None:
    entry = {
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "task_id":     task_id,
        "status":      status,
        "duration_ms": round(duration_ms, 2),
        "error":       error,
    }
    _get_exec_logger().info(json.dumps(entry, ensure_ascii=False))


def execute_task(task_id: str) -> dict:
    """
    task_id로 task_store에서 컨텍스트를 조회해 실행.
    반환: {task_id, status, risk_level, duration_ms, ...}
    """
    start = time.time()

    ctx = task_store.get(task_id)
    if not ctx:
        duration = (time.time() - start) * 1000
        _log_execution(task_id, "FAIL", duration, "task not found in task_store")
        log.warning("execute_task: task_id=%s not found in store", task_id)
        return {"task_id": task_id, "status": "FAIL", "error": "task not found in task_store"}

    task   = ctx["task"]
    risk   = ctx["risk"]
    policy = ctx["policy"]
    level  = risk.risk_level

    # high / critical — 승인돼도 실행 금지
    if level in _BLOCKED_LEVELS:
        duration = (time.time() - start) * 1000
        reason = f"risk level '{level}' is always blocked"
        _log_execution(task_id, "BLOCKED", duration, reason)
        log.warning("execute_task blocked: task_id=%s risk=%s", task_id, level)
        return {"task_id": task_id, "status": "BLOCKED", "risk_level": level, "error": reason}

    # 승인 토큰 유효성 확인
    token_id = None
    approval_valid = False
    for tid, entry in approval_manager._store.items():
        if entry.get("task_id") == task_id:
            token_id = tid
            approval_valid = is_token_valid(tid)
            break

    # low 는 토큰 없이도 실행 가능
    if level == "low":
        approval_valid = True

    plan = build_execution_plan(task, risk, token_id if approval_valid else None)

    try:
        result = execute_allowed(task, risk, plan, policy, approval_valid, actor="dashboard_executor")
    except Exception as exc:
        duration = (time.time() - start) * 1000
        _log_execution(task_id, "FAIL", duration, str(exc))
        log.error("execute_task exception: task_id=%s error=%s", task_id, exc)
        return {"task_id": task_id, "status": "FAIL", "error": str(exc)}

    duration = (time.time() - start) * 1000
    exec_status = result.get("status", "UNKNOWN")
    log_status  = "SUCCESS" if exec_status == "EXECUTED" else exec_status
    error_msg   = "; ".join(result.get("blocked_reasons", [])) if exec_status == "BLOCKED" else None

    _log_execution(task_id, log_status, duration, error_msg)
    log.info("execute_task: task_id=%s status=%s duration_ms=%.1f", task_id, log_status, duration)

    return {**result, "duration_ms": duration}
