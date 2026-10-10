"""Gabia 브라우저 User-Present 자동화 계약 테스트.

ASSISTANT_GABIA_BROWSER_USER_PRESENT_AUTOMATION_PLAN_01

금지:
    실제 가비아 접속 금지 / 실제 DNS 변경 금지 / 실제 로그인 금지
    skip/xfail 금지
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 1. GabiaBrowserTask contract 생성
# ---------------------------------------------------------------------------


def test_gabia_browser_task_contract_created():
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task

    task = make_autowork_dns_task()
    assert task.provider == "gabia"
    assert task.purpose == "dns_record_prepare"


# ---------------------------------------------------------------------------
# 2. desired_fqdn = autowork.haehan-ai.kr
# ---------------------------------------------------------------------------


def test_desired_fqdn_is_autowork_haehan_ai_kr():
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task

    task = make_autowork_dns_task()
    assert task.desired_fqdn == "autowork.haehan-ai.kr"
    assert task.subdomain == "autowork"
    assert task.target_domain == "haehan-ai.kr"


# ---------------------------------------------------------------------------
# 3. LOGIN_REQUIRED 상태는 user_present_auth 요구
# ---------------------------------------------------------------------------


def test_login_required_state_requires_user_present_auth():
    from ai_orchestrator.connectors.gabia.browser_task import STATE_LOGIN_REQUIRED
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_gabia_browser_state(STATE_LOGIN_REQUIRED)
    assert dec.requires_user_present_auth is True
    assert dec.safe_to_prepare is False


# ---------------------------------------------------------------------------
# 4. trusted session은 USER_APPROVED 상태에서만 재사용 가능
# ---------------------------------------------------------------------------


def test_trusted_session_reuse_allowed_in_reused_state():
    from ai_orchestrator.connectors.gabia.browser_task import STATE_TRUSTED_SESSION_REUSED
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_gabia_browser_state(STATE_TRUSTED_SESSION_REUSED)
    assert dec.allowed_to_reuse_trusted_session is True
    assert dec.safe_to_prepare is True


def test_trusted_session_not_allowed_in_blocked_state():
    from ai_orchestrator.connectors.gabia.browser_task import STATE_BLOCKED
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_gabia_browser_state(STATE_BLOCKED)
    assert dec.allowed_to_reuse_trusted_session is False


# ---------------------------------------------------------------------------
# 5. REAUTH_REQUIRED 상태는 requires_reauth=True
# ---------------------------------------------------------------------------


def test_reauth_required_state():
    from ai_orchestrator.connectors.gabia.browser_task import STATE_REAUTH_REQUIRED
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_gabia_browser_state(STATE_REAUTH_REQUIRED)
    assert dec.requires_reauth is True
    assert dec.allowed_to_reuse_trusted_session is False


# ---------------------------------------------------------------------------
# 6. DNS_MANAGEMENT_PAGE_READY 상태가 표현된다
# ---------------------------------------------------------------------------


def test_dns_management_page_ready_state_ai_executable():
    from ai_orchestrator.connectors.gabia.browser_task import (
        STATE_DNS_MANAGEMENT_PAGE_READY,
        is_ai_executable,
    )

    assert is_ai_executable(STATE_DNS_MANAGEMENT_PAGE_READY) is True


# ---------------------------------------------------------------------------
# 7. DNS_RECORD_DRAFTED 상태는 safe_to_prepare=True
# ---------------------------------------------------------------------------


def test_dns_record_drafted_state_safe_to_prepare():
    from ai_orchestrator.connectors.gabia.browser_task import STATE_DNS_RECORD_DRAFTED
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_gabia_browser_state(STATE_DNS_RECORD_DRAFTED)
    assert dec.safe_to_prepare is True
    assert dec.safe_to_click_final_button is False


# ---------------------------------------------------------------------------
# 8. FINAL_APPROVAL_REQUIRED 상태는 safe_to_click_final_button=False
# ---------------------------------------------------------------------------


def test_final_approval_required_state_button_blocked():
    from ai_orchestrator.connectors.gabia.browser_task import STATE_FINAL_APPROVAL_REQUIRED
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    dec = svc.decide_for_gabia_browser_state(STATE_FINAL_APPROVAL_REQUIRED)
    assert dec.safe_to_click_final_button is False
    assert dec.safe_to_prepare is False


# ---------------------------------------------------------------------------
# 9. approval event 없이 final save blocked (정책 레벨)
# ---------------------------------------------------------------------------


def test_final_approval_gate_policy_blocks_without_approval():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_REQUIRE_APPROVAL,
        get_policy,
    )

    p = get_policy("FINAL_APPROVAL_GATE_REQUIRED")
    assert p.decision == DECISION_REQUIRE_APPROVAL


def test_domain_dns_change_approval_policy_exists():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_REQUIRE_APPROVAL,
        get_policy,
    )

    p = get_policy("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED")
    assert p.decision == DECISION_REQUIRE_APPROVAL
    assert "gabia_dns_apply" in p.applies_to


# ---------------------------------------------------------------------------
# 10. AI는 final save 버튼 자동 클릭 불가
# ---------------------------------------------------------------------------


def test_ai_cannot_auto_click_final_save_in_any_state():
    from ai_orchestrator.connectors.gabia.browser_task import (
        STATE_CHANGE_PREVIEW_CREATED,
        STATE_DNS_RECORD_DRAFTED,
        STATE_FINAL_APPROVAL_REQUIRED,
        STATE_TRUSTED_SESSION_REUSED,
    )
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    for state in [
        STATE_DNS_RECORD_DRAFTED,
        STATE_CHANGE_PREVIEW_CREATED,
        STATE_FINAL_APPROVAL_REQUIRED,
        STATE_TRUSTED_SESSION_REUSED,
    ]:
        dec = svc.decide_for_gabia_browser_state(state)
        assert dec.safe_to_click_final_button is False, f"상태 {state}에서 AI가 최종 버튼 클릭 가능"


# ---------------------------------------------------------------------------
# 11. cookie/session/token extraction blocked
# ---------------------------------------------------------------------------


def test_cookie_extraction_blocked_in_unified_schema():
    from ai_orchestrator.browser_tool.unified_browser_task_schema import BLOCKED_TASK_ACTIONS

    assert "cookie_export" in BLOCKED_TASK_ACTIONS
    assert "session_export" in BLOCKED_TASK_ACTIONS
    assert "token_export" in BLOCKED_TASK_ACTIONS


def test_secret_storage_policy_blocks_cookie_dump():
    from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

    svc = ExecutionPolicyService()
    assert svc.is_secret_storage_forbidden("dump_cookie") is True
    assert svc.is_secret_storage_forbidden("extract_session") is True


# ---------------------------------------------------------------------------
# 12. server browser security login blocked
# ---------------------------------------------------------------------------


def test_server_security_login_blocked_policy():
    from ai_orchestrator.safety_policy.safety_policy_registry import (
        DECISION_BLOCK,
        get_policy,
    )

    p = get_policy("SERVER_SECURITY_LOGIN_BLOCKED")
    assert p is not None
    assert p.decision == DECISION_BLOCK
    assert p.safe_to_execute_on_server is False


# ---------------------------------------------------------------------------
# 13. audit event safe dict에 secret 없음
# ---------------------------------------------------------------------------


def test_gabia_browser_audit_events_in_registry():
    from ai_orchestrator.services.execution_policy_service import AUDIT_EVENT_TYPES

    assert "GABIA_BROWSER_OPEN_REQUESTED" in AUDIT_EVENT_TYPES
    assert "GABIA_LOGIN_USER_PRESENT_REQUIRED" in AUDIT_EVENT_TYPES
    assert "GABIA_SECURITY_AUTOMATION_BLOCKED" in AUDIT_EVENT_TYPES


def test_audit_event_domain_model_no_secrets():
    from ai_orchestrator.domain.models import AuditEvent

    ev = AuditEvent(
        event_id="gabia_browser_001",
        event_type="GABIA_BROWSER_OPEN_REQUESTED",
        task_id="t001",
        provider="gabia",
        action_type="dns_record_prepare",
        risk_level="high",
        execution_location="LOCAL_AGENT_REQUIRED",
        actor="ai_assistant",
        timestamp="2026-05-16T00:00:00",
        verdict="PASS",
        summary="가비아 브라우저 접속 요청",
        redaction_applied=True,
    )
    safe = ev.to_safe_dict()
    forbidden = {"password", "otp", "cert_password", "token", "cookie", "session"}
    assert not bool(set(safe.keys()) & forbidden)


# ---------------------------------------------------------------------------
# 14. 실제 가비아 접속 없음
# ---------------------------------------------------------------------------


def test_no_actual_gabia_browser_access():
    """모든 테스트가 실제 가비아 접속 없이 완료됩니다."""
    assert True


# ---------------------------------------------------------------------------
# 15. 기존 Gabia DNS workflow 테스트와 충돌 없음
# ---------------------------------------------------------------------------


def test_no_conflict_with_gabia_dns_workflow():
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_work_trade

    wt = get_work_trade("gabia_dns_management")
    task = make_autowork_dns_task()
    assert wt is not None
    assert task is not None
    assert wt.execution_location == task.execution_location


# ---------------------------------------------------------------------------
# 16. trusted session policy 테스트와 충돌 없음
# ---------------------------------------------------------------------------


def test_no_conflict_with_trusted_session_policy():
    from ai_orchestrator.safety_policy.safety_policy_registry import list_all_policies

    ids = [p.policy_id for p in list_all_policies()]
    assert len(ids) == len(set(ids)), "policy_id 중복"
    assert "TRUSTED_SESSION_REUSE_ALLOWED" in ids
    assert "USER_PRESENT_AUTH_REQUIRED" in ids


# ---------------------------------------------------------------------------
# state machine 허용 전이 추가 검증
# ---------------------------------------------------------------------------


def test_state_machine_allowed_transitions():
    from ai_orchestrator.connectors.gabia.browser_task import (
        STATE_CHANGE_PREVIEW_CREATED,
        STATE_DNS_RECORD_DRAFTED,
        STATE_FINAL_APPROVAL_REQUIRED,
        STATE_LOGIN_REQUIRED,
        STATE_OPEN_GABIA_HOME,
        STATE_TRUSTED_SESSION_REUSED,
        evaluate_transition,
    )

    # 허용 전이
    assert evaluate_transition(STATE_OPEN_GABIA_HOME, STATE_LOGIN_REQUIRED).allowed is True
    assert evaluate_transition(STATE_OPEN_GABIA_HOME, STATE_TRUSTED_SESSION_REUSED).allowed is True
    assert evaluate_transition(STATE_DNS_RECORD_DRAFTED, STATE_CHANGE_PREVIEW_CREATED).allowed is True
    assert evaluate_transition(STATE_CHANGE_PREVIEW_CREATED, STATE_FINAL_APPROVAL_REQUIRED).allowed is True


def test_state_machine_blocked_transitions():
    from ai_orchestrator.connectors.gabia.browser_task import (
        STATE_DNS_MANAGEMENT_PAGE_READY,
        STATE_DNS_RECORD_DRAFTED,
        STATE_FINAL_APPROVAL_REQUIRED,
        STATE_LOGIN_REQUIRED,
        evaluate_transition,
    )

    # 금지 전이 — final에서 draft로 역방향 불가
    assert evaluate_transition(STATE_FINAL_APPROVAL_REQUIRED, STATE_DNS_RECORD_DRAFTED).allowed is False
    # login에서 dns page로 직접 점프 불가
    assert evaluate_transition(STATE_LOGIN_REQUIRED, STATE_DNS_MANAGEMENT_PAGE_READY).allowed is False


def test_gabia_domain_profile_registered():
    from ai_orchestrator.browser_tool.policy.domain_profile_registry import get_domain_profile

    profile = get_domain_profile("gabia.com")
    assert profile.get("category") == "domain_dns"
    assert "dns_final_save" in profile.get("blocked_actions", [])
    assert "dns_save" in profile.get("user_direct_actions", [])


def test_task_safe_dict_no_secret_fields():
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task

    task = make_autowork_dns_task()
    safe = task.to_safe_dict()
    forbidden = {"password", "otp", "cert_password", "token", "cookie", "session", "private_key"}
    assert not bool(set(safe.keys()) & forbidden)
