# 운영 진입점 아님 — CLI 전용 (컨테이너 실행: ai_orchestrator.asgi:app)
import io
import logging
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ai_orchestrator.audit.audit_logger import log_event, read_recent_logs  # noqa: E402, I001 — sys.stdout 재설정 뒤 import
from ai_orchestrator.tasks.executor import execute  # noqa: E402 — sys.stdout 재설정 뒤 import
from tools.gates.approval import (  # noqa: E402 — sys.stdout 재설정 뒤 import
    approve_token,
    issue_token,
    validate_token,
)
from ai_orchestrator.core.logging_setup import setup_logging  # noqa: E402 — sys.stdout 재설정 뒤 import
from ai_orchestrator.core.models import TaskRequest  # noqa: E402 — sys.stdout 재설정 뒤 import
from ai_orchestrator.llm.openai_client import (  # noqa: E402 — sys.stdout 재설정 뒤 import
    generate_approval_reason,
    generate_task_summary,
    is_mock_mode,
)
from ai_orchestrator.llm.planner import plan  # noqa: E402 — sys.stdout 재설정 뒤 import

setup_logging()
logger = logging.getLogger(__name__)


def _header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _sep():
    print("-" * 60)


def run_scenario_a():
    _header("시나리오 A: LOW 작업 — 자동 허용")
    req = TaskRequest(
        task_id="S-A-001",
        source="manual",
        action_type="read_file",
        target="/var/log/app.log",
        description="서버 로그 파일 읽기",
        requested_by="admin",
    )
    log_event("TASK_RECEIVED", req.task_id, action_type=req.action_type, target=req.target, actor=req.requested_by)

    risk, ep = plan(req)
    log_event(
        "RISK_ASSESSED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        requires_approval=ep.requires_approval,
        actor="system",
    )
    log_event(
        "PLAN_CREATED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        requires_approval=ep.requires_approval,
        actor="system",
    )

    ai_summary = generate_task_summary(req, risk)
    result = execute(ep)
    log_event(
        "DRY_RUN_RETURNED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        decision=result,
        actor="executor",
    )

    print(f"  task_id              : {req.task_id}")
    print(f"  risk_level           : {risk.risk_level.upper()}")
    print(f"  allowed              : {ep.allowed}")
    print(f"  requires_approval    : {ep.requires_approval}")
    print(f"  ai_summary           : {ai_summary}")
    print(f"  final_status         : {result}")
    _sep()


def run_scenario_b():
    _header("시나리오 B: MEDIUM 작업 — 승인 후 드라이런")
    req = TaskRequest(
        task_id="S-B-001",
        source="pc",
        action_type="edit_config",
        target="/var/www/haehan/config.yaml",
        description="서비스 설정 파일 수정",
        payload={"key": "timeout", "value": 30},
        requested_by="admin",
    )
    log_event("TASK_RECEIVED", req.task_id, action_type=req.action_type, target=req.target, actor=req.requested_by)

    risk, ep = plan(req)
    log_event(
        "RISK_ASSESSED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        requires_approval=ep.requires_approval,
    )

    token = issue_token(req, risk, ttl_minutes=30)
    log_event(
        "APPROVAL_ISSUED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        decision="issued",
        actor=req.requested_by,
        note=f"token_id={token.token_id}",
    )

    approval_reason = generate_approval_reason(req, ep)

    pre_result = execute(ep)
    approval_status = token.status
    approval_id_hint = token.token_id[:8]
    print(f"  task_id              : {req.task_id}")
    print(f"  risk_level           : {risk.risk_level.upper()}")
    print(f"  allowed              : {ep.allowed}")
    print(f"  requires_approval    : {ep.requires_approval}")
    print(f"  approval_status      : {approval_status} (id={approval_id_hint}...)")
    print(f"  ai_approval_reason   : {approval_reason}")
    print(f"  [승인 전] status     : {pre_result}")

    approved, _status = approve_token(token.token_id, req.task_id, approved_by="대표님", role="admin")
    log_event(
        "APPROVAL_GRANTED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        decision=_status,
        actor="대표님",
        role="admin",
        token_id=token.token_id,
    )

    valid = validate_token(token.token_id, req.task_id)
    final_status = "APPROVED_DRY_RUN" if valid else pre_result
    log_event(
        "DRY_RUN_RETURNED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        decision=final_status,
        actor="executor",
    )

    print(f"  approval_token_status: {approved.status}")
    print(f"  token_valid          : {valid}")
    print(f"  final_status         : {final_status}")
    _sep()


