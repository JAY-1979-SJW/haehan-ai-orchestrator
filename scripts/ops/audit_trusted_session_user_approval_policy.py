"""신뢰 세션 및 최종 승인 게이트 정책 감사 스크립트.

ASSISTANT_TRUSTED_SESSION_AND_USER_APPROVAL_POLICY_REDESIGN_01

철학:
    AI는 업무를 준비한다.
    AI는 신뢰 세션을 재사용한다.
    AI는 최종 버튼 앞에서 멈춘다.
    대표님이 승인한다.
    그 후 결과를 AI가 검증하고 기록한다.

실행:
    python scripts/ops/audit_trusted_session_user_approval_policy.py
    python scripts/ops/audit_trusted_session_user_approval_policy.py --json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 정책 레코드 정의 (registry 임포트 실패 시 fallback)
# ---------------------------------------------------------------------------

REQUIRED_POLICIES = [
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
]

REQUIRED_CONSTANTS = [
    "AUTH_MODE_USER_PRESENT", "AUTH_MODE_TRUSTED_REUSE", "AUTH_MODE_OAUTH_API",
    "SESSION_TRUST_NONE", "SESSION_TRUST_PRESENT", "SESSION_TRUST_REUSABLE",
    "FINAL_ACTION_SAVE", "FINAL_ACTION_SUBMIT", "FINAL_ACTION_PAY",
    "FINAL_ACTION_SIGN", "FINAL_ACTION_DOMAIN_CHANGE", "FINAL_ACTION_BID",
    "GATE_PREPARE_ALLOWED", "GATE_FINAL_BLOCKED", "GATE_USER_APPROVAL_NEEDED",
    "FINAL_ACTION_TYPES", "FINAL_ACTION_SCOPES", "SECRET_STORAGE_SCOPES",
    "DOMAIN_CHANGE_SCOPES", "TRUSTED_SESSION_SCOPES",
]

REQUIRED_AUDIT_EVENTS = [
    "AUDIT_USER_PRESENT_AUTH_REQUIRED",
    "AUDIT_TRUSTED_SESSION_REUSED",
    "AUDIT_TRUSTED_SESSION_EXPIRED",
    "AUDIT_FINAL_APPROVAL_REQUIRED",
    "AUDIT_FINAL_APPROVAL_GRANTED",
    "AUDIT_FINAL_ACTION_BLOCKED",
    "AUDIT_SECRET_STORAGE_BLOCKED",
    "AUDIT_CERT_PASSWORD_BLOCKED",
    "AUDIT_SERVER_LOGIN_BLOCKED",
    "AUDIT_DOMAIN_CHANGE_GATE",
]

REQUIRED_POLICY_FIELDS = [
    "safe_to_prepare", "safe_to_click_final_button",
    "requires_final_approval", "allowed_to_reuse_trusted_session",
    "requires_user_present_auth", "requires_reauth",
]

SITE_KEYS = [
    "gabia", "naver", "google", "g2b", "bank",
    "tax", "bid", "insurance", "certificate_portal", "eum",
]

SECURITY_CONSTRAINTS = [
    "password/otp/cert_password/token/cookie/session/credential/private_key 저장 금지",
    "인증서 파일 서버 복사 금지",
    "브라우저 쿠키 덤프 금지",
    "세션 탈취 금지",
    "보안 우회 금지",
    "최종 제출/저장/변경 버튼 자동 클릭 금지",
    "결제/송금/투찰/전자서명 자동 실행 금지",
]


def _check_policies() -> tuple[list[str], list[str]]:
    """registry에 10개 신규 정책이 모두 등록되어 있는지 확인한다."""
    present, missing = [], []
    try:
        from ai_orchestrator.safety_policy.safety_policy_registry import get_policy
        for pid in REQUIRED_POLICIES:
            if get_policy(pid):
                present.append(pid)
            else:
                missing.append(pid)
    except Exception as exc:
        missing = REQUIRED_POLICIES[:]
        missing.append(f"[IMPORT_ERROR] {exc}")
    return present, missing


def _check_constants() -> tuple[list[str], list[str]]:
    """신규 상수가 모두 registry에 있는지 확인한다."""
    present, missing = [], []
    try:
        import ai_orchestrator.safety_policy.safety_policy_registry as r
        for const in REQUIRED_CONSTANTS:
            if hasattr(r, const):
                present.append(const)
            else:
                missing.append(const)
    except Exception as exc:
        missing = REQUIRED_CONSTANTS[:]
        missing.append(f"[IMPORT_ERROR] {exc}")
    return present, missing


def _check_policy_decision_fields() -> tuple[list[str], list[str]]:
    """PolicyDecision에 신규 필드가 있는지 확인한다."""
    present, missing = [], []
    try:
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
            reason="audit",
        )
        for f in REQUIRED_POLICY_FIELDS:
            if hasattr(d, f):
                present.append(f)
            else:
                missing.append(f)
    except Exception as exc:
        missing = REQUIRED_POLICY_FIELDS[:]
        missing.append(f"[IMPORT_ERROR] {exc}")
    return present, missing


def _check_audit_events() -> tuple[list[str], list[str]]:
    """AuditEvent 상수가 모두 있는지 확인한다."""
    present, missing = [], []
    try:
        import ai_orchestrator.services.execution_policy_service as svc
        for ev in REQUIRED_AUDIT_EVENTS:
            if hasattr(svc, ev):
                present.append(ev)
            else:
                missing.append(ev)
    except Exception as exc:
        missing = REQUIRED_AUDIT_EVENTS[:]
        missing.append(f"[IMPORT_ERROR] {exc}")
    return present, missing


def _check_site_policy() -> tuple[list[str], list[str]]:
    """사이트별 액션 정책 판정이 동작하는지 확인한다."""
    working, failing = [], []
    try:
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
        svc = ExecutionPolicyService()
        for site in SITE_KEYS:
            try:
                dec = svc.decide_for_site_action(site, "navigate_to_work_screen")
                assert dec.safe_to_prepare is True
                assert dec.safe_to_click_final_button is False
                working.append(site)
            except Exception as e:
                failing.append(f"{site}: {e}")
    except Exception as exc:
        failing = [f"[IMPORT_ERROR] {exc}"]
    return working, failing


def _check_final_action_blocked() -> bool:
    """SAVE 행위가 final_action으로 올바르게 감지되는지 확인한다."""
    try:
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
        svc = ExecutionPolicyService()
        return svc.is_final_action("SAVE") and svc.is_final_action("click_submit_button")
    except Exception:
        return False


def _check_secret_storage_blocked() -> bool:
    """dump_cookie가 secret_storage_forbidden으로 감지되는지 확인한다."""
    try:
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService
        svc = ExecutionPolicyService()
        return svc.is_secret_storage_forbidden("dump_cookie")
    except Exception:
        return False


def main() -> None:
    policies_present, policies_missing = _check_policies()
    consts_present, consts_missing = _check_constants()
    fields_present, fields_missing = _check_policy_decision_fields()
    events_present, events_missing = _check_audit_events()
    sites_working, sites_failing = _check_site_policy()
    final_action_ok = _check_final_action_blocked()
    secret_ok = _check_secret_storage_blocked()

    checklist = [
        {"item": "신규 정책 10개 등록", "ok": len(policies_missing) == 0},
        {"item": "신규 상수 모두 존재", "ok": len(consts_missing) == 0},
        {"item": "PolicyDecision 신규 필드", "ok": len(fields_missing) == 0},
        {"item": "AuditEvent 상수 10개", "ok": len(events_missing) == 0},
        {"item": "사이트별 정책 판정 정상", "ok": len(sites_failing) == 0},
        {"item": "SAVE = 최종행위 감지", "ok": final_action_ok},
        {"item": "dump_cookie = 시크릿 저장 금지 감지", "ok": secret_ok},
    ]

    all_pass = all(c["ok"] for c in checklist)

    report = {
        "policy_redesign_id": "ASSISTANT_TRUSTED_SESSION_AND_USER_APPROVAL_POLICY_REDESIGN_01",
        "read_only": True,
        "policies_registered": policies_present,
        "policies_missing": policies_missing,
        "constants_present_count": len(consts_present),
        "constants_missing": consts_missing,
        "policy_decision_fields_present": fields_present,
        "policy_decision_fields_missing": fields_missing,
        "audit_events_present_count": len(events_present),
        "audit_events_missing": events_missing,
        "sites_working": sites_working,
        "sites_failing": sites_failing,
        "final_action_detection_ok": final_action_ok,
        "secret_storage_detection_ok": secret_ok,
        "security_constraints": SECURITY_CONSTRAINTS,
        "operating_philosophy": [
            "AI는 업무를 준비한다.",
            "AI는 신뢰 세션을 재사용한다.",
            "AI는 최종 버튼 앞에서 멈춘다.",
            "대표님이 승인한다.",
            "그 후 결과를 AI가 검증하고 기록한다.",
        ],
        "checklist": checklist,
        "verdict": "PASS" if all_pass else "FAIL",
    }

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if all_pass else 1)

    print("=" * 60)
    print("신뢰 세션 / 최종 승인 게이트 정책 감사")
    print("=" * 60)
    print(f"등록 정책: {len(policies_present)}/10", end="")
    if policies_missing:
        print(f"  ⚠ 미등록: {policies_missing}")
    else:
        print("  PASS")

    print(f"상수: {len(consts_present)}/{len(REQUIRED_CONSTANTS)}", end="")
    if consts_missing:
        print(f"  ⚠ 누락: {consts_missing}")
    else:
        print("  PASS")

    print(f"PolicyDecision 신규 필드: {len(fields_present)}/{len(REQUIRED_POLICY_FIELDS)}", end="")
    if fields_missing:
        print(f"  ⚠ 누락: {fields_missing}")
    else:
        print("  PASS")

    print(f"AuditEvent: {len(events_present)}/{len(REQUIRED_AUDIT_EVENTS)}", end="")
    if events_missing:
        print(f"  ⚠ 누락: {events_missing}")
    else:
        print("  PASS")

    print(f"사이트 정책: {len(sites_working)}/{len(SITE_KEYS)}", end="")
    if sites_failing:
        print(f"  ⚠ 실패: {sites_failing}")
    else:
        print("  PASS")

    for c in checklist:
        status = "PASS" if c["ok"] else "FAIL"
        print(f"  [{status}] {c['item']}")

    print()
    print(f"최종 판정: {report['verdict']}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
