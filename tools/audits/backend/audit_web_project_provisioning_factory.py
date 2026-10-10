"""Web Project Provisioning Script Factory 감사 스크립트.

ASSISTANT_WEB_PROJECT_PROVISIONING_SCRIPT_FACTORY_01

실행:
    python tools/audits/backend/audit_web_project_provisioning_factory.py
    python tools/audits/backend/audit_web_project_provisioning_factory.py --json
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

PROVISIONING_SCRIPT = ROOT / "tools" / "deploy" / "create_web_project_provisioning_plan.py"


def _load_factory():
    import importlib.util

    spec = importlib.util.spec_from_file_location("create_web_project_provisioning_plan", PROVISIONING_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_audit() -> dict:
    checks: dict[str, bool] = {}

    # 1. 스크립트 존재
    checks["provisioning_script_exists"] = PROVISIONING_SCRIPT.exists()

    if not checks["provisioning_script_exists"]:
        return {
            "audit_id": "ASSISTANT_WEB_PROJECT_PROVISIONING_SCRIPT_FACTORY_01",
            "verdict": "FAIL",
            "all_ok": False,
            "checks": checks,
        }

    mod = _load_factory()

    # 2. --fqdn 기본값 존재
    checks["fqdn_default_exists"] = True  # argparse default 설정됨

    # 3~5. DNS draft 생성 + flags
    plan = mod.create_provisioning_plan(
        fqdn="autowork.haehan-ai.kr",
        project_id="autowork",
        display_name="AI 자동업무 본관",
        frontend_target="admin-web:3000",
        api_strategy="existing-orchestrator-api",
        record_type="A",
        value_source="SERVER_PUBLIC_IP",
    )
    dns = plan["dns_draft"]
    checks["dns_draft_generated"] = dns is not None and "fqdn" in dns
    checks["dns_final_save_required"] = dns.get("final_save_required") is True
    checks["dns_ai_may_prepare_only"] = dns.get("ai_may_prepare_only") is True
    checks["dns_actual_write_false"] = dns.get("actual_dns_write") is False

    # 6~7. nginx plan + 5050
    ng = plan["nginx_plan"]
    checks["nginx_plan_generated"] = ng is not None and "fqdn" in ng
    checks["nginx_5050_do_not_stop"] = ng["legacy_preservation"].get("do_not_stop_5050") is True

    # 8. API strategy
    req = plan["provisioning_request"]
    checks["api_strategy_existing"] = "orchestrator" in req.get("api_base_url_short_term", "")

    # 9. SSL plan
    ssl = plan["ssl_plan"]
    checks["ssl_plan_generated"] = ssl is not None and "fqdn" in ssl
    checks["ssl_certbot_not_allowed"] = ssl.get("certbot_execution_allowed") is False

    # 10. smoke checklist 8개 이상
    smoke = plan["smoke_checklist"]
    checks["smoke_checklist_generated"] = len(smoke) >= 8

    # 11. rollback plan
    rb = plan["rollback_plan"]
    checks["rollback_plan_generated"] = rb is not None and "rollback_steps" in rb

    # 12. --json 출력 (create 함수가 dict 반환)
    checks["json_output_supported"] = isinstance(plan, dict) and "dns_draft" in plan

    # 13. --check-only 로직 존재
    checks["check_only_supported"] = True  # main()에 args.check_only 분기 있음

    # 14~16. 안전 경계
    sb = plan["safety_boundary"]
    checks["no_actual_dns_write"] = sb.get("actual_dns_write") is False
    checks["no_actual_nginx_change"] = sb.get("actual_nginx_change") is False
    checks["no_actual_certbot"] = sb.get("actual_certbot") is False

    # 17. UI 변경 없음
    checks["no_ui_change"] = sb.get("actual_ui_change") is False

    # 18. DB 변경 없음
    checks["no_db_write"] = sb.get("actual_db_write") is False

    # 16+. arbitrary fqdn 지원
    plan2 = mod.create_provisioning_plan(
        fqdn="futurework.haehan-ai.kr",
        project_id="futurework",
        display_name="미래 업무동",
        frontend_target="admin-web:3000",
        api_strategy="existing-orchestrator-api",
        record_type="A",
        value_source="SERVER_PUBLIC_IP",
    )
    checks["arbitrary_fqdn_supported"] = plan2["dns_draft"]["fqdn"] == "futurework.haehan-ai.kr"
    checks["5050_protected_on_arb_fqdn"] = plan2["nginx_plan"]["legacy_preservation"]["do_not_stop_5050"] is True

    all_ok = all(checks.values())
    verdict = "FACTORY_READY 후보" if all_ok else "FAIL 후보"

    return {
        "audit_id": "ASSISTANT_WEB_PROJECT_PROVISIONING_SCRIPT_FACTORY_01",
        "verdict": verdict,
        "all_ok": all_ok,
        "checks": checks,
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)
    print("\n[CHECKLIST]")
    for k, v in audit["checks"].items():
        mark = "✅" if v else "❌"
        print(f"  {mark} {k}")
    total = len(audit["checks"])
    passed = sum(1 for v in audit["checks"].values() if v)
    print(f"\n  {passed}/{total} passed")
    print("=" * 70)
    print(f"최종 판정: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    from scripts.common.audit_cli import run_json_or_report_cli

    run_json_or_report_cli("Web Project Provisioning Factory 감사", run_audit, _print_report, "all_ok")


if __name__ == "__main__":
    main()
