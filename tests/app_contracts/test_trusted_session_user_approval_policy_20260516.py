"""신뢰 세션 및 사용자 최종 승인 게이트 정책 테스트.

ASSISTANT_TRUSTED_SESSION_AND_USER_APPROVAL_POLICY_REDESIGN_01
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 모듈 임포트 헬퍼
# ---------------------------------------------------------------------------


def _registry():
    from ai_orchestrator.safety_policy import safety_policy_registry as r

    return r


def _service():
    from ai_orchestrator.services.execution_policy_service import (
        AUDIT_EVENT_TYPES,
        ExecutionPolicyService,
        get_execution_policy_service,
    )

    return ExecutionPolicyService(), get_execution_policy_service, AUDIT_EVENT_TYPES


# ---------------------------------------------------------------------------
# STEP 3: 신규 상수 존재 확인
# ---------------------------------------------------------------------------


def test_auth_mode_constants_exist():
    r = _registry()
    assert r.AUTH_MODE_USER_PRESENT == "USER_PRESENT_AUTH"
    assert r.AUTH_MODE_TRUSTED_REUSE == "TRUSTED_SESSION_REUSE"
    assert r.AUTH_MODE_OAUTH_API == "OAUTH_API"


def test_session_trust_level_constants_exist():
    r = _registry()
    assert r.SESSION_TRUST_NONE == "NONE"
    assert r.SESSION_TRUST_PRESENT == "USER_PRESENT"
    assert r.SESSION_TRUST_REUSABLE == "REUSABLE"


def test_final_action_types_complete():
    r = _registry()
    required = {
        r.FINAL_ACTION_SAVE,
        r.FINAL_ACTION_SUBMIT,
        r.FINAL_ACTION_PAY,
        r.FINAL_ACTION_SIGN,
        r.FINAL_ACTION_DOMAIN_CHANGE,
        r.FINAL_ACTION_SEND,
        r.FINAL_ACTION_BID,
        r.FINAL_ACTION_TRANSFER,
    }
    assert required <= r.FINAL_ACTION_TYPES


def test_approval_gate_constants_exist():
    r = _registry()
    assert r.GATE_PREPARE_ALLOWED == "PREPARE_ALLOWED"
    assert r.GATE_FINAL_BLOCKED == "FINAL_BLOCKED"
    assert r.GATE_USER_APPROVAL_NEEDED == "USER_APPROVAL_NEEDED"
    assert r.GATE_REAUTH_REQUIRED == "REAUTH_REQUIRED"


# ---------------------------------------------------------------------------
# STEP 4: 10개 신규 정책 등록 확인
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "policy_id",
    [
        "USER_PRESENT_AUTH_REQUIRED",
        "TRUSTED_SESSION_REUSE_ALLOWED",
        "SECRET_STORAGE_FORBIDDEN",
        "SERVER_SECURITY_LOGIN_BLOCKED",
        "LOCAL_AGENT_SECURE_LOGIN_REQUIRED",
        "FINAL_APPROVAL_GATE_REQUIRED",
        "CERTIFICATE_PASSWORD_NEVER_STORED",
        "OAUTH_REFRESH_TOKEN_SECURE_STORE_ONLY",
        "DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED",
        "TRUSTED_SESSION_EXPIRE_REAUTH_REQUIRED",
    ],
)
def test_new_policy_registered(policy_id):
    from ai_orchestrator.safety_policy.safety_policy_registry import get_policy

    policy = get_policy(policy_id)
    assert policy is not None, f"정책 미등록: {policy_id}"


def test_total_policy_count_at_least_18():
    from ai_orchestrator.safety_policy.safety_policy_registry import list_all_policies

    assert len(list_all_policies()) >= 18


def test_final_approval_gate_decision_is_require_approval():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_REQUIRE_APPROVAL,
        get_policy,
    )

    p = get_policy("FINAL_APPROVAL_GATE_REQUIRED")
    assert p.decision == DECISION_REQUIRE_APPROVAL


def test_secret_storage_forbidden_decision_is_block():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_BLOCK,
        get_policy,
    )

    p = get_policy("SECRET_STORAGE_FORBIDDEN")
    assert p.decision == DECISION_BLOCK
    assert p.safe_to_execute_on_server is False


def test_user_present_auth_decision_is_require_user():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_REQUIRE_USER,
        get_policy,
    )

    p = get_policy("USER_PRESENT_AUTH_REQUIRED")
    assert p.decision == DECISION_REQUIRE_USER


def test_trusted_session_reuse_decision_is_allow():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_ALLOW,
        get_policy,
    )

    p = get_policy("TRUSTED_SESSION_REUSE_ALLOWED")
    assert p.decision == DECISION_ALLOW


def test_domain_dns_change_severity_critical():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        SEV_CRITICAL,
        get_policy,
    )

    p = get_policy("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED")
    assert p.severity == SEV_CRITICAL


# ---------------------------------------------------------------------------
# STEP 5: PolicyDecision 신규 필드
# ---------------------------------------------------------------------------


def test_policy_decision_has_new_fields():
    from ai_orchestrator.services.execution_policy_service import PolicyDecision

    d = PolicyDecision(
        execution_location="LOCAL_AGENT_REQUIRED",
        server_executable=False,
        requires_local_agent=True,
        requires_user_direct=False,
        requires_oauth_setup=False,
        is_external_app_hold=False,
        is_blocked=False,
        requires_secret_redaction=False,
        reason="test",
    )
    assert hasattr(d, "safe_to_prepare")
    assert hasattr(d, "safe_to_click_final_button")
    assert hasattr(d, "requires_final_approval")
    assert hasattr(d, "allowed_to_reuse_trusted_session")
    assert hasattr(d, "requires_user_present_auth")
    assert hasattr(d, "requires_reauth")


def test_policy_decision_defaults():
    from ai_orchestrator.services.execution_policy_service import PolicyDecision

    d = PolicyDecision(
        execution_location="SERVER_INTERNAL_ONLY",
        server_executable=True,
        requires_local_agent=False,
        requires_user_direct=False,
        requires_oauth_setup=False,
        is_external_app_hold=False,
        is_blocked=False,
        requires_secret_redaction=False,
        reason="default test",
    )
    assert d.safe_to_prepare is True
    assert d.safe_to_click_final_button is False
    assert d.requires_final_approval is False


def test_policy_decision_to_dict_contains_new_fields():
    from ai_orchestrator.services.execution_policy_service import PolicyDecision

    d = PolicyDecision(
        execution_location="LOCAL_AGENT_REQUIRED",
        server_executable=False,
        requires_local_agent=True,
        requires_user_direct=False,
        requires_oauth_setup=False,
        is_external_app_hold=False,
        is_blocked=False,
        requires_secret_redaction=False,
        reason="dict test",
        safe_to_prepare=True,
        requires_final_approval=True,
    )
    d_dict = d.to_dict()
    assert "safe_to_prepare" in d_dict
    assert "safe_to_click_final_button" in d_dict
    assert "requires_final_approval" in d_dict
    assert d_dict["requires_final_approval"] is True


# ---------------------------------------------------------------------------
# STEP 6: 사이트별 액션 정책 판정
# ---------------------------------------------------------------------------


def test_gabia_dns_requires_final_approval():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_site_action("gabia", "gabia_dns_apply")
    assert dec.requires_final_approval is True
    assert dec.safe_to_click_final_button is False
    assert dec.safe_to_prepare is True


def test_g2b_requires_user_present_auth():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_site_action("g2b", "navigate_to_work_screen")
    assert dec.requires_user_present_auth is True


def test_naver_safe_to_prepare():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_site_action("naver", "fill_form")
    assert dec.safe_to_prepare is True
    assert dec.safe_to_click_final_button is False


def test_is_final_action_save():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    assert svc.is_final_action("SAVE") is True
    assert svc.is_final_action("click_save_button") is True
    assert svc.is_final_action("fill_form") is False


def test_is_domain_change_approval_required():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    assert svc.is_domain_change_approval_required("gabia_dns_apply") is True
    assert svc.is_domain_change_approval_required("fill_form") is False


def test_is_secret_storage_forbidden():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    assert svc.is_secret_storage_forbidden("store_password") is True
    assert svc.is_secret_storage_forbidden("dump_cookie") is True
    assert svc.is_secret_storage_forbidden("navigate_to_work_screen") is False


# ---------------------------------------------------------------------------
# STEP 7: AuditEvent 타입 확인
# ---------------------------------------------------------------------------


def test_audit_event_types_complete():
    from ai_orchestrator.services.execution_policy_service import AUDIT_EVENT_TYPES

    required = {
        "USER_PRESENT_AUTH_REQUIRED",
        "TRUSTED_SESSION_REUSED",
        "TRUSTED_SESSION_EXPIRED_REAUTH_NEEDED",
        "FINAL_APPROVAL_REQUIRED",
        "FINAL_APPROVAL_GRANTED",
        "FINAL_ACTION_BLOCKED_NO_APPROVAL",
        "SECRET_STORAGE_ATTEMPT_BLOCKED",
        "CERT_PASSWORD_STORE_BLOCKED",
        "SERVER_SECURITY_LOGIN_BLOCKED",
        "DOMAIN_DNS_CHANGE_APPROVAL_GATE",
    }
    assert required <= AUDIT_EVENT_TYPES


def test_audit_event_types_count():
    from ai_orchestrator.services.execution_policy_service import AUDIT_EVENT_TYPES

    assert len(AUDIT_EVENT_TYPES) >= 10
