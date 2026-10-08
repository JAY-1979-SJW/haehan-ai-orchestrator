"""autowork 서브도메인 DNS/nginx/SSL 기초 도면 감사 스크립트.

ASSISTANT_SUBDOMAIN_DNS_ROUTING_FOUNDATION_01

실행:
    python scripts/ops/audit_subdomain_dns_routing_foundation.py
    python scripts/ops/audit_subdomain_dns_routing_foundation.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SAFE_BOUNDARY = {
    "actual_dns_write": False,
    "actual_nginx_change": False,
    "actual_certbot": False,
    "actual_gabia_access": False,
    "actual_ssl_issue": False,
    "server_restart": False,
    "db_schema_change": False,
    "ui_change": False,
    "secret_output": False,
}


def _check_dns_draft() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {}
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import (
            AUTOWORK_DNS_APPROVAL_SUMMARY,
            AUTOWORK_DNS_DRAFT,
            AUTOWORK_FQDN,
        )

        result["fqdn_autowork_defined"] = AUTOWORK_FQDN == "autowork.haehan-ai.kr"
        result["dns_draft_exists"] = AUTOWORK_DNS_DRAFT is not None
        result["dns_draft_final_save_req"] = AUTOWORK_DNS_DRAFT.requires_final_approval is True
        result["dns_draft_safe_to_prepare"] = AUTOWORK_DNS_DRAFT.safe_to_prepare is True
        result["dns_approval_ai_prepare_only"] = AUTOWORK_DNS_APPROVAL_SUMMARY.ai_may_prepare_only is True
        result["dns_approval_user_must_save"] = AUTOWORK_DNS_APPROVAL_SUMMARY.user_must_click_final_save is True
        safe_d = AUTOWORK_DNS_DRAFT.to_safe_dict()
        forbidden = {"password", "otp", "token", "cookie", "session", "cert_password"}
        result["dns_draft_no_secrets"] = not bool(set(safe_d.keys()) & forbidden)
    except Exception as e:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_nginx_plan() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {}
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import (
            EXISTING_NGINX_ROUTES,
            NGINX_RECOMMENDED_PLAN,
        )

        locs = [r["location"] for r in EXISTING_NGINX_ROUTES]
        result["existing_api_route"] = any("/orchestrator/api/" in l for l in locs)  # noqa: E741
        result["existing_5050_route"] = any(l == "/orchestrator/" for l in locs)  # noqa: E741
        result["existing_admin_web_route"] = any("/orchestrator/admin-web/" in l for l in locs)  # noqa: E741
        result["nginx_plan_exists"] = NGINX_RECOMMENDED_PLAN is not None
        result["nginx_change_not_allowed_now"] = NGINX_RECOMMENDED_PLAN.get("change_allowed_now") is False
        result["5050_impact_none"] = "없음" in str(NGINX_RECOMMENDED_PLAN.get("5050_impact", ""))
    except Exception as e:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_5050_protection() -> bool:
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import EXISTING_NGINX_ROUTES

        for r in EXISTING_NGINX_ROUTES:
            if r["location"] == "/orchestrator/":
                return "5050" in r.get("note", "") or "중단 금지" in r.get("note", "")
        return False
    except Exception:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        return False


def _check_ssl_plan() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {}
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SSL_PLAN

        result["ssl_plan_exists"] = SSL_PLAN is not None
        result["ssl_fqdn_correct"] = SSL_PLAN.get("fqdn") == "autowork.haehan-ai.kr"
        result["ssl_certbot_not_executed"] = SSL_PLAN.get("actual_certbot_execution") is False
        result["ssl_change_not_allowed"] = SSL_PLAN.get("change_allowed_now") is False
        result["ssl_steps_count"] = len(SSL_PLAN.get("steps", [])) >= 5
        result["ssl_dns_precondition"] = len(SSL_PLAN.get("preconditions", [])) >= 2
    except Exception as e:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_smoke() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {}
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SMOKE_CHECKLIST

        result["smoke_count_ge_8"] = len(SMOKE_CHECKLIST) >= 8
        result["smoke_has_dns_resolve"] = any(
            "DNS" in s.get("check", "") or "resolve" in s.get("check", "").lower() for s in SMOKE_CHECKLIST
        )
        result["smoke_has_https"] = any(
            "HTTPS" in s.get("check", "") or "443" in s.get("check", "") for s in SMOKE_CHECKLIST
        )
        result["smoke_has_existing_api"] = any(
            "orchestrator" in s.get("cmd", "") or "orchestrator" in s.get("check", "") for s in SMOKE_CHECKLIST
        )
        result["smoke_has_5050"] = any(
            "5050" in s.get("check", "") or "legacy" in s.get("check", "").lower() for s in SMOKE_CHECKLIST
        )
        result["smoke_p0_count"] = sum(1 for s in SMOKE_CHECKLIST if s.get("tier") == "P0") >= 3
    except Exception as e:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_rollback() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {}
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import (
            AUTOWORK_ROLLBACK_PLAN,
            NGINX_ROLLBACK_PLAN,
            SSL_ROLLBACK_PLAN,
        )

        result["dns_rollback_exists"] = AUTOWORK_ROLLBACK_PLAN is not None
        result["dns_rollback_user_approval"] = AUTOWORK_ROLLBACK_PLAN.requires_user_approval is True
        result["dns_rollback_steps_ge_4"] = len(AUTOWORK_ROLLBACK_PLAN.rollback_steps) >= 4
        result["nginx_rollback_exists"] = NGINX_ROLLBACK_PLAN is not None
        result["nginx_5050_protection"] = "5050" in str(NGINX_ROLLBACK_PLAN)
        result["ssl_rollback_exists"] = SSL_ROLLBACK_PLAN is not None
        result["ssl_no_cert_delete"] = "삭제하지 않" in str(SSL_ROLLBACK_PLAN)
    except Exception as e:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def _check_gabia_flow() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {}
    try:
        from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import (
            AUTOWORK_DNS_APPROVAL_SUMMARY,
            AUTOWORK_DNS_CHANGE_PREVIEW,
        )
        from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task

        result["change_preview_exists"] = AUTOWORK_DNS_CHANGE_PREVIEW is not None
        result["change_preview_approval_req"] = AUTOWORK_DNS_CHANGE_PREVIEW.approval_required is True
        result["change_preview_final_blocked"] = AUTOWORK_DNS_CHANGE_PREVIEW.final_button_blocked is True
        result["approval_summary_ai_prepare"] = AUTOWORK_DNS_APPROVAL_SUMMARY.ai_may_prepare_only is True
        task = make_autowork_dns_task()
        result["browser_task_fqdn_match"] = task.desired_fqdn == "autowork.haehan-ai.kr"
        result["browser_task_final_blocked"] = task.safe_to_click_final_button is False
    except Exception as e:  # noqa: BLE001 - 서브도메인 DNS 라우팅 기반 정책 자체감사 스크립트 - 예외 발생시 체크 결과를 False 또는 error 로 기록하는 fail-closed 패턴, 이미 안전한 방향
        result["[error]"] = str(e)
    return result


def main() -> None:
    dns = _check_dns_draft()
    nginx = _check_nginx_plan()
    p5050 = _check_5050_protection()
    ssl = _check_ssl_plan()
    smoke = _check_smoke()
    rb = _check_rollback()
    gabia = _check_gabia_flow()

    def ok(d: dict, k: str) -> bool:
        return d.get(k, False) is True

    checklist = [
        {"item": "fqdn autowork.haehan-ai.kr 정의", "ok": ok(dns, "fqdn_autowork_defined")},
        {"item": "DNS draft 존재", "ok": ok(dns, "dns_draft_exists")},
        {"item": "DNS draft final_save_required=True", "ok": ok(dns, "dns_draft_final_save_req")},
        {"item": "ai_may_prepare_only=True", "ok": ok(dns, "dns_approval_ai_prepare_only")},
        {"item": "user_must_click_final_save=True", "ok": ok(dns, "dns_approval_user_must_save")},
        {"item": "DNS draft secret 없음", "ok": ok(dns, "dns_draft_no_secrets")},
        {"item": "기존 /orchestrator/api/ 라우트 기록", "ok": ok(nginx, "existing_api_route")},
        {"item": "기존 /orchestrator/ 5050 라우트 기록", "ok": ok(nginx, "existing_5050_route")},
        {"item": "5050 중단 금지 조건 포함", "ok": p5050},
        {"item": "nginx 추천 계획 존재", "ok": ok(nginx, "nginx_plan_exists")},
        {"item": "nginx 변경 현재 금지", "ok": ok(nginx, "nginx_change_not_allowed_now")},
        {"item": "SSL 계획 존재", "ok": ok(ssl, "ssl_plan_exists")},
        {"item": "SSL FQDN 정확", "ok": ok(ssl, "ssl_fqdn_correct")},
        {"item": "certbot 현재 미실행", "ok": ok(ssl, "ssl_certbot_not_executed")},
        {"item": "smoke 체크리스트 8개 이상", "ok": ok(smoke, "smoke_count_ge_8")},
        {"item": "smoke DNS resolve 항목", "ok": ok(smoke, "smoke_has_dns_resolve")},
        {"item": "smoke HTTPS 항목", "ok": ok(smoke, "smoke_has_https")},
        {"item": "smoke 기존 /orchestrator 유지 항목", "ok": ok(smoke, "smoke_has_existing_api")},
        {"item": "DNS rollback 존재", "ok": ok(rb, "dns_rollback_exists")},
        {"item": "DNS rollback 사용자 승인 필요", "ok": ok(rb, "dns_rollback_user_approval")},
        {"item": "nginx rollback 5050 보호", "ok": ok(rb, "nginx_5050_protection")},
        {"item": "Gabia change preview 연결", "ok": ok(gabia, "change_preview_exists")},
        {"item": "browser task FQDN 일치", "ok": ok(gabia, "browser_task_fqdn_match")},
        {"item": "final button blocked", "ok": ok(gabia, "browser_task_final_blocked")},
    ]

    all_pass = all(c["ok"] for c in checklist)

    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import (
        AUTOWORK_DNS_DRAFT,
        AUTOWORK_ROLLBACK_PLAN,
        NGINX_RECOMMENDED_PLAN,
        SMOKE_CHECKLIST,
        SSL_PLAN,
    )

    report = {
        "plan_id": "ASSISTANT_SUBDOMAIN_DNS_ROUTING_FOUNDATION_01",
        "read_only": True,
        "safe_boundary": SAFE_BOUNDARY,
        "dns_draft": AUTOWORK_DNS_DRAFT.to_safe_dict(),
        "nginx_plan": NGINX_RECOMMENDED_PLAN,
        "ssl_plan": SSL_PLAN,
        "smoke_checklist": list(SMOKE_CHECKLIST),
        "rollback_plan": AUTOWORK_ROLLBACK_PLAN.to_safe_dict(),
        "gabia_flow": gabia,
        "checklist": checklist,
        "verdict": "PASS" if all_pass else "FAIL",
    }

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if all_pass else 1)

    print("=" * 60)
    print("autowork 서브도메인 DNS/nginx/SSL 기초 도면 감사")
    print("=" * 60)
    for c in checklist:
        status = "PASS" if c["ok"] else "FAIL"
        print(f"  [{status}] {c['item']}")
    print()
    print(f"최종 판정: {report['verdict']}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
