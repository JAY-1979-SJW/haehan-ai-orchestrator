"""
화이트리스트 실행기 — 최종 게이트
policy + risk + approval + adapter capability 모두 검사 후 실행
"""

import json
import logging
import os
import time
from pathlib import Path

from orchestrator_v1.tasks import command_adapter, file_adapter
from orchestrator_v1.core import audit_logger
from orchestrator_v1.core.logger import get_logger, log_event
from ai_orchestrator.core.logging_utils import truncate_large_text
from orchestrator_v1.core.models import ExecutionPlan, RiskAssessment, TaskRequest

log = get_logger("executor")

_HISTORY_PATH = Path(__file__).resolve().parents[2] / "storage" / "execution_history.jsonl"

_EXECUTABLE_LOW_ACTIONS = {"read_file", "list_dir", "inspect_logs", "status_check"}
_BLOCKED_LEVELS = {"high", "critical"}

_ADAPTER_MAP = {
    "read_file": "file",
    "list_dir": "file",
    "inspect_logs": "command",
    "status_check": "command",
    "edit_config": "file",
    "write_file": "file",
    "create_patch": "file",
    "run_shell": "command",
}


def _append_history(entry: dict) -> None:
    Path(_HISTORY_PATH).parent.mkdir(parents=True, exist_ok=True)
    with Path(_HISTORY_PATH).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _path_starts(child: str, parent: str) -> bool:
    # os.path.abspath 유지(STD-02 pathlib 전환 예외): Path.resolve()는 심볼릭 링크를
    # 따라가는데, 이 함수는 allowed/blocked 경로 포함 여부를 판정하는 보안 경계
    # 로직이다 — 심볼릭 링크로 우회 가능한 다른 정규화로 바꾸면 판정 의미가
    # 바뀔 위험이 있어 기존 동작(symlink 미해석)을 그대로 유지한다.
    p = os.path.normcase(os.path.normpath(os.path.abspath(parent)))
    c = os.path.normcase(os.path.normpath(os.path.abspath(child)))
    return c == p or c.startswith(p + os.sep)


def _blocked_command_hit(policy: dict, task: TaskRequest) -> str | None:
    blocked_cmds = policy.get("blocked_commands", [])
    for bc in blocked_cmds:
        if bc.lower() in task.target.lower() or bc.lower() in task.action_type.lower():
            return bc
    return None


def _blocked_path_hit(policy: dict, task: TaskRequest) -> str | None:
    blocked_paths = policy.get("blocked_paths", [])
    for bp in blocked_paths:
        if task.target.startswith(bp):
            return bp
    return None


