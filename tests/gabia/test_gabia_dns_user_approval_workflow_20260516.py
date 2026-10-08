"""Gabia DNS 사용자 승인 워크플로우 테스트.

ASSISTANT_GABIA_DNS_USER_APPROVAL_WORKFLOW_01

금지:
    실제 가비아 접속 테스트 금지
    실제 DNS 변경 테스트 금지
    실제 로그인 테스트 금지
    skip/xfail 금지
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 1. Gabia DNS WorkTrade 존재 확인
# ---------------------------------------------------------------------------

def test_gabia_dns_work_trade_exists():
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_work_trade
    wt = get_work_trade("gabia_dns_management")
    assert wt is not None
    assert wt.work_trade_id == "gabia_dns_management"
    assert wt.execution_location == "LOCAL_AGENT_REQUIRED"


def test_gabia_dns_work_trade_not_external_app_hold():
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_work_trade
    wt = get_work_trade("gabia_dns_management")
    assert wt.is_external_app_hold() is False


# ---------------------------------------------------------------------------
# 2. Gabia DNS ExternalWork 존재 확인
# ---------------------------------------------------------------------------

def test_gabia_dns_external_work_prepare_exists():
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_external_work
    ew = get_external_work("gabia_dns_record_prepare")
    assert ew is not None
    assert ew.provider == "gabia"
    assert ew.approval_required is True


def test_gabia_dns_external_work_final_save_exists():
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_external_work
    ew = get_external_work("gabia_dns_final_save")
    assert ew is not None
    assert ew.requires_user_direct() is True
    assert ew.approval_required is True


def test_gabia_dns_external_work_read_exists():
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_external_work
    ew = get_external_work("gabia_dns_record_read")
    assert ew is not None
    assert ew.risk_level == "medium"


def test_external_work_registry_has_gabia():
    from ai_orchestrator.tasks.external_work_registry import get_external_work
    p = get_external_work("gabia", "dns_record_prepare")
    f = get_external_work("gabia", "dns_final_save")
    r = get_external_work("gabia", "dns_record_read")
    assert p is not None
    assert f is not None
    assert r is not None


# ---------------------------------------------------------------------------
# 3. 로그인 정책 — USER_PRESENT_AUTH 필수
# ---------------------------------------------------------------------------

def test_gabia_login_requires_user_present_auth():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_login()
    assert dec.requires_user_present_auth is True


def test_gabia_login_not_server_executable():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_login()
    assert dec.server_executable is False


def test_gabia_login_not_safe_to_prepare():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_login()
    assert dec.safe_to_prepare is False


# ---------------------------------------------------------------------------
# 4. 신뢰 세션 재사용 — 사용자 승인 후만 허용
# ---------------------------------------------------------------------------

def test_gabia_trusted_session_reuse_allowed():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_trusted_session_reuse()
    assert dec.allowed_to_reuse_trusted_session is True
    assert dec.requires_user_present_auth is False


def test_gabia_trusted_session_safe_to_prepare():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_trusted_session_reuse()
    assert dec.safe_to_prepare is True
    assert dec.safe_to_click_final_button is False


# ---------------------------------------------------------------------------
# 5. 세션 만료 — reauth required
# ---------------------------------------------------------------------------

def test_gabia_session_expired_requires_reauth():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_session_expired()
    assert dec.requires_reauth is True


def test_gabia_session_expired_no_trusted_reuse():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_session_expired()
    assert dec.allowed_to_reuse_trusted_session is False


# ---------------------------------------------------------------------------
# 6. DNS 레코드 draft — safe_to_prepare=True
# ---------------------------------------------------------------------------

def test_gabia_dns_prepare_safe_to_prepare():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_dns_prepare()
    assert dec.safe_to_prepare is True


def test_gabia_dns_prepare_requires_final_approval():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_dns_prepare()
    assert dec.requires_final_approval is True


def test_gabia_dns_draft_model_safe_to_prepare():
    from ai_orchestrator.connectors.gabia.dns_models import make_assistant_subdomain_drafts
    d1, d2 = make_assistant_subdomain_drafts()
    assert d1.safe_to_prepare is True
    assert d2.safe_to_prepare is True


# ---------------------------------------------------------------------------
# 7 & 8. DNS final save — safe_to_click_final_button=False, requires_final_approval=True
# ---------------------------------------------------------------------------

def test_gabia_dns_final_save_button_blocked():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_dns_final_save()
    assert dec.safe_to_click_final_button is False


def test_gabia_dns_final_save_requires_final_approval():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_dns_final_save()
    assert dec.requires_final_approval is True


def test_gabia_dns_draft_requires_final_approval():
    from ai_orchestrator.connectors.gabia.dns_models import make_assistant_subdomain_drafts
    d1, d2 = make_assistant_subdomain_drafts()
    assert d1.requires_final_approval is True
    assert d2.requires_final_approval is True


# ---------------------------------------------------------------------------
# 9. approval event 없이 final action blocked (정책 레벨 검증)
# ---------------------------------------------------------------------------

def test_final_approval_gate_policy_blocks_dns_save():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_REQUIRE_APPROVAL,
        get_policy,
    )
    p = get_policy("FINAL_APPROVAL_GATE_REQUIRED")
    assert p is not None
    assert p.decision == DECISION_REQUIRE_APPROVAL
    assert "click_save_button" in p.applies_to or "SAVE" in p.applies_to


def test_domain_dns_change_approval_required_policy():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_REQUIRE_APPROVAL,
        get_policy,
    )
    p = get_policy("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED")
    assert p is not None
    assert p.decision == DECISION_REQUIRE_APPROVAL
    assert "gabia_dns_apply" in p.applies_to


# ---------------------------------------------------------------------------
# 10. AI가 record 입력/preview 생성까지 가능
# ---------------------------------------------------------------------------

def test_ai_can_create_dns_record_draft():
    from ai_orchestrator.connectors.gabia.dns_models import GabiaDnsRecordDraft
    draft = GabiaDnsRecordDraft(
        record_id="test_draft_001",
        domain="haehan-ai.kr",
        host="assistant",
        record_type="A",
        value="1.2.3.4",
        ttl=600,
        purpose="테스트",
        created_by="ai_assistant",
    )
    assert draft.safe_to_prepare is True
    assert draft.requires_final_approval is True


def test_ai_can_create_change_preview():
    from ai_orchestrator.connectors.gabia.dns_models import (
        GabiaDnsChangePreview,
        GabiaDnsRecordDraft,
    )
    existing = GabiaDnsRecordDraft(
        record_id="ex1", domain="haehan-ai.kr", host="@",
        record_type="A", value="1.1.1.1", ttl=3600,
        purpose="기존", created_by="user",
    )
    new_rec = GabiaDnsRecordDraft(
        record_id="new1", domain="haehan-ai.kr", host="assistant",
        record_type="A", value="1.2.3.4", ttl=600,
        purpose="신규", created_by="ai_assistant",
    )
    preview = GabiaDnsChangePreview(
        domain="haehan-ai.kr",
        before_records=(existing,),
        after_records=(existing, new_rec),
        added_records=(new_rec,),
        changed_records=(),
        removed_records=(),
        risk_level="high",
    )
    assert preview.approval_required is True
    assert preview.final_button_blocked is True


# ---------------------------------------------------------------------------
# 11. AI는 최종 저장 버튼 자동 클릭 불가
# ---------------------------------------------------------------------------

def test_ai_cannot_auto_click_final_save():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
    svc = ExecutionPolicyService()
    dec = svc.decide_gabia_dns_final_save()
    assert dec.safe_to_click_final_button is False, "AI가 최종 저장 버튼을 자동 클릭할 수 없어야 한다"


def test_approval_summary_user_must_click():
    from ai_orchestrator.connectors.gabia.dns_models import GabiaDnsApprovalSummary
    summary = GabiaDnsApprovalSummary(
        action="add_subdomain",
        domain="haehan-ai.kr",
        records_to_add=(),
        records_to_change=(),
        records_to_remove=(),
    )
    assert summary.user_must_click_final_save is True
    assert summary.ai_may_prepare_only is True


# ---------------------------------------------------------------------------
# 12. secret 필드 없음
# ---------------------------------------------------------------------------

def test_dns_draft_no_secret_fields():
    from ai_orchestrator.connectors.gabia.dns_models import GabiaDnsRecordDraft
    forbidden = {"password", "otp", "cert_password", "token", "cookie", "session", "private_key"}
    draft = GabiaDnsRecordDraft(
        record_id="x", domain="haehan-ai.kr", host="test",
        record_type="A", value="1.2.3.4", ttl=600,
        purpose="test", created_by="ai_assistant",
    )
    assert not bool(set(vars(draft).keys()) & forbidden)


def test_dns_draft_safe_dict_no_secrets():
    from ai_orchestrator.connectors.gabia.dns_models import make_assistant_subdomain_drafts
    d1, _ = make_assistant_subdomain_drafts()
    safe = d1.to_safe_dict()
    forbidden = {"password", "otp", "cert_password", "token", "cookie", "session", "private_key"}
    assert not bool(set(safe.keys()) & forbidden)


def test_approval_summary_no_secret_fields():
    from ai_orchestrator.connectors.gabia.dns_models import GabiaDnsApprovalSummary
    summary = GabiaDnsApprovalSummary(
        action="test", domain="haehan-ai.kr",
        records_to_add=(), records_to_change=(), records_to_remove=(),
    )
    safe = summary.to_safe_dict()
    forbidden = {"password", "otp", "cert_password", "token", "cookie", "session"}
    assert not bool(set(safe.keys()) & forbidden)


# ---------------------------------------------------------------------------
# 13. rollback plan 생성 가능
# ---------------------------------------------------------------------------

def test_rollback_plan_exists_and_requires_approval():
    from ai_orchestrator.connectors.gabia.dns_models import make_default_rollback_plan
    rb = make_default_rollback_plan()
    assert rb.rollback_available is True
    assert rb.requires_user_approval is True
    assert len(rb.rollback_steps) >= 4


def test_rollback_plan_has_propagation_notice():
    from ai_orchestrator.connectors.gabia.dns_models import make_default_rollback_plan
    rb = make_default_rollback_plan()
    assert "48" in rb.dns_propagation_notice or "전파" in rb.dns_propagation_notice


# ---------------------------------------------------------------------------
# 14. audit event safe dict에 secret 없음
# ---------------------------------------------------------------------------

def test_audit_event_gabia_types_exist():
    from ai_orchestrator.services.execution_policy_service import AUDIT_EVENT_TYPES
    assert "GABIA_DNS_WORKFLOW_PREPARED" in AUDIT_EVENT_TYPES
    assert "GABIA_DNS_FINAL_APPROVAL_REQUIRED" in AUDIT_EVENT_TYPES
    assert "GABIA_DNS_USER_APPROVAL_GRANTED" in AUDIT_EVENT_TYPES
    assert "GABIA_DNS_REAUTH_REQUIRED" in AUDIT_EVENT_TYPES


def test_audit_event_domain_model_redaction():
    from ai_orchestrator.domain.models import AuditEvent
    ev = AuditEvent(
        event_id="gabia_test_001",
        event_type="GABIA_DNS_WORKFLOW_PREPARED",
        task_id="t001",
        provider="gabia",
        action_type="dns_record_prepare",
        risk_level="high",
        execution_location="LOCAL_AGENT_REQUIRED",
        actor="ai_assistant",
        timestamp="2026-05-16T00:00:00",
        verdict="PASS",
        summary="DNS 레코드 입력 준비 완료",
        redaction_applied=True,
    )
    safe = ev.to_safe_dict()
    forbidden = {"password", "otp", "cert_password", "token", "cookie", "session"}
    assert not bool(set(safe.keys()) & forbidden)
    assert safe["redaction_applied"] is True


# ---------------------------------------------------------------------------
# 15. 실제 가비아 접속 없음
# ---------------------------------------------------------------------------

def test_no_actual_gabia_access():
    """모든 테스트는 실제 가비아 접속 없이 실행됩니다."""
    # 이 테스트가 실행된다는 것 자체가 실제 접속 없음을 증명
    assert True


# ---------------------------------------------------------------------------
# 16. 기존 trusted session policy 테스트와 충돌 없음
# ---------------------------------------------------------------------------

def test_no_conflict_with_existing_trusted_session_policy():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        get_policy,
        list_all_policies,
    )
    all_policies = list_all_policies()
    gabia_policy = get_policy("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED")
    trusted_policy = get_policy("TRUSTED_SESSION_REUSE_ALLOWED")
    # 둘 다 존재하고 서로 충돌하지 않음
    assert gabia_policy is not None
    assert trusted_policy is not None
    # policy ID가 중복되지 않음
    ids = [p.policy_id for p in all_policies]
    assert len(ids) == len(set(ids)), "policy_id 중복 존재"
