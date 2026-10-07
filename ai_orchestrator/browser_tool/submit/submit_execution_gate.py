"""
Browser Submit Execution Gate — 순수 판정 모듈

GATE는 submit 실행 없이 실행 가능 여부만 판정한다.
- controlled_submit_allowed: 핵심 6개 조건(policy/preview/approval/controlled/audit) 통과 여부
- production_submit_allowed: 핵심 6개 조건 + production_submit_enabled=True
- production_submit_enabled=False는 production submit만 차단. controlled 경로는 독립 판정.

No network, no DB, no file I/O, no side effects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# BlockReason constants
# ---------------------------------------------------------------------------

class BlockReason:
    POLICY_NOT_ALLOW              = "POLICY_NOT_ALLOW"
    PREVIEW_HASH_MISSING          = "PREVIEW_HASH_MISSING"
    VALIDATION_ID_MISSING         = "VALIDATION_ID_MISSING"
    APPROVAL_NOT_APPROVED         = "APPROVAL_NOT_APPROVED"
    CONTROLLED_SUBMIT_NOT_SUCCESS = "CONTROLLED_SUBMIT_NOT_SUCCESS"
    AUDIT_NOT_LOGGED              = "AUDIT_NOT_LOGGED"
    # PRODUCTION_DISABLED는 block_reasons에 포함되지 않음 — gate_verdict 경로와 분리
    PRODUCTION_DISABLED           = "PRODUCTION_DISABLED"


# ---------------------------------------------------------------------------
# Input / Output schemas
# ---------------------------------------------------------------------------

@dataclass
class ExecutionGateInput:
    # 핵심 6개 조건
    policy_verdict: str
    preview_hash: str
    validation_id: str
    risk_level: str
    approval_status: str
    controlled_submit_result: str
    audit_logged: bool
    # production 활성화 플래그 (production submit 전용 — 현재 기본값 False)
    production_submit_enabled: bool
    # 선택 메타데이터
    submitted_by: str = ""
    site_id: str = ""
    form_id: str = ""


@dataclass
class ExecutionGateResult:
    gate_verdict: str                   # "GATE_PASS" | "GATE_ALLOW_CONTROLLED" | "GATE_BLOCK"
    controlled_submit_allowed: bool
    production_submit_allowed: bool
    block_reasons: list = field(default_factory=list)
    gate_id: str = ""
    evaluated_at: str = ""
    production_submit_enabled: bool = False


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------

def evaluate_execution_gate(inp: ExecutionGateInput) -> ExecutionGateResult:
    """
    Execution Gate 판정.

    핵심 6개 조건 중 하나라도 실패 → GATE_BLOCK (controlled_submit_allowed=False).
    모두 통과 → controlled_submit_allowed=True.
    production_submit_enabled=True 추가 통과 → GATE_PASS (production_submit_allowed=True).
    production_submit_enabled=False → GATE_ALLOW_CONTROLLED (production_submit_allowed=False).

    PRODUCTION_DISABLED는 block_reasons에 포함하지 않는다.
    submit 실행 없음, DB write 없음, network 없음.
    """
    block_reasons: list[str] = []

    if inp.policy_verdict != "ALLOW":
        block_reasons.append(BlockReason.POLICY_NOT_ALLOW)

    if not inp.preview_hash:
        block_reasons.append(BlockReason.PREVIEW_HASH_MISSING)

    if not inp.validation_id:
        block_reasons.append(BlockReason.VALIDATION_ID_MISSING)

    if inp.approval_status != "approved":
        block_reasons.append(BlockReason.APPROVAL_NOT_APPROVED)

    if inp.controlled_submit_result != "success":
        block_reasons.append(BlockReason.CONTROLLED_SUBMIT_NOT_SUCCESS)

    if not inp.audit_logged:
        block_reasons.append(BlockReason.AUDIT_NOT_LOGGED)

    gate_id = f"gate_{uuid.uuid4().hex[:12]}"
    evaluated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if block_reasons:
        return ExecutionGateResult(
            gate_verdict="GATE_BLOCK",
            controlled_submit_allowed=False,
            production_submit_allowed=False,
            block_reasons=block_reasons,
            gate_id=gate_id,
            evaluated_at=evaluated_at,
            production_submit_enabled=inp.production_submit_enabled,
        )

    production_submit_allowed = inp.production_submit_enabled
    verdict = "GATE_PASS" if production_submit_allowed else "GATE_ALLOW_CONTROLLED"

    return ExecutionGateResult(
        gate_verdict=verdict,
        controlled_submit_allowed=True,
        production_submit_allowed=production_submit_allowed,
        block_reasons=[],
        gate_id=gate_id,
        evaluated_at=evaluated_at,
        production_submit_enabled=inp.production_submit_enabled,
    )
