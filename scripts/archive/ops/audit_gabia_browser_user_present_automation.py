"""Gabia 브라우저 User-Present 자동화 감사 스크립트.

ASSISTANT_GABIA_BROWSER_USER_PRESENT_AUTOMATION_PLAN_01

실행:
    python scripts/archive/ops/audit_gabia_browser_user_present_automation.py
    python scripts/archive/ops/audit_gabia_browser_user_present_automation.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

SAFE_BOUNDARY = {
    "실제_가비아_접속": False,
    "실제_DNS_변경": False,
    "실제_로그인": False,
    "최종_저장_버튼_자동_클릭": False,
    "password_저장": False,
    "OTP_저장": False,
    "cert_password_저장": False,
    "cookie_session_token_추출": False,
    "DB_schema_변경": False,
    "UI_변경": False,
    "서버_반영": False,
}


def _check_task_contract() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.connectors.gabia.browser_task import (
            make_autowork_dns_task,
        )

        result["GabiaBrowserTask_exists"] = True
        task = make_autowork_dns_task()
        result["desired_fqdn_autowork"] = task.desired_fqdn == "autowork.haehan-ai.kr"
        result["provider_gabia"] = task.provider == "gabia"
        result["safe_to_prepare_true"] = task.safe_to_prepare is True
        result["safe_to_click_final_false"] = task.safe_to_click_final_button is False
        result["requires_final_approval_true"] = task.requires_final_approval is True
        result["final_button_blocked_true"] = task.final_button_blocked is True
        result["execution_location_local"] = task.execution_location == "LOCAL_AGENT_REQUIRED"
        safe_d = task.to_safe_dict()
        forbidden = {"password", "otp", "cert_password", "token", "cookie", "session"}
        result["safe_dict_no_secrets"] = not bool(set(safe_d.keys()) & forbidden)
    except Exception as e:  # noqa: BLE001 - 가비아 브라우저 자동화 정책 계약(task/state machine/정책) 자체검증 스크립트 - import/호출 실패 시 체크리스트 항목을 실패로 기록(통과로 위장하지 않음), 실제 런타임 게이트가 아닌 감사 리포트
        result["[error]"] = str(e)
    return result


def _check_state_machine() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.connectors.gabia.browser_task import (
            STATE_DNS_MANAGEMENT_PAGE_READY,
            STATE_DNS_RECORD_DRAFTED,
            STATE_FINAL_APPROVAL_REQUIRED,
            STATE_LOGIN_REQUIRED,
            STATE_TRUSTED_SESSION_REUSED,
            USER_REQUIRED_STATES,
            evaluate_transition,
            is_ai_executable,
            is_final_button_blocked,
        )

        result["state_login_required_exists"] = True
        result["state_dns_page_ready_exists"] = True
        result["state_dns_record_drafted_exists"] = True
        result["state_final_approval_exists"] = True
        result["state_reauth_exists"] = True

        result["dns_page_ai_executable"] = is_ai_executable(STATE_DNS_MANAGEMENT_PAGE_READY)
        result["dns_drafted_ai_executable"] = is_ai_executable(STATE_DNS_RECORD_DRAFTED)
        result["final_approval_not_ai_exec"] = not is_ai_executable(STATE_FINAL_APPROVAL_REQUIRED)
        result["final_approval_button_block"] = is_final_button_blocked(STATE_FINAL_APPROVAL_REQUIRED)
        result["login_user_required"] = STATE_LOGIN_REQUIRED in USER_REQUIRED_STATES
        result["trusted_session_ai_exec"] = is_ai_executable(STATE_TRUSTED_SESSION_REUSED)

        tr = evaluate_transition(STATE_DNS_RECORD_DRAFTED, STATE_CHANGE_PREVIEW_CREATED := "CHANGE_PREVIEW_CREATED")  # noqa: F841
        result["transition_draft_to_preview"] = tr.allowed
        tr2 = evaluate_transition(STATE_FINAL_APPROVAL_REQUIRED, STATE_DNS_RECORD_DRAFTED)
        result["transition_final_to_draft_blocked"] = not tr2.allowed
    except Exception as e:  # noqa: BLE001 - 가비아 브라우저 자동화 정책 계약(task/state machine/정책) 자체검증 스크립트 - import/호출 실패 시 체크리스트 항목을 실패로 기록(통과로 위장하지 않음), 실제 런타임 게이트가 아닌 감사 리포트
        result["[error]"] = str(e)
    return result


def _check_policies() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.safety_policy.safety_policy_registry import get_policy

        result["USER_PRESENT_AUTH_REQUIRED"] = get_policy("USER_PRESENT_AUTH_REQUIRED") is not None
        result["TRUSTED_SESSION_REUSE_ALLOWED"] = get_policy("TRUSTED_SESSION_REUSE_ALLOWED") is not None
        result["SERVER_SECURITY_LOGIN_BLOCKED"] = get_policy("SERVER_SECURITY_LOGIN_BLOCKED") is not None
        result["SECRET_STORAGE_FORBIDDEN"] = get_policy("SECRET_STORAGE_FORBIDDEN") is not None
        result["DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED"] = get_policy("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED") is not None
        result["FINAL_APPROVAL_GATE_REQUIRED"] = get_policy("FINAL_APPROVAL_GATE_REQUIRED") is not None
    except Exception as e:  # noqa: BLE001 - 가비아 브라우저 자동화 정책 계약(task/state machine/정책) 자체검증 스크립트 - import/호출 실패 시 체크리스트 항목을 실패로 기록(통과로 위장하지 않음), 실제 런타임 게이트가 아닌 감사 리포트
        result["[error]"] = str(e)
    return result


def _check_policy_service() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.connectors.gabia.browser_task import (
            STATE_DNS_RECORD_DRAFTED,
            STATE_FINAL_APPROVAL_REQUIRED,
            STATE_LOGIN_REQUIRED,
            STATE_REAUTH_REQUIRED,
            STATE_TRUSTED_SESSION_REUSED,
        )
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

        svc = ExecutionPolicyService()

        login_dec = svc.decide_for_gabia_browser_state(STATE_LOGIN_REQUIRED)
        result["login_requires_user_present"] = login_dec.requires_user_present_auth is True
        result["login_safe_to_prepare_false"] = login_dec.safe_to_prepare is False

        trusted_dec = svc.decide_for_gabia_browser_state(STATE_TRUSTED_SESSION_REUSED)
        result["trusted_reuse_safe_to_prepare"] = trusted_dec.safe_to_prepare is True
        result["trusted_reuse_btn_blocked"] = trusted_dec.safe_to_click_final_button is False

        draft_dec = svc.decide_for_gabia_browser_state(STATE_DNS_RECORD_DRAFTED)
        result["draft_safe_to_prepare"] = draft_dec.safe_to_prepare is True
        result["draft_final_approval_req"] = draft_dec.requires_final_approval is True

        final_dec = svc.decide_for_gabia_browser_state(STATE_FINAL_APPROVAL_REQUIRED)
        result["final_safe_to_prepare_false"] = final_dec.safe_to_prepare is False
        result["final_btn_blocked"] = final_dec.safe_to_click_final_button is False

        reauth_dec = svc.decide_for_gabia_browser_state(STATE_REAUTH_REQUIRED)
        result["reauth_requires_reauth"] = reauth_dec.requires_reauth is True

        result["gabia_dns_blocked"] = svc.is_gabia_browser_action_blocked("dns_final_save")
        result["gabia_dns_user_direct"] = svc.is_gabia_browser_action_user_direct("dns_save")
    except Exception as e:  # noqa: BLE001 - 가비아 브라우저 자동화 정책 계약(task/state machine/정책) 자체검증 스크립트 - import/호출 실패 시 체크리스트 항목을 실패로 기록(통과로 위장하지 않음), 실제 런타임 게이트가 아닌 감사 리포트
        result["[error]"] = str(e)
    return result


def _check_audit_events() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.services.execution_policy_service import AUDIT_EVENT_TYPES

        for ev in [
            "GABIA_BROWSER_OPEN_REQUESTED",
            "GABIA_LOGIN_USER_PRESENT_REQUIRED",
            "GABIA_TRUSTED_SESSION_REUSED",
            "GABIA_DNS_PAGE_NAVIGATION_READY",
            "GABIA_SECURITY_AUTOMATION_BLOCKED",
        ]:
            result[ev] = ev in AUDIT_EVENT_TYPES
    except Exception as e:  # noqa: BLE001 - 가비아 브라우저 자동화 정책 계약(task/state machine/정책) 자체검증 스크립트 - import/호출 실패 시 체크리스트 항목을 실패로 기록(통과로 위장하지 않음), 실제 런타임 게이트가 아닌 감사 리포트
        result["[error]"] = str(e)
    return result


def _check_domain_profile() -> bool:
    try:
        from ai_orchestrator.browser_tool.policy.domain_profile_registry import get_domain_profile

        profile = get_domain_profile("gabia.com")
        return (
            profile.get("category") == "domain_dns"
            and "dns_final_save" in profile.get("blocked_actions", [])
            and "dns_save" in profile.get("user_direct_actions", [])
        )
    except Exception:  # noqa: BLE001 - 가비아 브라우저 자동화 정책 계약(task/state machine/정책) 자체검증 스크립트 - import/호출 실패 시 체크리스트 항목을 실패로 기록(통과로 위장하지 않음), 실제 런타임 게이트가 아닌 감사 리포트
        return False


def main() -> None:
    contract = _check_task_contract()
    states = _check_state_machine()
    policies = _check_policies()
    svc = _check_policy_service()
    events = _check_audit_events()
    profile_ok = _check_domain_profile()

    checklist = [
        {"item": "GabiaBrowserTask contract 존재", "ok": contract.get("GabiaBrowserTask_exists", False)},
        {"item": "desired_fqdn autowork.haehan-ai.kr", "ok": contract.get("desired_fqdn_autowork", False)},
        {"item": "safe_to_prepare=True", "ok": contract.get("safe_to_prepare_true", False)},
        {"item": "safe_to_click_final_button=False", "ok": contract.get("safe_to_click_final_false", False)},
        {"item": "requires_final_approval=True", "ok": contract.get("requires_final_approval_true", False)},
        {"item": "safe_dict secret 없음", "ok": contract.get("safe_dict_no_secrets", False)},
        {"item": "STATE_LOGIN_REQUIRED 존재", "ok": states.get("state_login_required_exists", False)},
        {"item": "STATE_DNS_MANAGEMENT_PAGE_READY 존재", "ok": states.get("state_dns_page_ready_exists", False)},
        {"item": "STATE_DNS_RECORD_DRAFTED 존재", "ok": states.get("state_dns_record_drafted_exists", False)},
        {"item": "STATE_FINAL_APPROVAL_REQUIRED 존재", "ok": states.get("state_final_approval_exists", False)},
        {"item": "DNS page AI 실행 가능", "ok": states.get("dns_page_ai_executable", False)},
        {"item": "FINAL_APPROVAL AI 실행 불가", "ok": states.get("final_approval_not_ai_exec", False)},
        {"item": "FINAL_APPROVAL 버튼 차단", "ok": states.get("final_approval_button_block", False)},
        {"item": "USER_PRESENT_AUTH 정책", "ok": policies.get("USER_PRESENT_AUTH_REQUIRED", False)},
        {"item": "TRUSTED_SESSION_REUSE 정책", "ok": policies.get("TRUSTED_SESSION_REUSE_ALLOWED", False)},
        {"item": "SERVER_SECURITY_LOGIN_BLOCKED 정책", "ok": policies.get("SERVER_SECURITY_LOGIN_BLOCKED", False)},
        {"item": "로그인 상태 requires_user_present_auth", "ok": svc.get("login_requires_user_present", False)},
        {"item": "신뢰 세션 safe_to_prepare=True", "ok": svc.get("trusted_reuse_safe_to_prepare", False)},
        {"item": "FINAL 상태 safe_to_click_final=False", "ok": svc.get("final_btn_blocked", False)},
        {"item": "dns_final_save 차단 확인", "ok": svc.get("gabia_dns_blocked", False)},
        {"item": "gabia.com domain profile 등록", "ok": profile_ok},
        {
            "item": "브라우저 AuditEvent 5개",
            "ok": all(events.values()) if events and "[error]" not in events else False,
        },
    ]

    all_pass = all(c["ok"] for c in checklist)

    report = {
        "automation_plan_id": "ASSISTANT_GABIA_BROWSER_USER_PRESENT_AUTOMATION_PLAN_01",
        "read_only": True,
        "safe_boundary": SAFE_BOUNDARY,
        "task_contract": contract,
        "state_machine": states,
        "policies": policies,
        "policy_service": svc,
        "audit_events": events,
        "domain_profile_ok": profile_ok,
        "final_approval_gate": {
            "safe_to_prepare": True,
            "safe_to_click_final_button": False,
            "requires_final_approval": True,
            "user_must_approve": True,
        },
        "checklist": checklist,
        "verdict": "PASS" if all_pass else "FAIL",
    }

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if all_pass else 1)

    print("=" * 60)
    print("Gabia 브라우저 User-Present 자동화 감사")
    print("=" * 60)
    for c in checklist:
        status = "PASS" if c["ok"] else "FAIL"
        print(f"  [{status}] {c['item']}")
    print()
    print(f"최종 판정: {report['verdict']}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
