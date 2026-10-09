"""Web Project Provisioning Script Factory 테스트.

ASSISTANT_WEB_PROJECT_PROVISIONING_SCRIPT_FACTORY_01

금지:
    실제 DNS 조회 금지 / 실제 nginx 변경 금지 / 실제 certbot 실행 금지
    skip/xfail 금지
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PROVISIONING_SCRIPT = ROOT / "tools" / "deploy" / "create_web_project_provisioning_plan.py"
AUDIT_SCRIPT = ROOT / "tools" / "audits" / "backend" / "audit_web_project_provisioning_factory.py"

# 스크립트가 한글(em dash 포함)을 print 한다 — Windows 콘솔 기본 코드페이지(cp949)로는
# 인코딩 못 하는 문자가 있어 UnicodeEncodeError 로 죽는다. 자식 프로세스 stdio를 utf-8로 강제.
_SUBPROC_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _load_factory():
    import importlib.util

    spec = importlib.util.spec_from_file_location("create_web_project_provisioning_plan", PROVISIONING_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _autowork_plan():
    mod = _load_factory()
    return mod.create_provisioning_plan(
        fqdn="autowork.haehan-ai.kr",
        project_id="autowork",
        display_name="AI 자동업무 본관",
        frontend_target="admin-web:3000",
        api_strategy="existing-orchestrator-api",
        record_type="A",
        value_source="SERVER_PUBLIC_IP",
    )


def _futurework_plan():
    mod = _load_factory()
    return mod.create_provisioning_plan(
        fqdn="futurework.haehan-ai.kr",
        project_id="futurework",
        display_name="미래 업무동",
        frontend_target="admin-web:3000",
        api_strategy="existing-orchestrator-api",
        record_type="A",
        value_source="SERVER_PUBLIC_IP",
    )


# ---------------------------------------------------------------------------
# 1. provisioning script 존재
# ---------------------------------------------------------------------------


def test_provisioning_script_exists():
    assert PROVISIONING_SCRIPT.exists()


def test_audit_script_exists():
    assert AUDIT_SCRIPT.exists()


def test_provisioning_script_importable():
    mod = _load_factory()
    assert hasattr(mod, "create_provisioning_plan")
    assert hasattr(mod, "SAFE_BOUNDARY")
    assert hasattr(mod, "API_STRATEGIES")


# ---------------------------------------------------------------------------
# 2. autowork 기본 계획 생성
# ---------------------------------------------------------------------------


def test_autowork_plan_verdict_ready():
    plan = _autowork_plan()
    assert plan["verdict"] == "PLAN_READY"
    assert plan["all_ok"] is True


def test_autowork_plan_fqdn():
    plan = _autowork_plan()
    assert plan["provisioning_request"]["fqdn"] == "autowork.haehan-ai.kr"


def test_autowork_plan_has_all_sections():
    plan = _autowork_plan()
    required = {
        "provisioning_request",
        "dns_draft",
        "nginx_plan",
        "ssl_plan",
        "smoke_checklist",
        "rollback_plan",
        "safety_boundary",
        "next_steps",
    }
    assert required.issubset(set(plan.keys()))


# ---------------------------------------------------------------------------
# 3. arbitrary fqdn 계획 생성
# ---------------------------------------------------------------------------


def test_futurework_plan_generated():
    plan = _futurework_plan()
    assert plan["verdict"] == "PLAN_READY"


def test_futurework_fqdn_not_hardcoded_to_autowork():
    plan = _futurework_plan()
    assert plan["dns_draft"]["fqdn"] == "futurework.haehan-ai.kr"
    assert plan["provisioning_request"]["fqdn"] == "futurework.haehan-ai.kr"


def test_futurework_ssl_plan_fqdn():
    plan = _futurework_plan()
    assert plan["ssl_plan"]["fqdn"] == "futurework.haehan-ai.kr"


def test_futurework_smoke_fqdn():
    plan = _futurework_plan()
    cmds = " ".join(item["cmd"] for item in plan["smoke_checklist"])
    assert "futurework.haehan-ai.kr" in cmds


# ---------------------------------------------------------------------------
# 4. fqdn host/root_domain 분해
# ---------------------------------------------------------------------------


def test_fqdn_split_autowork():
    mod = _load_factory()
    host, root = mod._split_fqdn("autowork.haehan-ai.kr")
    assert host == "autowork"
    assert root == "haehan-ai.kr"


def test_fqdn_split_futurework():
    mod = _load_factory()
    host, root = mod._split_fqdn("futurework.haehan-ai.kr")
    assert host == "futurework"
    assert root == "haehan-ai.kr"


def test_fqdn_split_newservice():
    mod = _load_factory()
    host, root = mod._split_fqdn("newservice.haehan-ai.kr")
    assert host == "newservice"
    assert root == "haehan-ai.kr"


# ---------------------------------------------------------------------------
# 5. DNS draft final_save_required=True
# ---------------------------------------------------------------------------


def test_dns_final_save_required():
    plan = _autowork_plan()
    assert plan["dns_draft"]["final_save_required"] is True


def test_dns_final_save_required_arbitrary():
    plan = _futurework_plan()
    assert plan["dns_draft"]["final_save_required"] is True


# ---------------------------------------------------------------------------
# 6. DNS draft ai_may_prepare_only=True
# ---------------------------------------------------------------------------


def test_dns_ai_may_prepare_only():
    plan = _autowork_plan()
    assert plan["dns_draft"]["ai_may_prepare_only"] is True


def test_dns_user_must_click_final_save():
    plan = _autowork_plan()
    assert plan["dns_draft"]["user_must_click_final_save"] is True


# ---------------------------------------------------------------------------
# 7. nginx plan 5050 do-not-stop 포함
# ---------------------------------------------------------------------------


def test_nginx_5050_do_not_stop():
    plan = _autowork_plan()
    assert plan["nginx_plan"]["legacy_preservation"]["do_not_stop_5050"] is True


def test_nginx_5050_do_not_stop_arbitrary():
    plan = _futurework_plan()
    assert plan["nginx_plan"]["legacy_preservation"]["do_not_stop_5050"] is True


def test_nginx_orchestrator_api_8400():
    plan = _autowork_plan()
    assert plan["nginx_plan"]["legacy_preservation"]["orchestrator_api_8400_required"] is True


def test_nginx_change_not_allowed_now():
    plan = _autowork_plan()
    assert plan["nginx_plan"]["change_allowed_now"] is False


# ---------------------------------------------------------------------------
# 8. api strategy existing-orchestrator-api 표현
# ---------------------------------------------------------------------------


def test_api_strategy_uses_orchestrator_path():
    plan = _autowork_plan()
    url = plan["provisioning_request"]["api_base_url_short_term"]
    assert "/orchestrator/api/" in url


def test_api_strategy_change_not_allowed_now():
    mod = _load_factory()
    strat = mod.API_STRATEGIES["existing-orchestrator-api"]
    assert strat["change_allowed_now"] is False


# ---------------------------------------------------------------------------
# 9. SSL plan certbot_execution_allowed=False
# ---------------------------------------------------------------------------


def test_ssl_certbot_not_allowed():
    plan = _autowork_plan()
    assert plan["ssl_plan"]["certbot_execution_allowed"] is False


def test_ssl_dns_must_resolve_first():
    plan = _autowork_plan()
    assert plan["ssl_plan"]["dns_must_resolve_first"] is True


def test_ssl_actual_certbot_false():
    plan = _autowork_plan()
    assert plan["ssl_plan"]["actual_certbot"] is False


def test_ssl_plan_steps_count():
    plan = _autowork_plan()
    assert len(plan["ssl_plan"]["steps"]) >= 5


# ---------------------------------------------------------------------------
# 10. smoke checklist 8개 이상
# ---------------------------------------------------------------------------


def test_smoke_checklist_count():
    plan = _autowork_plan()
    assert len(plan["smoke_checklist"]) >= 8


def test_smoke_has_dns():
    plan = _autowork_plan()
    cmds = " ".join(i["cmd"] for i in plan["smoke_checklist"])
    assert "host" in cmds or "dig" in cmds


def test_smoke_has_http_301():
    plan = _autowork_plan()
    expects = " ".join(i["expect"] for i in plan["smoke_checklist"])
    assert "301" in expects


def test_smoke_has_https_200():
    plan = _autowork_plan()
    expects = " ".join(i["expect"] for i in plan["smoke_checklist"])
    assert "200" in expects


def test_smoke_has_tls():
    plan = _autowork_plan()
    cmds = " ".join(i["cmd"] for i in plan["smoke_checklist"])
    assert "openssl" in cmds


def test_smoke_has_orchestrator():
    plan = _autowork_plan()
    cmds = " ".join(i["cmd"] for i in plan["smoke_checklist"])
    assert "orchestrator" in cmds


def test_smoke_has_5050():
    plan = _autowork_plan()
    cmds = " ".join(i["cmd"] for i in plan["smoke_checklist"])
    assert "5050" in cmds


def test_smoke_p0_count():
    plan = _autowork_plan()
    p0 = [i for i in plan["smoke_checklist"] if i["tier"] == "P0"]
    assert len(p0) >= 3


# ---------------------------------------------------------------------------
# 11. rollback plan 존재
# ---------------------------------------------------------------------------


def test_rollback_plan_exists():
    plan = _autowork_plan()
    rb = plan["rollback_plan"]
    assert rb is not None
    assert rb["requires_user_approval"] is True


def test_rollback_steps_count():
    plan = _autowork_plan()
    assert len(plan["rollback_plan"]["rollback_steps"]) >= 4


def test_rollback_5050_must_survive():
    plan = _autowork_plan()
    assert plan["rollback_plan"]["5050_must_survive_rollback"] is True


def test_rollback_conditions_count():
    plan = _autowork_plan()
    assert len(plan["rollback_plan"]["rollback_conditions"]) >= 4


# ---------------------------------------------------------------------------
# 12. --json 출력 유효
# ---------------------------------------------------------------------------


def test_json_output_valid():
    result = subprocess.run(
        [sys.executable, str(PROVISIONING_SCRIPT), "--fqdn", "autowork.haehan-ai.kr", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
        env=_SUBPROC_ENV,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["verdict"] == "PLAN_READY"
    assert "dns_draft" in parsed


def test_json_arbitrary_fqdn():
    result = subprocess.run(
        [
            sys.executable,
            str(PROVISIONING_SCRIPT),
            "--fqdn",
            "futurework.haehan-ai.kr",
            "--project-id",
            "futurework",
            "--display-name",
            "미래 업무동",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
        env=_SUBPROC_ENV,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["dns_draft"]["fqdn"] == "futurework.haehan-ai.kr"


# ---------------------------------------------------------------------------
# 13. --check-only 동작
# ---------------------------------------------------------------------------


def test_check_only_exits_zero():
    result = subprocess.run(
        [sys.executable, str(PROVISIONING_SCRIPT), "--fqdn", "test.haehan-ai.kr", "--check-only"],
        capture_output=True,
        text=True,
        timeout=10,
        encoding="utf-8",
        env=_SUBPROC_ENV,
    )
    assert result.returncode == 0
    assert "check-only" in result.stdout.lower() or "CHECK-ONLY" in result.stdout


def test_check_only_no_plan_output():
    result = subprocess.run(
        [sys.executable, str(PROVISIONING_SCRIPT), "--fqdn", "test.haehan-ai.kr", "--check-only"],
        capture_output=True,
        text=True,
        timeout=10,
        encoding="utf-8",
        env=_SUBPROC_ENV,
    )
    assert "PLAN_READY" not in result.stdout


# ---------------------------------------------------------------------------
# 14. 실제 DNS write 없음
# ---------------------------------------------------------------------------


def test_no_actual_dns_write_in_boundary():
    mod = _load_factory()
    assert mod.SAFE_BOUNDARY["actual_dns_write"] is False


def test_no_actual_dns_write_in_plan():
    plan = _autowork_plan()
    assert plan["safety_boundary"]["actual_dns_write"] is False
    assert plan["dns_draft"]["actual_dns_write"] is False


# ---------------------------------------------------------------------------
# 15. 실제 nginx change 없음
# ---------------------------------------------------------------------------


def test_no_actual_nginx_change_in_boundary():
    mod = _load_factory()
    assert mod.SAFE_BOUNDARY["actual_nginx_change"] is False


def test_no_actual_nginx_change_in_plan():
    plan = _autowork_plan()
    assert plan["safety_boundary"]["actual_nginx_change"] is False
    assert plan["nginx_plan"]["actual_nginx_change"] is False


# ---------------------------------------------------------------------------
# 16. 실제 certbot 실행 없음
# ---------------------------------------------------------------------------


def test_no_actual_certbot_in_boundary():
    mod = _load_factory()
    assert mod.SAFE_BOUNDARY["actual_certbot"] is False


def test_no_actual_certbot_in_plan():
    plan = _autowork_plan()
    assert plan["safety_boundary"]["actual_certbot"] is False
    assert plan["ssl_plan"]["actual_certbot"] is False


# ---------------------------------------------------------------------------
# 17. UI 파일 변경 없음
# ---------------------------------------------------------------------------


def test_no_ui_change_in_boundary():
    mod = _load_factory()
    assert mod.SAFE_BOUNDARY["actual_ui_change"] is False


def test_no_ui_change_in_plan():
    plan = _autowork_plan()
    assert plan["safety_boundary"]["actual_ui_change"] is False


# ---------------------------------------------------------------------------
# 18. 기존 공정 기준 충돌 없음
# ---------------------------------------------------------------------------


def test_compatible_with_frontdoor_checklist():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_autowork_frontdoor_operation",
        ROOT / "tools" / "audits" / "backend" / "audit_autowork_frontdoor_operation.py",
    )
    fd_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fd_mod)

    factory_mod = _load_factory()
    # API base URL 전략 일치 확인
    assert "/orchestrator/api/" in fd_mod.API_BASE_URL_SHORT_TERM
    assert "/orchestrator/api/" in factory_mod.API_STRATEGIES["existing-orchestrator-api"]["base_url"]


def test_5050_target_consistent():
    mod = _load_factory()
    assert "5050" in mod.LEGACY_5050_TARGET


def test_orchestrator_api_target_consistent():
    mod = _load_factory()
    assert "8400" in mod.LEGACY_ORCHESTRATOR_API


# ---------------------------------------------------------------------------
# 19. audit script PASS
# ---------------------------------------------------------------------------


def test_audit_factory_all_ok():
    import importlib.util

    spec = importlib.util.spec_from_file_location("audit_web_project_provisioning_factory", AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run_audit()
    assert result["all_ok"] is True, f"audit 실패: {result['checks']}"


def test_safety_boundary_no_violations():
    plan = _autowork_plan()
    assert plan["safety_boundary"]["violations"] == []
    assert plan["safety_boundary"]["boundary_ok"] is True
