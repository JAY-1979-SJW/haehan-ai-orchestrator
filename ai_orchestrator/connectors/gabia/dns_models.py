"""Gabia DNS 변경 관련 도메인 모델.

ASSISTANT_GABIA_DNS_USER_APPROVAL_WORKFLOW_01

이 모듈은 DNS 변경 초안/미리보기/승인요약/롤백계획 모델을 정의한다.
실제 가비아 접속 없이 백엔드에서 업무 준비 구조만 정의한다.

금지 필드:
    password, otp, cert_password, token, cookie,
    session, credential, private_key, authorization

포함 가능:
    record_type, host, value, ttl, domain, purpose 등 DNS 업무 데이터만
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

APPROVAL_GATE_PREPARE_ALLOWED = "PREPARE_ALLOWED"
APPROVAL_GATE_FINAL_BLOCKED = "FINAL_BLOCKED"

DNS_RECORD_TYPES = frozenset({"A", "CNAME", "MX", "TXT", "NS", "AAAA", "CAA"})


# ---------------------------------------------------------------------------
# GabiaDnsRecordDraft — DNS 레코드 입력 초안
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GabiaDnsRecordDraft:
    """AI가 준비하는 DNS 레코드 입력 초안.

    safe_to_prepare=True: AI가 이 모델을 채울 수 있다.
    requires_final_approval=True: 실제 저장은 사용자 승인 후에만 가능.
    """

    record_id: str
    domain: str
    host: str
    record_type: str
    value: str
    ttl: int
    purpose: str
    created_by: str  # "ai_assistant" 또는 "user"
    safe_to_prepare: bool = True
    requires_final_approval: bool = True

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "domain": self.domain,
            "host": self.host,
            "record_type": self.record_type,
            "value": self.value,
            "ttl": self.ttl,
            "purpose": self.purpose,
            "created_by": self.created_by,
            "safe_to_prepare": self.safe_to_prepare,
            "requires_final_approval": self.requires_final_approval,
        }


# ---------------------------------------------------------------------------
# GabiaDnsChangePreview — 변경 전/후 비교표
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GabiaDnsChangePreview:
    """DNS 변경 전/후 비교 미리보기.

    approval_required=True: 이 미리보기를 기반으로 사용자 승인 요청.
    final_button_blocked=True: AI가 최종 적용 버튼 클릭 불가.
    """

    domain: str
    before_records: tuple[GabiaDnsRecordDraft, ...]
    after_records: tuple[GabiaDnsRecordDraft, ...]
    added_records: tuple[GabiaDnsRecordDraft, ...]
    changed_records: tuple[GabiaDnsRecordDraft, ...]
    removed_records: tuple[GabiaDnsRecordDraft, ...]
    risk_level: str
    approval_required: bool = True
    final_button_blocked: bool = True

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "before_count": len(self.before_records),
            "after_count": len(self.after_records),
            "added": [r.to_safe_dict() for r in self.added_records],
            "changed": [r.to_safe_dict() for r in self.changed_records],
            "removed": [r.to_safe_dict() for r in self.removed_records],
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "final_button_blocked": self.final_button_blocked,
        }


# ---------------------------------------------------------------------------
# GabiaDnsApprovalSummary — 사용자 승인 요청 요약
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GabiaDnsApprovalSummary:
    """사용자에게 전달하는 DNS 변경 승인 요청 요약.

    ai_may_prepare_only=True: AI는 준비만 했고 저장은 하지 않았음을 명시.
    user_must_click_final_save=True: 저장은 사용자가 직접 클릭해야 함을 명시.
    """

    action: str
    domain: str
    records_to_add: tuple[GabiaDnsRecordDraft, ...]
    records_to_change: tuple[GabiaDnsRecordDraft, ...]
    records_to_remove: tuple[GabiaDnsRecordDraft, ...]
    approval_gate: str = APPROVAL_GATE_FINAL_BLOCKED
    user_must_click_final_save: bool = True
    ai_may_prepare_only: bool = True

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "domain": self.domain,
            "records_to_add": [r.to_safe_dict() for r in self.records_to_add],
            "records_to_change": [r.to_safe_dict() for r in self.records_to_change],
            "records_to_remove": [r.to_safe_dict() for r in self.records_to_remove],
            "approval_gate": self.approval_gate,
            "user_must_click_final_save": self.user_must_click_final_save,
            "ai_may_prepare_only": self.ai_may_prepare_only,
        }


# ---------------------------------------------------------------------------
# GabiaDnsRollbackPlan — 롤백 계획
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GabiaDnsRollbackPlan:
    """DNS 변경 롤백 계획.

    requires_user_approval=True: 롤백도 사용자 승인 필요.
    """

    rollback_available: bool
    previous_records_ref: str  # 이전 레코드 참조 ID (실제 값 아님)
    rollback_steps: tuple[str, ...]
    requires_user_approval: bool = True
    dns_propagation_notice: str = (
        "DNS 변경은 전파에 최대 48시간이 소요됩니다. 롤백 후에도 즉시 반영되지 않을 수 있습니다."
    )

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "rollback_available": self.rollback_available,
            "previous_records_ref": self.previous_records_ref,
            "rollback_steps": list(self.rollback_steps),
            "requires_user_approval": self.requires_user_approval,
            "dns_propagation_notice": self.dns_propagation_notice,
        }


# ---------------------------------------------------------------------------
# 서브도메인 생성 기본 초안 (assistant.haehan-ai.kr, assistant-api.haehan-ai.kr)
# ---------------------------------------------------------------------------


def make_assistant_subdomain_drafts(
    server_ip: str = "PENDING_USER_CONFIRMATION",
) -> tuple[GabiaDnsRecordDraft, GabiaDnsRecordDraft]:
    """assistant, assistant-api 서브도메인 초안을 반환한다.

    server_ip는 AI가 단독 결정하지 않고 사용자 확인 후 채운다.
    """
    draft_assistant = GabiaDnsRecordDraft(
        record_id="draft_assistant_haehan_ai_kr",
        domain="haehan-ai.kr",
        host="assistant",
        record_type="A",
        value=server_ip,
        ttl=600,
        purpose="비서앱 admin-web 프론트엔드 서브도메인",
        created_by="ai_assistant",
        safe_to_prepare=True,
        requires_final_approval=True,
    )
    draft_api = GabiaDnsRecordDraft(
        record_id="draft_assistant_api_haehan_ai_kr",
        domain="haehan-ai.kr",
        host="assistant-api",
        record_type="A",
        value=server_ip,
        ttl=600,
        purpose="비서앱 FastAPI 백엔드 API 서브도메인",
        created_by="ai_assistant",
        safe_to_prepare=True,
        requires_final_approval=True,
    )
    return draft_assistant, draft_api


def make_default_rollback_plan() -> GabiaDnsRollbackPlan:
    """기본 롤백 계획을 반환한다."""
    return GabiaDnsRollbackPlan(
        rollback_available=True,
        previous_records_ref="gabia_dns_snapshot_before_change",
        rollback_steps=(
            "1. 가비아 관리자 페이지 접속 (사용자 직접)",
            "2. DNS 관리 메뉴 이동",
            "3. 변경된 레코드 선택 후 삭제 또는 이전 값으로 수정",
            "4. 저장/적용 (사용자 승인 후)",
            "5. DNS 전파 확인 (최대 48시간 대기)",
        ),
        requires_user_approval=True,
    )


__all__ = [
    "APPROVAL_GATE_FINAL_BLOCKED",
    "APPROVAL_GATE_PREPARE_ALLOWED",
    "DNS_RECORD_TYPES",
    "GabiaDnsApprovalSummary",
    "GabiaDnsChangePreview",
    "GabiaDnsRecordDraft",
    "GabiaDnsRollbackPlan",
    "make_assistant_subdomain_drafts",
    "make_default_rollback_plan",
]
