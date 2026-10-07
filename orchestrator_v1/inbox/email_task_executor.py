"""
email task approval → execution 연결
- approval 승인/거절 상태 처리
- 승인된 task → ready 상태 전환
- risk_level 정책 적용 후 executor 호출
  low: execute_allowed() 호출
  medium: SKIPPED (정책상 실행 금지)
  high/critical: BLOCKED_POLICY
- 자동 실행 없음 — execute_email_task() 명시적 호출만
"""

import time

import audit_logger
from logger import get_logger
from models import ExecutionPlan, RiskAssessment, TaskRequest
from orchestrator_v1.inbox import email_task_approval, email_task_store
from whitelist_executor import execute_allowed

log = get_logger("email_task_executor")

_RISK_BLOCKED_LEVELS = {"high", "critical"}
_RISK_MEDIUM = "medium"

_DEFAULT_POLICY: dict[str, list[str]] = {
    "allowed_paths": [],
    "blocked_paths": [],
    "blocked_commands": [],
}


def approve_task(
    task_id: str,
    approved_by: str,
    *,
    token_path: str | None = None,
    task_path: str | None = None,
) -> dict:
    """
    email task의 pending approval 승인 처리.
    approval_status → approved, task status → ready.
    자동 실행 없음.
    """
    task = email_task_store.get_email_task(task_id, path=task_path)
    if task is None:
        return {"status": "not_found", "task_id": task_id}

    token = email_task_approval.get_approval_for_task(task_id, token_path=token_path)
    if token is None:
        return {"status": "no_approval_request", "task_id": task_id}

    token_id = token["token_id"]

    result = email_task_approval.approve(token_id, approved_by, token_path=token_path)
    if result["status"] != "approved":
        return {"status": "approval_failed", "task_id": task_id, "reason": result}

    email_task_store.update_email_task_approval(
        task_id=task_id,
        approval_token_id=token_id,
        approval_requested_at=task.get("approval_requested_at", ""),
        approval_status="approved",
        path=task_path,
    )
    email_task_store.update_email_task_status(task_id, "ready", path=task_path)

    audit_logger.record(
        "EMAIL_TASK_APPROVED",
        task_id=task_id,
        actor=approved_by,
        risk_level=task.get("risk_level"),
        note=f"approved by {approved_by}, token={token_id[:6]}***",
        item_id=task.get("source_item_id"),
    )
    audit_logger.record(
        "EMAIL_TASK_EXECUTION_READY",
        task_id=task_id,
        actor=approved_by,
        risk_level=task.get("risk_level"),
        note="task status=ready (not auto-executed)",
        item_id=task.get("source_item_id"),
    )

    log.info("email task approved: task_id=%s token=%s", task_id, token_id[:6] + "***")

    return {
        "status": "approved",
        "task_id": task_id,
        "token_id": token_id,
        "approval_status": "approved",
        "task_status": "ready",
        "note": "ready — call execute to run (subject to policy)",
    }


def reject_task(
    task_id: str,
    rejected_by: str,
    *,
    token_path: str | None = None,
    task_path: str | None = None,
) -> dict:
    """
    email task의 pending approval 거절 처리.
    approval_status → rejected, task status 유지(pending).
    """
    task = email_task_store.get_email_task(task_id, path=task_path)
    if task is None:
        return {"status": "not_found", "task_id": task_id}

    token = email_task_approval.get_approval_for_task(task_id, token_path=token_path)
    if token is None:
        return {"status": "no_approval_request", "task_id": task_id}

    token_id = token["token_id"]

    result = email_task_approval.reject(token_id, rejected_by, token_path=token_path)
    if result["status"] != "rejected":
        return {"status": "rejection_failed", "task_id": task_id, "reason": result}

    email_task_store.update_email_task_approval(
        task_id=task_id,
        approval_token_id=token_id,
        approval_requested_at=task.get("approval_requested_at", ""),
        approval_status="rejected",
        path=task_path,
    )
    # task status는 pending 유지 — update 하지 않음

    audit_logger.record(
        "EMAIL_TASK_REJECTED",
        task_id=task_id,
        actor=rejected_by,
        risk_level=task.get("risk_level"),
        note=f"rejected by {rejected_by}, token={token_id[:6]}***",
        item_id=task.get("source_item_id"),
    )

    log.info("email task rejected: task_id=%s", task_id)

    return {
        "status": "rejected",
        "task_id": task_id,
        "token_id": token_id,
        "approval_status": "rejected",
        "task_status": task.get("status", "pending"),
    }


