"""External Site Approval Gate Registry.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

모든 고위험 작업의 승인 게이트를 정의한다.
auto_execute_allowed=False 고정. user_approval_required=True 고정.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_orchestrator.external_sites.provider_models import RISK_CRITICAL, RISK_HIGH


@dataclass(frozen=True)
class ApprovalGate:
    gate_id: str
    risk_level: str
    user_approval_required: bool
    auto_execute_allowed: bool
    evidence_required: bool
    rollback_required: bool
    audit_log_required: bool
    description: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "risk_level": self.risk_level,
            "user_approval_required": self.user_approval_required,
            "auto_execute_allowed": self.auto_execute_allowed,
            "evidence_required": self.evidence_required,
            "rollback_required": self.rollback_required,
            "audit_log_required": self.audit_log_required,
            "description": self.description,
        }


APPROVAL_GATES: tuple[ApprovalGate, ...] = (

    ApprovalGate(
        gate_id="DNS_RECORD_SAVE",
        risk_level=RISK_HIGH,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=True,
        audit_log_required=True,
        description="가비아 DNS 레코드 저장/수정 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="DOMAIN_TRANSFER",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=True,
        audit_log_required=True,
        description="도메인 이전 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="NAMESERVER_CHANGE",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=True,
        audit_log_required=True,
        description="네임서버 변경 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="PAYMENT",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="결제/과금 — 사용자 명시 승인 필수. 자동 실행 절대 금지.",
    ),
    ApprovalGate(
        gate_id="BID_SUBMIT",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="나라장터 투찰 제출 — 사용자 명시 승인 + 인증서 직접 서명 필수",
    ),
    ApprovalGate(
        gate_id="CERTIFICATE_SIGN",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="공인인증서 서명 — 사용자 직접 실행 필수. 비밀번호 저장 절대 금지.",
    ),
    ApprovalGate(
        gate_id="TAX_SUBMIT",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="세금 신고/납부 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="EMAIL_SEND",
        risk_level=RISK_HIGH,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="메일 발송 — 사용자 명시 승인 필수. 자동 발송 절대 금지.",
    ),
    ApprovalGate(
        gate_id="SMARTSTORE_PRODUCT_UPDATE",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=True,
        audit_log_required=True,
        description="스마트스토어 상품 변경 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="SMARTSTORE_ORDER_ACTION",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=True,
        audit_log_required=True,
        description="스마트스토어 주문 처리 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="ACCOUNT_CHANGE",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=True,
        audit_log_required=True,
        description="계정 정보 변경 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="FILE_UPLOAD_FINAL_SUBMIT",
        risk_level=RISK_HIGH,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="파일 업로드 최종 제출 — 사용자 명시 승인 필수",
    ),
    ApprovalGate(
        gate_id="DOCUMENT_FINAL_SUBMIT",
        risk_level=RISK_CRITICAL,
        user_approval_required=True,
        auto_execute_allowed=False,
        evidence_required=True,
        rollback_required=False,
        audit_log_required=True,
        description="문서 최종 제출 — 사용자 명시 승인 필수",
    ),
)

_GATE_INDEX: dict[str, ApprovalGate] = {g.gate_id: g for g in APPROVAL_GATES}


def get_gate(gate_id: str) -> ApprovalGate | None:
    return _GATE_INDEX.get(gate_id)


def list_critical_gates() -> list[ApprovalGate]:
    return [g for g in APPROVAL_GATES if g.risk_level == RISK_CRITICAL]


def assert_all_critical_gates_blocked() -> list[str]:
    violations = []
    for g in list_critical_gates():
        if g.auto_execute_allowed:
            violations.append(f"{g.gate_id}: CRITICAL gate auto_execute_allowed=True 위반")
    return violations


__all__ = [
    "ApprovalGate",
    "APPROVAL_GATES",
    "get_gate",
    "list_critical_gates",
    "assert_all_critical_gates_blocked",
]