def _can_execute_low(task: TaskRequest, policy: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if task.action_type not in _EXECUTABLE_LOW_ACTIONS:
        reasons.append(f"low action '{task.action_type}' is not in executable set (may be AI-only like summarize_text)")
        return False, reasons
    if os.path.sep in task.target or "/" in task.target:
        allowed_paths = policy.get("allowed_paths", [])
        blocked_paths = policy.get("blocked_paths", [])
        for bp in blocked_paths:
            if _path_starts(task.target, bp):
                reasons.append(f"target matches blocked path: '{bp}'")
                return False, reasons
        if allowed_paths:
            if not any(_path_starts(task.target, ap) for ap in allowed_paths):
                reasons.append(f"target path not in allowed_paths: {task.target}")
                return False, reasons
    return True, []


def can_execute(
    task: TaskRequest,
    risk: RiskAssessment,
    plan: ExecutionPlan,
    policy: dict,
    approval_valid: bool,
) -> tuple[bool, list[str]]:
    reasons = []
    level = risk.risk_level

    if level in _BLOCKED_LEVELS:
        reasons.append(f"risk level '{level}' is always blocked")
        return False, reasons

    if not plan.allowed:
        reasons.extend(plan.blocked_reasons)
        return False, reasons

    bc = _blocked_command_hit(policy, task)
    if bc is not None:
        reasons.append(f"blocked command pattern: '{bc}'")
        return False, reasons

    bp = _blocked_path_hit(policy, task)
    if bp is not None:
        reasons.append(f"target matches blocked path: '{bp}'")
        return False, reasons

    if level == "medium":
        if not approval_valid:
            reasons.append("medium action requires valid approval token")
            return False, reasons
        return True, []

    if level == "low":
        return _can_execute_low(task, policy)

    reasons.append(f"unhandled risk level: {level}")
    return False, reasons


def execute_allowed(
    task: TaskRequest,
    risk: RiskAssessment,
    plan: ExecutionPlan,
    policy: dict,
    approval_valid: bool,
    actor: str = "system",
) -> dict:
    ok, block_reasons = can_execute(task, risk, plan, policy, approval_valid)
    level = risk.risk_level

    base = {
        "task_id": task.task_id,
        "action_type": task.action_type,
        "target": task.target,
        "risk_level": level,
        "preview_only": False,
        "blocked_reasons": block_reasons,
    }

    allowed_paths = policy.get("allowed_paths", [])
    blocked_paths = policy.get("blocked_paths", [])

    # ── BLOCKED ──────────────────────────────────────────────
    if level in _BLOCKED_LEVELS or not ok:
        log_event(
            log,
            logging.WARNING,
            f"execution blocked: {'; '.join(block_reasons)}",
            event_type="EXECUTION_BLOCKED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
        )
        audit_logger.record(
            event_type="EXECUTION_BLOCKED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
            risk_level=level,
            note="; ".join(block_reasons),
            adapter=_ADAPTER_MAP.get(task.action_type, "none"),
        )
        entry = {
            **base,
            "execution_status": "BLOCKED",
            "exit_code": None,
            "actor": actor,
            "note": "; ".join(block_reasons),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "adapter": _ADAPTER_MAP.get(task.action_type, "none"),
        }
        _append_history(entry)
        return {**base, "status": "BLOCKED"}

    # ── MEDIUM → PREVIEW_ONLY ─────────────────────────────────
    if level == "medium":
        log_event(
            log,
            logging.INFO,
            "preview_only — no actual write",
            event_type="EXECUTION_PREVIEW",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
        )
        audit_logger.record(
            event_type="EXECUTION_PREVIEW",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
            risk_level=level,
            note="medium action — preview only",
        )
        adapter_result = {}
        if task.action_type in {"edit_config", "write_file", "create_patch"}:
            new_content = task.payload.get("new_content", "")
            adapter_result = file_adapter.preview_patch(task.target, new_content, allowed_paths, blocked_paths)
        _append_history(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "task_id": task.task_id,
                "adapter": "file",
                "action_type": task.action_type,
                "target": task.target,
                "execution_status": "PREVIEW_ONLY",
                "exit_code": None,
                "preview_only": True,
                "actor": actor,
                "note": "medium action — preview only, no actual write",
            }
        )
        return {**base, "status": "PREVIEW_ONLY", "preview_only": True, "adapter_result": adapter_result}

    # ── LOW → EXECUTE ─────────────────────────────────────────
    adapter = _ADAPTER_MAP.get(task.action_type, "none")
    log_event(
        log,
        logging.INFO,
        f"attempting execution via adapter={adapter}",
        event_type="EXECUTION_ALLOWED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor=actor,
    )
    audit_logger.record(
        event_type="EXECUTION_ALLOWED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor=actor,
        risk_level=level,
        adapter=adapter,
    )

    adapter_result = {}
    try:
        if task.action_type == "read_file":
            adapter_result = file_adapter.read_file(task.target, allowed_paths, blocked_paths)
        elif task.action_type == "list_dir":
            adapter_result = file_adapter.list_dir(task.target, allowed_paths, blocked_paths)
        elif task.action_type in {"inspect_logs", "status_check"}:
            cmd = task.payload.get("command", "")
            adapter_result = command_adapter.run_command(cmd, task.action_type)
        else:
            adapter_result = {"status": "BLOCKED", "reason": f"no adapter for '{task.action_type}'"}
    except Exception as e:  # noqa: BLE001 - 화이트리스트 액션 실행기 — 어댑터 실행 중 예외 발생 시 adapter_result.status를 ERROR로 설정해 exec_status가 BLOCKED로 판정되는 fail-closed 경로(EXECUTED가 아닌 BLOCKED로 귀결).
        log_event(
            log,
            logging.ERROR,
            f"unexpected exception: {e}",
            event_type="EXECUTION_FAILED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
        )
        audit_logger.record(
            event_type="EXECUTION_FAILED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
            note=str(e),
        )
        adapter_result = {"status": "ERROR", "reason": str(e)}

    exec_status = "EXECUTED" if adapter_result.get("status") == "OK" else "BLOCKED"
    exit_code = adapter_result.get("exit_code")

    if exec_status == "EXECUTED":
        log_event(
            log,
            logging.INFO,
            f"execution completed exit_code={exit_code}",
            event_type="EXECUTION_COMPLETED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
        )
        audit_logger.record(
            event_type="EXECUTION_COMPLETED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
            risk_level=level,
            adapter=adapter,
            exit_code=exit_code,
        )
    else:
        reason = truncate_large_text(adapter_result.get("reason", ""), max_len=200)
        log_event(
            log,
            logging.ERROR,
            f"execution failed: {reason}",
            event_type="EXECUTION_FAILED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
        )
        audit_logger.record(
            event_type="EXECUTION_FAILED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor=actor,
            note=reason,
        )

    _append_history(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "task_id": task.task_id,
            "adapter": adapter,
            "action_type": task.action_type,
            "target": task.target,
            "execution_status": exec_status,
            "exit_code": exit_code,
            "preview_only": False,
            "actor": actor,
            "note": adapter_result.get("reason", ""),
        }
    )
    return {**base, "status": exec_status, "adapter_result": adapter_result}
