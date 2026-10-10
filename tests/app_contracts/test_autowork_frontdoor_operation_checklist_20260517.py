"""autowork.haehan-ai.kr 정문 개통 운영 체크리스트 테스트.

ASSISTANT_AUTOWORK_FRONTDOOR_OPERATION_CHECKLIST_01

금지:
    실제 nginx reload 금지 / certbot 실행 금지 / DB write 금지
    UI 변경 금지 / 5050 중단 금지 / secret 출력 금지
    skip/xfail 금지
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 1. 감사 스크립트 존재
# ---------------------------------------------------------------------------


def test_audit_script_exists():
    p = ROOT / "tools" / "audits" / "backend" / "audit_autowork_frontdoor_operation.py"
    assert p.exists(), f"audit script 없음: {p}"


def test_audit_script_importable():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_autowork_frontdoor_operation",
        ROOT / "tools" / "audits" / "backend" / "audit_autowork_frontdoor_operation.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run_audit")
    assert hasattr(mod, "AUTOWORK_FQDN")


# ---------------------------------------------------------------------------
# 2. FQDN 고정
# ---------------------------------------------------------------------------


def test_autowork_fqdn_is_primary():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_autowork_frontdoor_operation",
        ROOT / "tools" / "audits" / "backend" / "audit_autowork_frontdoor_operation.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.AUTOWORK_FQDN == "autowork.haehan-ai.kr"


def test_autowork_dns_target_ip():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_autowork_frontdoor_operation",
        ROOT / "tools" / "audits" / "backend" / "audit_autowork_frontdoor_operation.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.AUTOWORK_DNS_TARGET_IP == "1.201.176.236"


# ── 이하 공통 mod 로딩 헬퍼 ──────────────────────────────────────────────────


def _load_audit_mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_autowork_frontdoor_operation",
        ROOT / "tools" / "audits" / "backend" / "audit_autowork_frontdoor_operation.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 3. autowork는 대표 웹 주소
# ---------------------------------------------------------------------------


def test_autowork_is_primary_web_address():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["fqdn"]["is_primary_domain"] is True


def test_autowork_role_defined():
    mod = _load_audit_mod()
    assert "정문" in mod.AUTOWORK_ROLE or "본관" in mod.AUTOWORK_ROLE


# ---------------------------------------------------------------------------
# 4. API base URL 단기 전략 고정
# ---------------------------------------------------------------------------


def test_api_short_term_uses_orchestrator_path():
    mod = _load_audit_mod()
    assert "/orchestrator/api/" in mod.API_BASE_URL_SHORT_TERM


def test_api_strategy_reason_exists():
    mod = _load_audit_mod()
    assert len(mod.API_CHANGE_REASON_NOT_NOW) > 10


def test_api_long_term_candidates_count():
    mod = _load_audit_mod()
    assert len(mod.API_BASE_URL_LONG_TERM_CANDIDATES) >= 3


# ---------------------------------------------------------------------------
# 5. 5050 중단 금지 조건
# ---------------------------------------------------------------------------


def test_5050_stop_forbidden_in_routing():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["routing"]["5050_stop_forbidden"] is True


def test_5050_stop_in_safe_boundary():
    mod = _load_audit_mod()
    assert mod.SAFE_BOUNDARY["5050_stop"] is False


# ---------------------------------------------------------------------------
# 6. /orchestrator/api/ → 8400 조건
# ---------------------------------------------------------------------------


def test_orchestrator_api_8400_documented():
    mod = _load_audit_mod()
    routes = mod.NGINX_ROUTING
    api_route = routes.get("/orchestrator/api/", {})
    assert "8400" in api_route.get("target", "")


def test_orchestrator_api_8400_in_audit():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["routing"]["orchestrator_api_8400_required"] is True
    assert "8400" in result["routing"]["orchestrator_api"]


# ---------------------------------------------------------------------------
# 7. /orchestrator/ → 5050 조건
# ---------------------------------------------------------------------------


def test_orchestrator_legacy_5050_documented():
    mod = _load_audit_mod()
    routes = mod.NGINX_ROUTING
    legacy = routes.get("/orchestrator/", {})
    assert "5050" in legacy.get("target", "")


def test_orchestrator_5050_in_audit():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert "5050" in result["routing"]["orchestrator_legacy"]


# ---------------------------------------------------------------------------
# 8. SSL 인증서 경로 조건
# ---------------------------------------------------------------------------


def test_ssl_cert_path_is_autowork():
    mod = _load_audit_mod()
    assert "autowork" in mod.SSL_CERT_PATH
    assert mod.SSL_CERT_PATH.endswith("fullchain.pem")


def test_ssl_key_path_defined_no_output():
    mod = _load_audit_mod()
    assert "autowork" in mod.SSL_KEY_PATH
    assert mod.SSL_KEY_PATH.endswith("privkey.pem")


def test_ssl_cert_path_in_audit():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert "autowork" in result["ssl"]["cert_path"]


# ---------------------------------------------------------------------------
# 9. 인증서 만료일 점검 조건
# ---------------------------------------------------------------------------


def test_ssl_expire_date_recorded():
    mod = _load_audit_mod()
    assert mod.SSL_EXPIRE_DATE == "2026-08-14"


def test_ssl_renew_before_days():
    mod = _load_audit_mod()
    assert mod.SSL_RENEW_BEFORE_DAYS == 30


def test_ssl_renew_deadline_in_audit():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert "2026-07-15" in result["ssl"]["renew_deadline"]


# ---------------------------------------------------------------------------
# 10. rollback backup 파일명 조건
# ---------------------------------------------------------------------------


def test_rollback_nginx_backup_name():
    mod = _load_audit_mod()
    assert "20260517_002307_pre_autowork" in mod.NGINX_ROLLBACK_DEFAULT


def test_rollback_acme_backup_name():
    mod = _load_audit_mod()
    assert "20260517_002320_pre_autowork" in mod.NGINX_ROLLBACK_ACME


def test_rollback_in_audit():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert "20260517_002307_pre_autowork" in result["rollback"]["nginx_default_backup"]
    assert "20260517_002320_pre_autowork" in result["rollback"]["nginx_acme_backup"]


def test_rollback_forbidden_now():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["rollback"]["rollback_forbidden_now"] is True


def test_rollback_conditions_count():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert len(result["rollback"]["rollback_conditions"]) >= 4


# ---------------------------------------------------------------------------
# 11. smoke command가 HTTP/HTTPS/TLS/orchestrator 포함
# ---------------------------------------------------------------------------


def test_smoke_commands_http_301():
    mod = _load_audit_mod()
    result = mod.run_audit()
    cmds = " ".join(result["smoke"]["smoke_commands"])
    assert "http://" in cmds and "301" in cmds


def test_smoke_commands_https_200():
    mod = _load_audit_mod()
    result = mod.run_audit()
    cmds = " ".join(result["smoke"]["smoke_commands"])
    assert "https://" in cmds and "200" in cmds


def test_smoke_commands_tls_verify():
    mod = _load_audit_mod()
    result = mod.run_audit()
    cmds = " ".join(result["smoke"]["smoke_commands"])
    assert "openssl" in cmds and "Verify" in cmds


def test_smoke_commands_orchestrator():
    mod = _load_audit_mod()
    result = mod.run_audit()
    cmds = " ".join(result["smoke"]["smoke_commands"])
    assert "orchestrator" in cmds


def test_smoke_commands_5050():
    mod = _load_audit_mod()
    result = mod.run_audit()
    cmds = " ".join(result["smoke"]["smoke_commands"])
    assert "5050" in cmds


# ---------------------------------------------------------------------------
# 12. certbot 실행 금지 조건
# ---------------------------------------------------------------------------


def test_certbot_exec_forbidden_in_boundary():
    mod = _load_audit_mod()
    assert mod.SAFE_BOUNDARY["certbot_execution"] is False


def test_certbot_forbidden_in_checklist():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["checklist"]["certbot_exec_forbidden"] is True


# ---------------------------------------------------------------------------
# 13. nginx reload 금지 조건
# ---------------------------------------------------------------------------


def test_nginx_reload_forbidden_in_boundary():
    mod = _load_audit_mod()
    assert mod.SAFE_BOUNDARY["nginx_reload"] is False


def test_nginx_reload_forbidden_in_checklist():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["checklist"]["nginx_reload_forbidden"] is True


# ---------------------------------------------------------------------------
# 14. UI 인테리어 미착수 조건
# ---------------------------------------------------------------------------


def test_frontend_interior_not_started():
    mod = _load_audit_mod()
    assert mod.FRONTEND_INTERIOR_STARTED is False


def test_frontend_interior_preconditions_count():
    mod = _load_audit_mod()
    assert len(mod.FRONTEND_INTERIOR_PRECONDITIONS) >= 4


def test_ui_not_started_in_checklist():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["checklist"]["ui_change_not_started"] is True


# ---------------------------------------------------------------------------
# 15. 전체 audit PASS
# ---------------------------------------------------------------------------


def test_audit_all_ok():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["all_ok"] is True, f"audit 실패: {result}"


def test_audit_verdict_ready():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert "READY" in result["verdict"] or "PASS" in result["verdict"]


def test_audit_safe_boundary_no_violations():
    mod = _load_audit_mod()
    result = mod.run_audit()
    assert result["boundary"]["violations"] == []


def test_checklist_completeness():
    mod = _load_audit_mod()
    result = mod.run_audit()
    checklist = result["checklist"]
    assert len(checklist) >= 15
    failed = [k for k, v in checklist.items() if not v]
    assert failed == [], f"체크리스트 실패 항목: {failed}"
