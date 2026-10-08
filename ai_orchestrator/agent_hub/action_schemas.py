"""Action Schemas — 액션 메타 정의 (input/output/summary/evidence/risk)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED, GRADE_USER_DIRECT, GRADE_BLOCKED,
)


@dataclass(frozen=True)
class ActionSpec:
    """단일 액션의 정적 스펙."""
    name: str
    risk_grade: str
    requires_user_approval: bool
    requires_pre_execution_summary: bool
    requires_evidence: bool
    is_pair: bool  # prepare/execute 짝이 있는지
    pair_with: str | None
    summary_fields: tuple[str, ...]
    evidence_fields: tuple[str, ...]
    description: str
    implemented: bool


# 1차 구현 + 향후 확장 액션 정의
_ACTION_SPECS: dict[str, ActionSpec] = {
    # ── 1차 구현 (browser.download_file) ─────────────────────────────────
    "browser.download_file": ActionSpec(
        name="browser.download_file",
        risk_grade=GRADE_AUTO_ALLOWED,
        requires_user_approval=False,
        requires_pre_execution_summary=False,
        requires_evidence=True,
        is_pair=False,
        pair_with=None,
        summary_fields=("source_url_safe", "expected_filename"),
        evidence_fields=("saved_safe_path", "file_size", "signature", "downloaded_at"),
        description="공개/비로그인 첨부파일 다운로드",
        implemented=True,
    ),
    # ── 1차 구현 (browser.attach_file) ──────────────────────────────────
    "browser.attach_file": ActionSpec(
        name="browser.attach_file",
        risk_grade=GRADE_USER_DELEGATED,
        requires_user_approval=True,
        requires_pre_execution_summary=True,
        requires_evidence=True,
        is_pair=False,
        pair_with=None,
        summary_fields=(
            "site", "form_field_label", "file_name", "file_size", "file_signature",
            "expected_result",
        ),
        evidence_fields=(
            "attached_file_name", "attached_at", "form_state_after",
        ),
        description="폼에 파일 첨부 (제출은 별도 승인)",
        implemented=True,
    ),
    # ── 2차 구현 (browser.prepare_submit) ─────────────────────────────────
    "browser.prepare_submit": ActionSpec(
        name="browser.prepare_submit",
        risk_grade=GRADE_AUTO_ALLOWED,
        requires_user_approval=False,
        requires_pre_execution_summary=False,
        requires_evidence=True,
        is_pair=True,
        pair_with="browser.submit_with_user_approval",
        summary_fields=("site", "form_summary"),
        evidence_fields=("preview_state", "summary_payload"),
        description="제출 직전 form 상태 캡처 + 요약 빌드 (실제 제출 X)",
        implemented=True,
    ),
    "browser.submit_with_user_approval": ActionSpec(
        name="browser.submit_with_user_approval",
        risk_grade=GRADE_USER_DIRECT,
        requires_user_approval=True,
        requires_pre_execution_summary=True,
        requires_evidence=True,
        is_pair=True,
        pair_with="browser.prepare_submit",
        summary_fields=(
            "site", "notice_no", "file_name", "amount", "company", "account",
            "expected_result",
        ),
        evidence_fields=(
            "submission_status", "receipt_no", "submitted_at",
            "result_screen_safe", "screenshot_path_safe",
        ),
        description="사용자 승인 후 제출 1회 실행",
        implemented=True,
    ),
    # ── 향후 (bid.prepare_bid) ──────────────────────────────────────────
    "bid.prepare_bid": ActionSpec(
        name="bid.prepare_bid",
        risk_grade=GRADE_AUTO_ALLOWED,
        requires_user_approval=False,
        requires_pre_execution_summary=False,
        requires_evidence=True,
        is_pair=True,
        pair_with="bid.submit_with_user_approval",
        summary_fields=("site", "notice_no", "bid_amount_summary"),
        evidence_fields=("bid_payload_preview", "summary_payload"),
        description="투찰 제출 직전 데이터 검증 + 요약 빌드",
        implemented=False,
    ),
    "bid.submit_with_user_approval": ActionSpec(
        name="bid.submit_with_user_approval",
        risk_grade=GRADE_USER_DIRECT,
        requires_user_approval=True,
        requires_pre_execution_summary=True,
        requires_evidence=True,
        is_pair=True,
        pair_with="bid.prepare_bid",
        summary_fields=(
            "site", "notice_no", "bid_amount", "company", "account",
            "deadline", "expected_result",
        ),
        evidence_fields=(
            "bid_status", "receipt_no", "submitted_at",
            "result_screen_safe", "screenshot_path_safe",
        ),
        description="사용자 승인 후 투찰 1회 실행",
        implemented=False,
    ),
    # ── 향후 (esign.prepare_signature) ──────────────────────────────────
    "esign.prepare_signature": ActionSpec(
        name="esign.prepare_signature",
        risk_grade=GRADE_AUTO_ALLOWED,
        requires_user_approval=False,
        requires_pre_execution_summary=False,
        requires_evidence=True,
        is_pair=True,
        pair_with="esign.execute_with_user_approval",
        summary_fields=("site", "document_summary"),
        evidence_fields=("document_hash_safe", "signer_info_safe", "summary_payload"),
        description="전자서명 직전 문서/대상 요약 (실제 서명 X)",
        implemented=False,
    ),
    "esign.execute_with_user_approval": ActionSpec(
        name="esign.execute_with_user_approval",
        risk_grade=GRADE_USER_DIRECT,
        requires_user_approval=True,
        requires_pre_execution_summary=True,
        requires_evidence=True,
        is_pair=True,
        pair_with="esign.prepare_signature",
        summary_fields=(
            "site", "document_name", "document_hash_safe", "signer_info_safe",
            "purpose", "expected_result",
        ),
        evidence_fields=(
            "signature_status", "signed_at", "result_screen_safe",
            "screenshot_path_safe", "signer_info_safe", "document_hash_safe",
        ),
        description="사용자 승인 후 전자서명 1회 실행 (인증서 비밀번호는 사용자 직접 입력)",
        implemented=False,
    ),
    # ── 범용 업무 실행 (business.*) ────────────────────────────────────────
    "business.prepare_action": ActionSpec(
        name="business.prepare_action",
        risk_grade=GRADE_AUTO_ALLOWED,
        requires_user_approval=False,
        requires_pre_execution_summary=False,
        requires_evidence=True,
        is_pair=True,
        pair_with="business.execute_with_user_approval",
        summary_fields=(
            "business_profile", "page_url_safe", "target_id",
            "organization_name", "amount", "due_date",
            "erp_module", "record_type", "record_title",
            "document_title", "approver_name", "signer_name",
            "attached_files_safe", "form_summary",
        ),
        evidence_fields=(
            "business_profile", "verdict", "prepared_at",
        ),
        description="범용 업무 실행 사전 검증 — 업무 프로필 기반 필드 검증 및 요약 생성",
        implemented=True,
    ),
    "business.execute_with_user_approval": ActionSpec(
        name="business.execute_with_user_approval",
        risk_grade=GRADE_USER_DIRECT,
        requires_user_approval=True,
        requires_pre_execution_summary=True,
        requires_evidence=True,
        is_pair=True,
        pair_with="business.prepare_action",
        summary_fields=(
            "business_profile", "page_url_safe", "submit_selector",
            "target_id", "organization_name", "amount", "due_date",
            "erp_module", "document_title", "signer_name",
        ),
        evidence_fields=(
            "business_profile", "verdict", "approval_request_id",
            "execution_location", "executed_at",
        ),
        description="범용 업무 실행 — 사용자 승인 후 local agent handoff 생성",
        implemented=True,
    ),
}


def all_specs() -> dict[str, ActionSpec]:
    """전체 등록된 액션 스펙."""
    return dict(_ACTION_SPECS)
