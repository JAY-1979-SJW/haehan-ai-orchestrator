"""
G2B 공개 공고 Dry-Run Workflow Integration Adapter

g2b_public_notice_workflow.py 결과를 기존 dry-run dispatch 계층에 연결한다.
실제 브라우저 실행, live G2B 접속, browser_worker/task_executor 호출 없음.

이번 단계 범위:
- G2B URL 분류 + 정책 판정 + dry-run plan 반환까지
- 실제 브라우저 실행 없음
- 실제 G2B 접속 없음
- browser_worker/task_executor live 연결 없음
- click/type/fill/submit/download 실행 없음
- safe_to_execute 항상 False
- dry_run 항상 True
- execution_dispatched 항상 False
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.connectors.g2b.g2b_public_notice_workflow import (
    ALLOWED_OPERATIONS,
    FORBIDDEN_OPERATIONS,
    VERDICT_BLOCKED,
    VERDICT_NEEDS_VERIFICATION,
    build_g2b_public_notice_workflow,
    validate_g2b_public_notice_workflow_result,
)

# ── adapter_decision 값 ────────────────────────────────────────────────────────

ADAPTER_G2B_DRYRUN_READY = "G2B_DRYRUN_READONLY_READY"
ADAPTER_G2B_BLOCKED = "G2B_DRYRUN_BLOCKED"
ADAPTER_G2B_NEEDS_VERIFICATION = "G2B_DRYRUN_NEEDS_VERIFICATION"

# ── 금지 operation ────────────────────────────────────────────────────────────

_ADAPTER_BLOCKED_OPERATIONS: frozenset[str] = frozenset(
    {
        "click",
        "type",
        "fill",
        "submit",
        "click_submit",
        "download",
        "upload",
        "post",
        "write",
        "delete",
        "update",
        "login",
        "cert",
        "payment",
        "contract",
        "bid_submit",
        "auto_login",
        "contract_submit",
    }
)


def evaluate_g2b_public_notice_dryrun(
    url: str,
    operation: str = "read",
    workflow_run_id: str = "",
    tenant_id: str = "",
    user_id: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    """
    G2B 공개 공고 URL에 대한 dry-run 워크플로우를 평가한다.

    정책 판정 순서:
    1. operation block check (adapter 레벨)
    2. build_g2b_public_notice_workflow() 호출 (URL normalize → domain classify → path check)
    3. validate workflow result
    4. dry-run result 구성 및 반환

    반환:
    - action_type
    - dry_run (항상 True)
    - input_url
    - canonical_url
    - operation
    - policy_verdict
    - adapter_decision
    - workflow_result
    - workflow_steps
    - blocked_reason
    - allowed_operations
    - forbidden_operations
    - execution_planned
    - execution_dispatched (항상 False)
    - live_browser_worker_called (항상 False)
    - download_auto_allowed (항상 False)
    - safe_to_execute (항상 False)
    - validation_errors
    - message_ko
    """
    op = (operation or "").lower().strip()

    base: dict[str, Any] = {
        "action_type": "G2B_PUBLIC_NOTICE_DRYRUN",
        "dry_run": True,
        "input_url": url,
        "canonical_url": url or "",
        "operation": op,
        "policy_verdict": VERDICT_BLOCKED,
        "adapter_decision": ADAPTER_G2B_BLOCKED,
        "workflow_result": {},
        "workflow_steps": [],
        "blocked_reason": "",
        "allowed_operations": ALLOWED_OPERATIONS,
        "forbidden_operations": FORBIDDEN_OPERATIONS,
        "execution_planned": False,
        "execution_dispatched": False,
        "live_browser_worker_called": False,
        "download_auto_allowed": False,
        "safe_to_execute": False,
        "validation_errors": [],
        "message_ko": "",
        "workflow_run_id": workflow_run_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "agent_id": agent_id,
    }

    # adapter 레벨 operation 차단 (workflow보다 먼저)
    if op in _ADAPTER_BLOCKED_OPERATIONS:
        base["blocked_reason"] = f"ADAPTER_BLOCKED_OPERATION: {op}"
        base["message_ko"] = f"operation '{op}'은 G2B dry-run adapter에서 허용되지 않습니다."
        return base

    # g2b_public_notice_workflow 호출
    wf_result = build_g2b_public_notice_workflow(url, operation=op)
    base["workflow_result"] = wf_result
    base["canonical_url"] = wf_result.get("canonical_url", url or "")
    base["workflow_steps"] = wf_result.get("workflow_steps", [])

    # validate
    validation_errors = validate_g2b_public_notice_workflow_result(wf_result)
    base["validation_errors"] = validation_errors

    verdict = wf_result.get("verdict", VERDICT_BLOCKED)
    base["policy_verdict"] = verdict

    # verdict에 따라 adapter_decision 결정
    if verdict == VERDICT_NEEDS_VERIFICATION:
        base["adapter_decision"] = ADAPTER_G2B_NEEDS_VERIFICATION
        base["blocked_reason"] = wf_result.get("blocked_reason", "NEEDS_URL_VERIFICATION")
        base["message_ko"] = wf_result.get("message_ko", "URL 검증이 필요합니다.")
        return base

    if verdict == VERDICT_BLOCKED:
        base["adapter_decision"] = ADAPTER_G2B_BLOCKED
        base["blocked_reason"] = wf_result.get("blocked_reason", "POLICY_BLOCK")
        base["message_ko"] = wf_result.get("message_ko", "정책에 의해 차단되었습니다.")
        return base

    # VERDICT_ALLOWED — dry-run plan만 반환, 실제 실행 없음
    base["adapter_decision"] = ADAPTER_G2B_DRYRUN_READY
    base["execution_planned"] = True
    # execution_dispatched는 항상 False (dry-run)
    base["execution_dispatched"] = False
    base["live_browser_worker_called"] = False
    base["message_ko"] = (
        f"G2B 공개 공고 dry-run 계획 준비 완료. "
        f"operation={op}, domain={wf_result.get('normalized_domain', '')}. "
        f"실제 실행은 별도 승인 후 수행됩니다."
    )
    return base


def validate_g2b_dryrun_adapter_result(result: dict[str, Any]) -> list[str]:
    """
    dry-run adapter 결과의 필수 필드 및 정책 준수를 검증한다.
    """
    errors: list[str] = []

    required_fields = [
        "action_type",
        "dry_run",
        "input_url",
        "canonical_url",
        "operation",
        "policy_verdict",
        "adapter_decision",
        "workflow_steps",
        "blocked_reason",
        "allowed_operations",
        "forbidden_operations",
        "execution_planned",
        "execution_dispatched",
        "live_browser_worker_called",
        "download_auto_allowed",
        "safe_to_execute",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    for key, expected, message in (
        ("dry_run", True, "dry_run은 항상 True여야 한다"),
        ("safe_to_execute", False, "safe_to_execute는 항상 False여야 한다"),
        ("execution_dispatched", False, "execution_dispatched는 항상 False여야 한다"),
        ("live_browser_worker_called", False, "live_browser_worker_called는 항상 False여야 한다"),
        ("download_auto_allowed", False, "download_auto_allowed는 항상 False여야 한다"),
    ):
        if result.get(key) is not expected:
            errors.append(message)

    valid_decisions = {
        ADAPTER_G2B_DRYRUN_READY,
        ADAPTER_G2B_BLOCKED,
        ADAPTER_G2B_NEEDS_VERIFICATION,
    }
    if "adapter_decision" in result and result["adapter_decision"] not in valid_decisions:
        errors.append(f"유효하지 않은 adapter_decision: {result['adapter_decision']}")

    # allowed_operations에 금지 동작 포함 여부
    forbidden_set = set(FORBIDDEN_OPERATIONS)
    for op in result.get("allowed_operations", []):
        if op.lower() in forbidden_set:
            errors.append(f"allowed_operations에 금지 동작 포함: {op}")

    return errors


__all__ = [
    "ADAPTER_G2B_BLOCKED",
    "ADAPTER_G2B_DRYRUN_READY",
    "ADAPTER_G2B_NEEDS_VERIFICATION",
    "evaluate_g2b_public_notice_dryrun",
    "validate_g2b_dryrun_adapter_result",
]