def execute_email_task(
    task_id: str,
    *,
    task_path: str | None = None,
    token_path: str | None = None,
    actor: str = "email_task_executor",
) -> dict:
    """
    ready 상태의 email task 실행.
    risk_level 정책 적용:
      low → execute_allowed() 호출
      medium → SKIPPED (정책상 실행 금지)
      high/critical → BLOCKED_POLICY
    자동 실행 없음 — 명시적 호출만.
    """
    task = email_task_store.get_email_task(task_id, path=task_path)
    if not task:
        return {"status": "not_found", "task_id": task_id}

    if task.get("status") != "ready":
        return {
            "status": "not_ready",
            "task_id": task_id,
            "current_status": task.get("status"),
        }

    if task.get("approval_status") != "approved":
        return {
            "status": "not_approved",
            "task_id": task_id,
            "approval_status": task.get("approval_status"),
        }

    risk_level = task.get("risk_level", "medium")

    # high / critical — 항상 차단
    if risk_level in _RISK_BLOCKED_LEVELS:
        audit_logger.record(
            "EMAIL_TASK_EXECUTION_BLOCKED_POLICY",
            task_id=task_id,
            actor=actor,
            risk_level=risk_level,
            note=f"risk_level '{risk_level}' always blocked",
            item_id=task.get("source_item_id"),
        )
        log.warning("email task blocked by policy: task_id=%s risk=%s", task_id, risk_level)
        return {
            "status": "blocked_policy",
            "task_id": task_id,
            "risk_level": risk_level,
            "reason": f"risk_level '{risk_level}' is always blocked",
        }

    # medium — 정책상 실행 금지, SKIPPED
    if risk_level == _RISK_MEDIUM:
        audit_logger.record(
            "EMAIL_TASK_EXECUTION_SKIPPED",
            task_id=task_id,
            actor=actor,
            risk_level=risk_level,
            note="medium risk — execution skipped by policy",
            item_id=task.get("source_item_id"),
        )
        log.info("email task skipped (medium policy): task_id=%s", task_id)
        return {
            "status": "skipped",
            "task_id": task_id,
            "risk_level": risk_level,
            "note": "medium execution blocked by policy",
        }

    # low — execute_allowed() 호출
    task_req = _to_task_request(task)
    risk_obj = RiskAssessment(
        risk_level="low",
        reasons=["email task risk_level=low"],
        requires_approval=False,
    )
    plan = ExecutionPlan(
        task_id=task_id,
        allowed=True,
        requires_approval=False,
        steps=[f"execute {task_req.action_type}"],
        blocked_reasons=[],
    )

    audit_logger.record(
        "EMAIL_TASK_EXECUTION_STARTED",
        task_id=task_id,
        actor=actor,
        risk_level=risk_level,
        note="low risk email task execution starting",
        item_id=task.get("source_item_id"),
    )
    log.info("email task execution started: task_id=%s", task_id)

    start = time.time()
    try:
        result = execute_allowed(task_req, risk_obj, plan, _DEFAULT_POLICY, True, actor=actor)
    except Exception as exc:  # noqa: BLE001 - email task 실행(execute_allowed) 중 예외 발생 시 task 상태를 error로 기록하고 에러 반환 - 승인/실행 판정은 execute_allowed 내부에서 이미 끝났고 이 except는 실행 실패 후처리일 뿐, 성공으로 위장하지 않음
        log.error("email task execution error: task_id=%s error=%s", task_id, exc)
        email_task_store.update_email_task_status(task_id, "error", path=task_path)
        return {"status": "error", "task_id": task_id, "error": str(exc)}

    duration_ms = (time.time() - start) * 1000
    email_task_store.update_email_task_status(task_id, "executed", path=task_path)

    log.info(
        "email task executed: task_id=%s status=%s duration_ms=%.1f",
        task_id,
        result.get("status"),
        duration_ms,
    )
    return {**result, "task_id": task_id, "duration_ms": round(duration_ms, 2)}


def _to_task_request(task: dict) -> TaskRequest:
    """email task dict → TaskRequest 변환. executor 입력 형식으로만 변환."""
    return TaskRequest(
        task_id=task["task_id"],
        source="manual",
        action_type=task.get("task_type") or "email_task",
        target=task.get("title", task["task_id"]),
        description=task.get("title", ""),
        payload={},
        requested_by="email_approval",
    )
