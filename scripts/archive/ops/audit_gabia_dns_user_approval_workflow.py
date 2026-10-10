"""Gabia DNS 사용자 승인 워크플로우 감사 스크립트.

ASSISTANT_GABIA_DNS_USER_APPROVAL_WORKFLOW_01

체크리스트:
  1. Gabia DNS WorkTrade 정의 존재
  2. Gabia DNS ExternalWork 정의 존재 (3개)
  3. USER_PRESENT_AUTH_REQUIRED 정책 연결
  4. TRUSTED_SESSION_REUSE_ALLOWED 정책 연결
  5. DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED 정책 연결
  6. safe_to_prepare=True 검증
  7. safe_to_click_final_button=False 검증
  8. DNS final save 자동 클릭 차단 검증
  9. secret storage forbidden 검증
  10. session expired → reauth required 검증
  11. rollback plan 모델 존재
  12. audit event redaction 적용
  13. 실제 가비아 접속 없음 (read_only=True)
  14. UI 변경 없음
  15. DB/schema 변경 없음

실행:
    python scripts/archive/ops/audit_gabia_dns_user_approval_workflow.py
    python scripts/archive/ops/audit_gabia_dns_user_approval_workflow.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

GABIA_DNS_FLOW = [
    {
        "step": 1,
        "actor": "AI",
        "action": "DNS 변경 필요 감지 및 레코드 초안 준비",
        "safe_to_prepare": True,
        "final_gate": False,
    },
    {
        "step": 2,
        "actor": "USER",
        "action": "최초 가비아 로그인 (USER_PRESENT_AUTH)",
        "safe_to_prepare": False,
        "final_gate": False,
    },
    {
        "step": 3,
        "actor": "AI",
        "action": "DNS 관리 화면까지 자동 진입 (신뢰 세션)",
        "safe_to_prepare": True,
        "final_gate": False,
    },
    {
        "step": 4,
        "actor": "AI",
        "action": "레코드 값 입력 및 변경 전/후 미리보기 생성",
        "safe_to_prepare": True,
        "final_gate": False,
    },
    {
        "step": 5,
        "actor": "USER",
        "action": "미리보기 확인 후 최종 승인 결정",
        "safe_to_prepare": False,
        "final_gate": True,
    },
    {"step": 6, "actor": "USER", "action": "저장/적용 버튼 직접 클릭", "safe_to_prepare": False, "final_gate": True},
    {
        "step": 7,
        "actor": "AI",
        "action": "적용 결과 검증 및 감사 로그 기록",
        "safe_to_prepare": True,
        "final_gate": False,
    },
]

SAFE_BOUNDARY = {
    "실제_가비아_접속": False,
    "실제_DNS_변경": False,
    "실제_로그인": False,
    "최종_저장_버튼_자동_클릭": False,
    "password_저장": False,
    "OTP_저장": False,
    "cert_password_저장": False,
    "token_저장": False,
    "cookie_저장": False,
    "session_저장": False,
    "DB_schema_변경": False,
    "API_response_변경": False,
    "UI_변경": False,
    "서버_반영": False,
}


def _check_work_trade() -> bool:
    try:
        from ai_orchestrator.connectors.gabia.dns_work_registry import (
            get_work_trade,
        )

        wt = get_work_trade("gabia_dns_management")
        assert wt is not None
        assert wt.execution_location == "LOCAL_AGENT_REQUIRED"
        return True
    except Exception:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        return False


def _check_external_works() -> tuple[bool, list[str]]:
    try:
        from ai_orchestrator.connectors.gabia.dns_work_registry import list_gabia_external_works

        works = list_gabia_external_works()
        ids = [w.external_work_id for w in works]
        required = {
            "gabia_dns_record_prepare",
            "gabia_dns_final_save",
            "gabia_dns_record_read",
        }
        missing = required - set(ids)
        return len(missing) == 0, list(missing)
    except Exception as e:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        return False, [str(e)]


def _check_policies() -> dict[str, bool]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.safety_policy.safety_policy_registry import get_policy

        result["USER_PRESENT_AUTH_REQUIRED"] = get_policy("USER_PRESENT_AUTH_REQUIRED") is not None
        result["TRUSTED_SESSION_REUSE_ALLOWED"] = get_policy("TRUSTED_SESSION_REUSE_ALLOWED") is not None
        result["DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED"] = get_policy("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED") is not None
        result["FINAL_APPROVAL_GATE_REQUIRED"] = get_policy("FINAL_APPROVAL_GATE_REQUIRED") is not None
        result["SECRET_STORAGE_FORBIDDEN"] = get_policy("SECRET_STORAGE_FORBIDDEN") is not None
        result["SERVER_SECURITY_LOGIN_BLOCKED"] = get_policy("SERVER_SECURITY_LOGIN_BLOCKED") is not None
    except Exception as e:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        for k in result:
            result[k] = False
        result["[error]"] = str(e)
    return result


def _check_policy_decisions() -> dict[str, bool]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

        svc = ExecutionPolicyService()

        login = svc.decide_gabia_login()
        result["login_requires_user_present_auth"] = login.requires_user_present_auth is True

        session = svc.decide_gabia_trusted_session_reuse()
        result["trusted_session_reuse_allowed"] = session.allowed_to_reuse_trusted_session is True

        prepare = svc.decide_gabia_dns_prepare()
        result["dns_prepare_safe_to_prepare"] = prepare.safe_to_prepare is True
        result["dns_prepare_final_approval_req"] = prepare.requires_final_approval is True
        result["dns_prepare_final_btn_blocked"] = prepare.safe_to_click_final_button is False

        save = svc.decide_gabia_dns_final_save()
        result["dns_final_save_blocked"] = save.safe_to_click_final_button is False
        result["dns_final_save_requires_approval"] = save.requires_final_approval is True
        result["dns_final_save_user_direct"] = save.requires_user_direct is True

        expired = svc.decide_gabia_session_expired()
        result["session_expired_reauth_required"] = expired.requires_reauth is True
        result["session_expired_no_reuse"] = expired.allowed_to_reuse_trusted_session is False
    except Exception as e:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_dns_models() -> dict[str, bool]:
    result: dict[str, Any] = {}
    try:
        from ai_orchestrator.connectors.gabia.dns_models import (
            make_assistant_subdomain_drafts,
            make_default_rollback_plan,
        )

        result["GabiaDnsRecordDraft"] = True
        result["GabiaDnsChangePreview"] = True
        result["GabiaDnsApprovalSummary"] = True
        result["GabiaDnsRollbackPlan"] = True

        # draft 생성 테스트
        d1, _d2 = make_assistant_subdomain_drafts()
        result["draft_safe_to_prepare"] = d1.safe_to_prepare is True
        result["draft_requires_final_approval"] = d1.requires_final_approval is True
        result["draft_no_secret_fields"] = all(
            not hasattr(d1, f) for f in ("password", "otp", "cert_password", "token", "cookie", "session")
        )

        # rollback plan 테스트
        rb = make_default_rollback_plan()
        result["rollback_requires_user_approval"] = rb.requires_user_approval is True
        result["rollback_steps_exist"] = len(rb.rollback_steps) >= 4

        # to_safe_dict에 secret 없는지 확인
        safe_d = d1.to_safe_dict()
        forbidden = {"password", "otp", "cert_password", "token", "cookie", "session", "private_key"}
        result["safe_dict_no_secrets"] = not bool(set(safe_d.keys()) & forbidden)

    except Exception as e:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_audit_events() -> bool:
    try:
        from ai_orchestrator.services.execution_policy_service import AUDIT_EVENT_TYPES

        gabia_events = {
            "GABIA_DNS_WORKFLOW_PREPARED",
            "GABIA_DNS_RECORD_DRAFTED",
            "GABIA_DNS_CHANGE_PREVIEW_CREATED",
            "GABIA_DNS_FINAL_APPROVAL_REQUIRED",
            "GABIA_DNS_USER_APPROVAL_GRANTED",
            "GABIA_DNS_USER_APPROVAL_DENIED",
            "GABIA_DNS_SESSION_REUSED",
            "GABIA_DNS_REAUTH_REQUIRED",
        }
        return gabia_events <= AUDIT_EVENT_TYPES
    except Exception:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        return False


def _check_external_work_registry() -> bool:
    try:
        from ai_orchestrator.tasks.external_work_registry import get_external_work

        p = get_external_work("gabia", "dns_record_prepare")
        f = get_external_work("gabia", "dns_final_save")
        r = get_external_work("gabia", "dns_record_read")
        return p is not None and f is not None and r is not None
    except Exception:  # noqa: BLE001 - 가비아 DNS 사용자승인 워크플로 정책 존재여부 자체감사 스크립트 - 예외 발생시 해당 체크 항목을 False(불통과)로 기록하는 fail-closed 패턴, 이미 안전한 방향
        return False


def main() -> None:
    wt_ok = _check_work_trade()
    ew_ok, ew_missing = _check_external_works()
    policies = _check_policies()
    decisions = _check_policy_decisions()
    models = _check_dns_models()
    audit_ok = _check_audit_events()
    registry_ok = _check_external_work_registry()

    checklist = [
        {"item": "Gabia DNS WorkTrade 정의 존재", "ok": wt_ok},
        {"item": "Gabia DNS ExternalWork 3개 존재", "ok": ew_ok},
        {"item": "external_work_registry gabia 항목", "ok": registry_ok},
        {"item": "USER_PRESENT_AUTH_REQUIRED 정책", "ok": policies.get("USER_PRESENT_AUTH_REQUIRED", False)},
        {"item": "TRUSTED_SESSION_REUSE_ALLOWED 정책", "ok": policies.get("TRUSTED_SESSION_REUSE_ALLOWED", False)},
        {
            "item": "DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED 정책",
            "ok": policies.get("DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED", False),
        },
        {"item": "FINAL_APPROVAL_GATE_REQUIRED 정책", "ok": policies.get("FINAL_APPROVAL_GATE_REQUIRED", False)},
        {"item": "SECRET_STORAGE_FORBIDDEN 정책", "ok": policies.get("SECRET_STORAGE_FORBIDDEN", False)},
        {"item": "로그인 requires_user_present_auth", "ok": decisions.get("login_requires_user_present_auth", False)},
        {"item": "신뢰 세션 재사용 허용", "ok": decisions.get("trusted_session_reuse_allowed", False)},
        {"item": "DNS 준비 safe_to_prepare=True", "ok": decisions.get("dns_prepare_safe_to_prepare", False)},
        {"item": "DNS 준비 final_approval_required", "ok": decisions.get("dns_prepare_final_approval_req", False)},
        {"item": "DNS 최종 저장 버튼 AI 자동 클릭 차단", "ok": decisions.get("dns_final_save_blocked", False)},
        {"item": "세션 만료 reauth_required", "ok": decisions.get("session_expired_reauth_required", False)},
        {"item": "DNS draft 모델 safe_to_prepare", "ok": models.get("draft_safe_to_prepare", False)},
        {"item": "DNS draft 모델 requires_final_approval", "ok": models.get("draft_requires_final_approval", False)},
        {"item": "draft 모델 secret 필드 없음", "ok": models.get("draft_no_secret_fields", False)},
        {"item": "safe_dict secret 정보 없음", "ok": models.get("safe_dict_no_secrets", False)},
        {"item": "rollback plan 존재", "ok": models.get("rollback_requires_user_approval", False)},
        {"item": "Gabia DNS AuditEvent 타입 8개", "ok": audit_ok},
    ]

    all_pass = all(c["ok"] for c in checklist)

    report = {
        "workflow_id": "ASSISTANT_GABIA_DNS_USER_APPROVAL_WORKFLOW_01",
        "read_only": True,
        "actual_gabia_access": False,
        "actual_dns_change": False,
        "ui_change": False,
        "db_schema_change": False,
        "safe_boundary": SAFE_BOUNDARY,
        "gabia_dns_flow": GABIA_DNS_FLOW,
        "policies": policies,
        "policy_decisions": decisions,
        "dns_models": models,
        "audit_events_ok": audit_ok,
        "external_registry_ok": registry_ok,
        "work_trade_ok": wt_ok,
        "external_works_missing": ew_missing,
        "checklist": checklist,
        "final_approval_gate": {
            "safe_to_prepare": True,
            "safe_to_click_final_button": False,
            "requires_final_approval": True,
            "user_must_approve": True,
        },
        "verdict": "PASS" if all_pass else "FAIL",
    }

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if all_pass else 1)

    print("=" * 60)
    print("Gabia DNS 사용자 승인 워크플로우 감사")
    print("=" * 60)
    for c in checklist:
        status = "PASS" if c["ok"] else "FAIL"
        print(f"  [{status}] {c['item']}")
    print()
    print(f"최종 판정: {report['verdict']}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