def run_scenario_c():
    _header("시나리오 C: HIGH 작업 — 승인 후 드라이런")
    req = TaskRequest(
        task_id="S-C-001",
        source="server",
        action_type="restart_service",
        target="haehan-api",
        description="API 서버 재시작",
        payload={"reason": "memory leak fix"},
        requested_by="deploy-bot",
    )
    log_event("TASK_RECEIVED", req.task_id, action_type=req.action_type, target=req.target, actor=req.requested_by)

    risk, ep = plan(req)
    log_event(
        "RISK_ASSESSED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        requires_approval=ep.requires_approval,
    )

    token = issue_token(req, risk, ttl_minutes=30)
    log_event(
        "APPROVAL_ISSUED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        decision="issued",
        actor=req.requested_by,
        note=f"token_id={token.token_id}",
    )

    approved, _status = approve_token(token.token_id, req.task_id, approved_by="대표님", role="admin")
    log_event(
        "APPROVAL_GRANTED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        decision=_status,
        actor="대표님",
        role="admin",
        token_id=token.token_id,
    )

    valid = validate_token(token.token_id, req.task_id)
    final_status = "APPROVED_DRY_RUN" if valid else "PENDING_APPROVAL"
    log_event(
        "DRY_RUN_RETURNED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        decision=final_status,
        actor="executor",
    )

    print(f"  task_id              : {req.task_id}")
    print(f"  risk_level           : {risk.risk_level.upper()}")
    print(f"  allowed              : {ep.allowed}")
    print(f"  requires_approval    : {ep.requires_approval}")
    print(f"  approval_token_status: {approved.status}")
    print(f"  token_valid          : {valid}")
    print(f"  final_status         : {final_status}")
    _sep()


def run_scenario_d():
    _header("시나리오 D: CRITICAL 작업 — 기본 차단")
    req = TaskRequest(
        task_id="S-D-001",
        source="manual",
        action_type="delete_file",
        target="/var/www/haehan/old_backup.tar.gz",
        description="오래된 백업 파일 삭제",
        requested_by="admin",
    )
    log_event("TASK_RECEIVED", req.task_id, action_type=req.action_type, target=req.target, actor=req.requested_by)

    risk, ep = plan(req)
    log_event(
        "RISK_ASSESSED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        requires_approval=ep.requires_approval,
    )

    result = execute(ep)
    log_event(
        "EXECUTION_BLOCKED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=False,
        decision="BLOCKED",
        actor="policy",
        note="; ".join(ep.blocked_reasons),
    )

    print(f"  task_id              : {req.task_id}")
    print(f"  risk_level           : {risk.risk_level.upper()}")
    print(f"  allowed              : {ep.allowed}")
    print(f"  requires_approval    : {ep.requires_approval}")
    print(f"  blocked_reasons      : {ep.blocked_reasons}")
    print(f"  final_status         : {result}")
    _sep()


def main():
    # is_mock_mode()는 2026-09-24 OpenAI 삭제 이후 항상 True — "실제 연결" 분기는 도달 불가하므로 제거.
    assert is_mock_mode(), "OpenAI 호출 경로는 삭제됨 — MOCK 모드만 존재해야 합니다"
    mode = "[MOCK 모드]"
    logger.info("CLI 실행 시작 | mode=%s", mode)
    print(f"\n{'=' * 60}")
    print(f"  승인형 AI 오케스트레이터 2단계 드라이런  {mode}")
    print(f"{'=' * 60}")

    run_scenario_a()
    run_scenario_b()
    run_scenario_c()
    run_scenario_d()

    print("\n[최근 감사 로그 (최대 5건)]")
    for entry in read_recent_logs(limit=5):
        print(
            f"  {entry['timestamp'][:19]} | {entry['event_type']:<22} | {entry['task_id']} | {entry.get('decision', '')}"
        )

    logger.info("CLI 실행 완료")


if __name__ == "__main__":
    main()
