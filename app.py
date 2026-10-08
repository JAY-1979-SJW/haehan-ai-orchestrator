"""
haehan-ai-orchestrator 시나리오 실행기 (3단계)
시나리오 A~E: low read/list, medium preview, high blocked, critical blocked
각 단계마다 운영 로그 + 감사 로그 기록
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import orchestrator_v1.core.audit_logger as audit_logger
import orchestrator_v1.tasks.task_store as task_store
from orchestrator_v1.core.logger import get_logger, log_event
from orchestrator_v1.core.models import TaskRequest
from orchestrator_v1.monitoring.telegram_notifier import send_approval_request
from orchestrator_v1.tasks.approval_manager import (
    approve_token,
    build_execution_plan,
    is_token_valid,
    issue_token,
)
from orchestrator_v1.tasks.policy_engine import load_policy
from orchestrator_v1.tasks.risk_assessor import assess_risk
from orchestrator_v1.tasks.whitelist_executor import execute_allowed

log = get_logger("app")


def _print_result(label: str, result: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  시나리오 {label}")
    print(f"{'=' * 60}")
    keys = [
        "task_id",
        "risk_level",
        "allowed",
        "requires_approval",
        "telegram_status",
        "adapter_used",
        "final_status",
        "preview_only",
        "blocked_reasons",
    ]
    display = {
        "task_id": result.get("task_id", ""),
        "risk_level": result.get("risk_level", ""),
        "allowed": result.get("plan_allowed", ""),
        "requires_approval": result.get("requires_approval", ""),
        "telegram_status": result.get("telegram_status", "N/A"),
        "adapter_used": result.get("adapter_used", ""),
        "final_status": result.get("status", ""),
        "preview_only": result.get("preview_only", False),
        "blocked_reasons": result.get("blocked_reasons", []),
    }
    for k in keys:
        print(f"  {k:<20}: {display[k]}")
    if result.get("adapter_result"):
        ar = result["adapter_result"]
        print(f"  {'adapter_result':<20}: status={ar.get('status')} | {list(ar.keys())}")
    if result.get("telegram_detail"):
        td = result["telegram_detail"]
        print(f"  {'telegram_detail':<20}: mock={td.get('mock')} sent={td.get('sent')}")


_ADAPTER_MAP_DISPLAY = {
    "read_file": "file_adapter",
    "list_dir": "file_adapter",
    "inspect_logs": "command_adapter",
    "status_check": "command_adapter",
    "edit_config": "file_adapter (preview)",
    "write_file": "file_adapter (preview)",
    "run_shell": "command_adapter",
    "restart_service": "none (blocked)",
    "delete_file": "none (blocked)",
}


def run_scenario(label: str, task: TaskRequest, mock_approve: bool = False) -> dict:
    # ── 요청 접수 ──────────────────────────────────────────────
    log_event(
        log,
        logging.INFO,
        f"scenario start: {label}",
        event_type="TASK_RECEIVED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor=task.requested_by,
    )
    audit_logger.record(
        event_type="TASK_RECEIVED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor=task.requested_by,
        note=task.description,
    )

    policy = load_policy()
    # Windows: storage 경로를 allowed_paths에 추가
    storage_path = str(Path(__file__).parent / "storage") + os.sep
    allowed = policy.get("allowed_paths", [])
    if storage_path not in allowed:
        allowed.append(storage_path)
    policy["allowed_paths"] = allowed

    # ── 위험도 판정 ────────────────────────────────────────────
    risk = assess_risk(task, policy)
    task_store.register(task, risk, policy)  # executor가 task_id로 조회 가능하게 등록
    log_event(
        log,
        logging.INFO,
        f"risk assessed: level={risk.risk_level} requires_approval={risk.requires_approval}",
        event_type="RISK_ASSESSED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor=task.requested_by,
    )
    audit_logger.record(
        event_type="RISK_ASSESSED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor=task.requested_by,
        risk_level=risk.risk_level,
        requires_approval=risk.requires_approval,
    )

    # ── 승인 토큰 발급 ─────────────────────────────────────────
    token_id = None
    tg_result = None

    if risk.requires_approval and risk.risk_level != "critical":
        token_id = issue_token(task, risk)
        log_event(
            log,
            logging.INFO,
            "approval token issued",
            event_type="APPROVAL_ISSUED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor="approval_manager",
        )
        # 토큰 원문 로그 금지 — token_id 앞 6자만 표기
        masked_token = (token_id[:6] + "***") if token_id else "N/A"
        audit_logger.record(
            event_type="APPROVAL_ISSUED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor="approval_manager",
            risk_level=risk.risk_level,
            token_prefix=masked_token,
        )

    # ── 실행 계획 수립 ─────────────────────────────────────────
    plan = build_execution_plan(task, risk, token_id)
    log_event(
        log,
        logging.INFO,
        f"plan created: allowed={plan.allowed} steps={len(plan.steps)}",
        event_type="PLAN_CREATED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor="approval_manager",
    )
    audit_logger.record(
        event_type="PLAN_CREATED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor="approval_manager",
        risk_level=risk.risk_level,
        plan_allowed=plan.allowed,
        blocked_reasons=plan.blocked_reasons,
    )

    # ── 텔레그램 승인 요청 ─────────────────────────────────────
    if risk.requires_approval:
        tg_result = send_approval_request(task, risk, plan, token_id)
        log_event(
            log,
            logging.INFO,
            f"approval request sent via telegram mock={tg_result.get('mock')}",
            event_type="APPROVAL_ISSUED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor="telegram_notifier",
        )

    # ── 승인 처리 (mock) ───────────────────────────────────────
    if mock_approve and token_id:
        approve_token(token_id)
        log_event(
            log,
            logging.INFO,
            "approval granted (mock)",
            event_type="APPROVAL_GRANTED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor="mock_approver",
        )
        audit_logger.record(
            event_type="APPROVAL_GRANTED",
            task_id=task.task_id,
            action_type=task.action_type,
            actor="mock_approver",
            note="mock approval in scenario test",
        )

    approval_valid = is_token_valid(token_id) if token_id else False

    # ── 실행 ──────────────────────────────────────────────────
    exec_result = execute_allowed(task, risk, plan, policy, approval_valid, actor="scenario_runner")

    # ── 결과 로그 ─────────────────────────────────────────────
    final_status = exec_result.get("status", "UNKNOWN")
    log_level = logging.INFO if final_status != "BLOCKED" else logging.WARNING
    log_event(
        log,
        log_level,
        f"scenario complete: final_status={final_status}",
        event_type="EXECUTION_COMPLETED" if final_status == "EXECUTED" else "EXECUTION_BLOCKED",
        task_id=task.task_id,
        action_type=task.action_type,
        actor="scenario_runner",
    )

    output = {
        **exec_result,
        "plan_allowed": plan.allowed,
        "requires_approval": risk.requires_approval,
        "adapter_used": _ADAPTER_MAP_DISPLAY.get(task.action_type, "none"),
        "telegram_status": (
            "sent" if tg_result and tg_result.get("sent") else "not_required" if not tg_result else "failed"
        ),
        "telegram_detail": tg_result,
    }
    _print_result(label, output)
    return output


def main():
    import tempfile

    tempfile.gettempdir()
    storage_dir = Path(__file__).parent / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    test_file = storage_dir / "test_read.txt"
    if not test_file.exists():
        with test_file.open("w") as f:
            f.write("hello orchestrator\n")

    log_event(log, logging.INFO, "=== orchestrator scenarios start ===", event_type="TASK_RECEIVED", actor="main")

    print("\n" + "=" * 60)
    print("  haehan-ai-orchestrator 시나리오 실행")
    print("=" * 60)

    run_scenario(
        "A: low read_file → EXECUTED",
        TaskRequest(
            task_id="task-A-001", source="pc", action_type="read_file", target=test_file, description="테스트 파일 읽기"
        ),
    )

    run_scenario(
        "B: low list_dir → EXECUTED",
        TaskRequest(
            task_id="task-B-001",
            source="pc",
            action_type="list_dir",
            target=storage_dir,
            description="스토리지 디렉토리 목록 조회",
        ),
    )

    run_scenario(
        "C: medium edit_config → PREVIEW_ONLY",
        TaskRequest(
            task_id="task-C-001",
            source="pc",
            action_type="edit_config",
            target=test_file,
            description="설정 파일 수정 시도",
            payload={"new_content": "updated config content\nnew line\n"},
        ),
        mock_approve=True,
    )

    run_scenario(
        "D: high restart_service → BLOCKED",
        TaskRequest(
            task_id="task-D-001",
            source="server",
            action_type="restart_service",
            target="nginx",
            description="nginx 재시작 요청",
        ),
        mock_approve=True,
    )

    run_scenario(
        "E: critical delete_file → BLOCKED",
        TaskRequest(
            task_id="task-E-001",
            source="server",
            action_type="delete_file",
            target="/var/www/haehan/app.py",
            description="파일 삭제 요청",
        ),
        mock_approve=True,
    )

    log_event(
        log, logging.INFO, "=== orchestrator scenarios complete ===", event_type="EXECUTION_COMPLETED", actor="main"
    )
    print("\n" + "=" * 60)
    print("  실행 완료. logs/ 및 storage/ 참조")
    print("=" * 60)


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="haehan-ai-orchestrator")
    parser.add_argument("--dashboard", action="store_true", help="운영 대시보드 실행 (Flask)")
    parser.add_argument("--monitor", action="store_true", help="운영 감시기 실행 (tail -f + 텔레그램 알림)")
    parser.add_argument("--host", default="127.0.0.1", help="대시보드 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5050, help="대시보드 포트 (기본: 5050)")
    parser.add_argument("--seed", action="store_true", help="시나리오 A~E 실행 후 대시보드 시작")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.monitor:
        from orchestrator_v1.monitoring.monitor import run_monitor

        run_monitor()
    elif args.dashboard:
        if args.seed:
            main()
        from orchestrator_v1.monitoring.dashboard import run_dashboard

        run_dashboard(host=args.host, port=args.port)
    else:
        main()
