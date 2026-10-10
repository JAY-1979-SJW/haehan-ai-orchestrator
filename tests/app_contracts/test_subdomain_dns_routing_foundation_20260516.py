"""autowork 서브도메인 DNS/nginx/SSL 기초 도면 테스트.

ASSISTANT_SUBDOMAIN_DNS_ROUTING_FOUNDATION_01

금지:
    실제 DNS 저장 금지 / nginx 변경 금지 / certbot 실행 금지
    skip/xfail 금지
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 1. autowork.haehan-ai.kr 대표 FQDN 정의
# ---------------------------------------------------------------------------

def test_autowork_fqdn_defined():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_FQDN
    assert AUTOWORK_FQDN == "autowork.haehan-ai.kr"


def test_autowork_subdomain_and_base_domain():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_SUBDOMAIN, BASE_DOMAIN
    assert AUTOWORK_SUBDOMAIN == "autowork"
    assert BASE_DOMAIN == "haehan-ai.kr"


# ---------------------------------------------------------------------------
# 2. DNS draft final_save_required=True
# ---------------------------------------------------------------------------

def test_dns_draft_requires_final_approval():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_DNS_DRAFT
    assert AUTOWORK_DNS_DRAFT.requires_final_approval is True


def test_dns_draft_safe_to_prepare():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_DNS_DRAFT
    assert AUTOWORK_DNS_DRAFT.safe_to_prepare is True


def test_dns_draft_no_real_ip():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_DNS_DRAFT
    assert "PENDING" in AUTOWORK_DNS_DRAFT.value


# ---------------------------------------------------------------------------
# 3. AI may prepare only = True
# ---------------------------------------------------------------------------

def test_dns_approval_ai_prepare_only():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_DNS_APPROVAL_SUMMARY
    assert AUTOWORK_DNS_APPROVAL_SUMMARY.ai_may_prepare_only is True
    assert AUTOWORK_DNS_APPROVAL_SUMMARY.user_must_click_final_save is True


# ---------------------------------------------------------------------------
# 4. final button click blocked
# ---------------------------------------------------------------------------

def test_change_preview_final_button_blocked():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_DNS_CHANGE_PREVIEW
    assert AUTOWORK_DNS_CHANGE_PREVIEW.final_button_blocked is True
    assert AUTOWORK_DNS_CHANGE_PREVIEW.approval_required is True


def test_browser_task_final_button_blocked():
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task
    task = make_autowork_dns_task()
    assert task.safe_to_click_final_button is False
    assert task.final_button_blocked is True


# ---------------------------------------------------------------------------
# 5. nginx 기존 구조 유지 계획 포함
# ---------------------------------------------------------------------------

def test_existing_nginx_routes_documented():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import EXISTING_NGINX_ROUTES
    locs = [r["location"] for r in EXISTING_NGINX_ROUTES]
    assert any("/orchestrator/api/" in l for l in locs)
    assert any("/orchestrator/admin-web/" in l for l in locs)
    assert any(l == "/orchestrator/" for l in locs)


def test_nginx_recommended_plan_no_change_allowed():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import NGINX_RECOMMENDED_PLAN
    assert NGINX_RECOMMENDED_PLAN.get("change_allowed_now") is False


# ---------------------------------------------------------------------------
# 6. 5050 중단 금지 조건 포함
# ---------------------------------------------------------------------------

def test_5050_protection_in_existing_routes():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import EXISTING_NGINX_ROUTES
    flask_route = next(r for r in EXISTING_NGINX_ROUTES if r["location"] == "/orchestrator/")
    assert "5050" in flask_route.get("note", "") or "중단 금지" in flask_route.get("note", "")


def test_5050_protection_in_nginx_rollback():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import NGINX_ROLLBACK_PLAN
    assert "5050" in str(NGINX_ROLLBACK_PLAN)


# ---------------------------------------------------------------------------
# 7. SSL 계획 존재
# ---------------------------------------------------------------------------

def test_ssl_plan_exists():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SSL_PLAN
    assert SSL_PLAN is not None
    assert SSL_PLAN.get("fqdn") == "autowork.haehan-ai.kr"


def test_ssl_certbot_not_executed():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SSL_PLAN
    assert SSL_PLAN.get("actual_certbot_execution") is False
    assert SSL_PLAN.get("change_allowed_now") is False


def test_ssl_plan_has_steps():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SSL_PLAN
    assert len(SSL_PLAN.get("steps", [])) >= 5


# ---------------------------------------------------------------------------
# 8. smoke 체크리스트 8개 이상
# ---------------------------------------------------------------------------

def test_smoke_checklist_count():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SMOKE_CHECKLIST
    assert len(SMOKE_CHECKLIST) >= 8


def test_smoke_has_dns_and_https_items():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SMOKE_CHECKLIST
    checks = [s.get("check", "") + s.get("cmd", "") for s in SMOKE_CHECKLIST]
    assert any("DNS" in c or "resolve" in c.lower() for c in checks)
    assert any("HTTPS" in c or "443" in c for c in checks)


def test_smoke_has_existing_orchestrator_check():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SMOKE_CHECKLIST
    combined = " ".join(s.get("check", "") + s.get("cmd", "") for s in SMOKE_CHECKLIST)
    assert "orchestrator" in combined


def test_smoke_p0_items_exist():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import SMOKE_CHECKLIST
    p0_count = sum(1 for s in SMOKE_CHECKLIST if s.get("tier") == "P0")
    assert p0_count >= 3


# ---------------------------------------------------------------------------
# 9. rollback 계획 존재
# ---------------------------------------------------------------------------

def test_dns_rollback_exists():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_ROLLBACK_PLAN
    assert AUTOWORK_ROLLBACK_PLAN is not None
    assert AUTOWORK_ROLLBACK_PLAN.requires_user_approval is True


def test_dns_rollback_steps_sufficient():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_ROLLBACK_PLAN
    assert len(AUTOWORK_ROLLBACK_PLAN.rollback_steps) >= 4


def test_nginx_and_ssl_rollback_exist():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import NGINX_ROLLBACK_PLAN, SSL_ROLLBACK_PLAN
    assert NGINX_ROLLBACK_PLAN is not None
    assert SSL_ROLLBACK_PLAN is not None
    assert "삭제하지 않" in str(SSL_ROLLBACK_PLAN)


# ---------------------------------------------------------------------------
# 10. Gabia DNS workflow와 연결
# ---------------------------------------------------------------------------

def test_gabia_dns_work_registry_connected():
    from ai_orchestrator.connectors.gabia.dns_work_registry import get_work_trade
    wt = get_work_trade("gabia_dns_management")
    assert wt is not None
    assert wt.execution_location == "LOCAL_AGENT_REQUIRED"


# ---------------------------------------------------------------------------
# 11. Gabia browser task desired_fqdn 일치
# ---------------------------------------------------------------------------

def test_browser_task_fqdn_matches_plan():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_FQDN
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task
    task = make_autowork_dns_task()
    assert task.desired_fqdn == AUTOWORK_FQDN


# ---------------------------------------------------------------------------
# 12. 실제 DNS write 없음
# ---------------------------------------------------------------------------

def test_no_actual_dns_write():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import get_full_foundation_plan
    plan = get_full_foundation_plan()
    assert plan.get("actual_dns_write") is False
    assert plan.get("read_only") is True


# ---------------------------------------------------------------------------
# 13. 실제 nginx change 없음
# ---------------------------------------------------------------------------

def test_no_actual_nginx_change():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import get_full_foundation_plan
    plan = get_full_foundation_plan()
    assert plan.get("actual_nginx_change") is False


# ---------------------------------------------------------------------------
# 14. 실제 certbot 없음
# ---------------------------------------------------------------------------

def test_no_actual_certbot():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import get_full_foundation_plan
    plan = get_full_foundation_plan()
    assert plan.get("actual_certbot") is False


# ---------------------------------------------------------------------------
# 15. UI 파일 변경 없음 (plan read_only 확인)
# ---------------------------------------------------------------------------

def test_plan_read_only_flag():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import get_full_foundation_plan
    plan = get_full_foundation_plan()
    assert plan.get("read_only") is True
    assert plan.get("actual_gabia_access") is False


def test_dns_draft_safe_dict_no_secrets():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import AUTOWORK_DNS_DRAFT
    safe = AUTOWORK_DNS_DRAFT.to_safe_dict()
    forbidden = {"password", "otp", "token", "cookie", "session", "cert_password", "private_key"}
    assert not bool(set(safe.keys()) & forbidden)


# ---------------------------------------------------------------------------
# 16. quality gate: layer audit 무결성
# ---------------------------------------------------------------------------

def test_autowork_plan_no_forbidden_imports():
    import importlib
    import ai_orchestrator.connectors.gabia.autowork_subdomain_plan as mod
    assert mod is not None


def test_full_foundation_plan_structure():
    from ai_orchestrator.connectors.gabia.autowork_subdomain_plan import get_full_foundation_plan
    plan = get_full_foundation_plan()
    required_keys = {
        "plan_id", "fqdn", "read_only",
        "dns_draft", "nginx_recommended_plan", "ssl_plan",
        "smoke_checklist", "dns_rollback", "final_approval_gate",
    }
    assert required_keys.issubset(set(plan.keys()))
    gate = plan["final_approval_gate"]
    assert gate["safe_to_prepare"] is True
    assert gate["safe_to_click_final_button"] is False
    assert gate["requires_final_approval"] is True
