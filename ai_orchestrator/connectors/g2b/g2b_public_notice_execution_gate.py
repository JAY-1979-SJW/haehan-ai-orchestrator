"""
G2B 공개 공고 Execution Gate

dry-run adapter 결과를 검증하여 live 실행 candidate 여부를 판정한다.

원칙:
- read/open_url/navigate만 READONLY_EXECUTION_CANDIDATE 판정
- click/type/fill/submit/download/login/cert/bid/contract/payment → BLOCKED
- execution_dispatched는 live runner 실행 전 항상 False
- server_browser_used 항상 False
- download_auto_allowed 항상 False
- DB write 없음
- cookie/session/token/password/otp 출력 없음
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter import (
    ADAPTER_G2B_BLOCKED,
    ADAPTER_G2B_DRYRUN_READY,
    ADAPTER_G2B_NEEDS_VERIFICATION,
    evaluate_g2b_public_notice_dryrun,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_workflow import (
    VERDICT_ALLOWED,
    VERDICT_BLOCKED,
    VERDICT_NEEDS_VERIFICATION,
)

# ── gate_verdict 값 ───────────────────────────────────────────────────────────

GATE_READONLY_EXECUTION_CANDIDATE = "READONLY_EXECUTION_CANDIDATE"
GATE_BLOCKED = "GATE_BLOCKED"
GATE_NEEDS_VERIFICATION = "GATE_NEEDS_VERIFICATION"
GATE_DRYRUN_INVALID = "GATE_DRYRUN_INVALID"

# ── 금지 operation (gate 레벨) ────────────────────────────────────────────────

_GATE_BLOCKED_OPERATIONS: frozenset[str] = frozenset(
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

# ── 허용 operation ────────────────────────────────────────────────────────────

_GATE_ALLOWED_OPERATIONS: frozenset[str] = frozenset(
    {
        "read",
        "navigate",
        "open_url",
    }
)


def build_g2b_readonly_execution_candidate(
    url: str,
    operation: str,
) -> dict[str, Any]:
    """
    dry-run adapter를 통해 실행 candidate dict를 빌드한다.
    gate를 통과해야만 live runner가 실행할 수 있다.

    반환:
    - input_url
    - canonical_url
    - operation
    - gate_verdict
    - execution_allowed
    - execution_dispatched (항상 False)
    - server_browser_used (항상 False)
    - download_auto_allowed (항상 False)
    - local_agent_required (항상 True)
    - dryrun_result
    - blocked_reason
    - requires_url_verification
    """
    op = (operation or "").lower().strip()

    base: dict[str, Any] = {
        "input_url": url,
        "canonical_url": url or "",
        "operation": op,
        "gate_verdict": GATE_BLOCKED,
        "execution_allowed": False,
        "execution_dispatched": False,
        "server_browser_used": False,
        "download_auto_allowed": False,
        "local_agent_required": True,
        "dryrun_result": {},
        "blocked_reason": "",
        "requires_url_verification": False,
    }

    # gate 레벨 operation 차단
    if op in _GATE_BLOCKED_OPERATIONS:
        base["blocked_reason"] = f"GATE_BLOCKED_OPERATION: {op}"
        return base

    # dry-run adapter 호출
    dryrun = evaluate_g2b_public_notice_dryrun(url, operation=op)
    base["dryrun_result"] = dryrun
    base["canonical_url"] = dryrun.get("canonical_url", url or "")

    return evaluate_g2b_public_notice_execution_gate(dryrun)


def evaluate_g2b_public_notice_execution_gate(
    dryrun_result: dict[str, Any],
) -> dict[str, Any]:
    """
    dry-run adapter 결과를 받아 gate 판정을 수행한다.

    반환 dict는 build_g2b_readonly_execution_candidate와 동일 schema.
    """
    op = (dryrun_result.get("operation") or "").lower().strip()
    url = dryrun_result.get("input_url", "")
    canonical = dryrun_result.get("canonical_url", url)

    base: dict[str, Any] = {
        "input_url": url,
        "canonical_url": canonical,
        "operation": op,
        "gate_verdict": GATE_BLOCKED,
        "execution_allowed": False,
        "execution_dispatched": False,
        "server_browser_used": False,
        "download_auto_allowed": False,
        "local_agent_required": True,
        "dryrun_result": dryrun_result,
        "blocked_reason": "",
        "requires_url_verification": False,
    }

    # operation 차단
    if op in _GATE_BLOCKED_OPERATIONS:
        base["blocked_reason"] = f"GATE_BLOCKED_OPERATION: {op}"
        return base

    adapter_decision = dryrun_result.get("adapter_decision", ADAPTER_G2B_BLOCKED)
    policy_verdict = dryrun_result.get("policy_verdict", VERDICT_BLOCKED)

    if adapter_decision == ADAPTER_G2B_NEEDS_VERIFICATION or policy_verdict == VERDICT_NEEDS_VERIFICATION:
        base["gate_verdict"] = GATE_NEEDS_VERIFICATION
        base["requires_url_verification"] = True
        base["blocked_reason"] = dryrun_result.get("blocked_reason", "NEEDS_URL_VERIFICATION")
        return base

    if adapter_decision != ADAPTER_G2B_DRYRUN_READY or policy_verdict != VERDICT_ALLOWED:
        base["blocked_reason"] = dryrun_result.get("blocked_reason", "POLICY_BLOCKED")
        return base

    # 허용 operation 확인
    if op not in _GATE_ALLOWED_OPERATIONS:
        base["blocked_reason"] = f"OPERATION_NOT_IN_ALLOWED_SET: {op}"
        return base

    # PASS
    base["gate_verdict"] = GATE_READONLY_EXECUTION_CANDIDATE
    base["execution_allowed"] = True
    return base


def validate_g2b_execution_gate_result(result: dict[str, Any]) -> list[str]:
    """
    gate 결과의 필수 필드 및 정책 준수를 검증한다.
    오류 목록을 반환한다 (빈 리스트 = 유효).
    """
    errors: list[str] = []

    required_fields = [
        "input_url",
        "canonical_url",
        "operation",
        "gate_verdict",
        "execution_allowed",
        "execution_dispatched",
        "server_browser_used",
        "download_auto_allowed",
        "local_agent_required",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("server_browser_used") is not False:
        errors.append("server_browser_used는 항상 False여야 한다")

    if result.get("download_auto_allowed") is not False:
        errors.append("download_auto_allowed는 항상 False여야 한다")

    if result.get("execution_dispatched") is not False:
        errors.append("gate 단계에서 execution_dispatched는 항상 False여야 한다")

    if result.get("local_agent_required") is not True:
        errors.append("local_agent_required는 항상 True여야 한다")

    valid_gate_verdicts = {
        GATE_READONLY_EXECUTION_CANDIDATE,
        GATE_BLOCKED,
        GATE_NEEDS_VERIFICATION,
        GATE_DRYRUN_INVALID,
    }
    if "gate_verdict" in result and result["gate_verdict"] not in valid_gate_verdicts:
        errors.append(f"유효하지 않은 gate_verdict: {result['gate_verdict']}")

    if result.get("execution_allowed") and result.get("gate_verdict") != GATE_READONLY_EXECUTION_CANDIDATE:
        errors.append("execution_allowed=True이면 gate_verdict가 READONLY_EXECUTION_CANDIDATE여야 한다")

    return errors


__all__ = [
    "GATE_BLOCKED",
    "GATE_DRYRUN_INVALID",
    "GATE_NEEDS_VERIFICATION",
    "GATE_READONLY_EXECUTION_CANDIDATE",
    "build_g2b_readonly_execution_candidate",
    "evaluate_g2b_public_notice_execution_gate",
    "validate_g2b_execution_gate_result",
]
