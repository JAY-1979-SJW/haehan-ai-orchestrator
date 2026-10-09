"""APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01 테스트.

Priority 1 read-only endpoint 구현 계획 검증.
실제 구현 없음 — 시공계획서 공정.
"""
from __future__ import annotations

import pytest

import tools.audits.app.audit_app_api_readonly_endpoints_implementation_plan as m

# ── 1. audit script / 전역 플래그 ─────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_api_readonly_endpoints_implementation_plan  # noqa: F401


def test_audit_id():
    assert m.AUDIT_ID == "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN"


def test_implementation_allowed_false():
    assert m.IMPLEMENTATION_ALLOWED is False


def test_router_modification_allowed_false():
    assert m.ROUTER_MODIFICATION_ALLOWED is False


def test_frontend_wiring_allowed_false():
    assert m.FRONTEND_WIRING_ALLOWED is False


def test_mutation_endpoint_allowed_false():
    assert m.MUTATION_ENDPOINT_ALLOWED is False


def test_server_action_allowed_false():
    assert m.SERVER_ACTION_ALLOWED is False


# ── 2. priority1 plan matrix ──────────────────────────────────────────────────

def test_priority1_plan_3_endpoints():
    assert len(m.PRIORITY1_ENDPOINT_PLAN_MATRIX) == 3


@pytest.mark.parametrize("endpoint", [
    "GET /api/v1/app/health/summary",
    "GET /api/v1/app/providers",
    "GET /api/v1/app/storage/status",
])
def test_priority1_endpoint_exists(endpoint: str):
    eps = [e["endpoint"] for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX]
    assert endpoint in eps


def test_all_priority1_method_get():
    for ep in m.PRIORITY1_ENDPOINT_PLAN_MATRIX:
        assert ep["method"] == "GET"


def test_all_priority1_is_1():
    for ep in m.PRIORITY1_ENDPOINT_PLAN_MATRIX:
        assert ep["priority"] == 1


def test_all_mutation_allowed_false():
    for ep in m.PRIORITY1_ENDPOINT_PLAN_MATRIX:
        assert ep["mutation_allowed"] is False


def test_all_side_effect_false():
    for ep in m.PRIORITY1_ENDPOINT_PLAN_MATRIX:
        assert ep["side_effect_allowed"] is False


# ── 3. router location ────────────────────────────────────────────────────────

def test_selected_router_file_exists():
    assert m.ROUTER_LOCATION_PLAN.get("selected_router_file")


def test_router_modification_not_allowed_now():
    assert m.ROUTER_LOCATION_PLAN.get("router_modification_allowed_now") is False


# ── 4. response schema frozen ─────────────────────────────────────────────────

def test_all_response_schema_frozen():
    for ep in m.PRIORITY1_ENDPOINT_PLAN_MATRIX:
        assert ep.get("response_schema_frozen") is True


# ── 5. health schema 검증 ─────────────────────────────────────────────────────

def test_health_schema_has_dry_run_enabled():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "health" in e["endpoint"])
    schema_data = ep["response_schema"]["data"]
    assert "post_tasks_dry_run_enabled" in schema_data


def test_health_schema_no_restart_allowed_true():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "health" in e["endpoint"])
    forbidden = ep.get("forbidden_response_fields", [])
    assert any("restart_allowed=true" in f for f in forbidden)


# ── 6. providers schema 검증 ─────────────────────────────────────────────────

def test_providers_12_required():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "providers" in e["endpoint"])
    assert ep.get("provider_count_required") == 12


def test_providers_cookie_storage_false():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "providers" in e["endpoint"])
    assert ep.get("cookie_storage_allowed_all") is False


def test_providers_schema_has_cookie_storage_allowed():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "providers" in e["endpoint"])
    providers = ep["response_schema"]["data"]["providers"]
    assert "cookie_storage_allowed" in providers[0]


# ── 7. storage schema 검증 ────────────────────────────────────────────────────

def test_storage_named_volume_reflected():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "storage" in e["endpoint"])
    assert ep.get("schema_includes_named_volume") is True


def test_storage_bind_mount_reflected():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "storage" in e["endpoint"])
    assert ep.get("schema_includes_bind_mount") is True


def test_storage_approval_token_policy_reflected():
    ep = next(e for e in m.PRIORITY1_ENDPOINT_PLAN_MATRIX if "storage" in e["endpoint"])
    assert ep.get("schema_includes_approval_token_policy") is True


# ── 8. redaction policy ───────────────────────────────────────────────────────

@pytest.mark.parametrize("field", [
    "raw_token", "access_token", "cookie", "password", "approval_token_raw",
])
def test_redaction_field_exists(field: str):
    fields = [r["field"] for r in m.REDACTION_POLICY_MATRIX]
    assert field in fields


# ── 9. read-only guard matrix ─────────────────────────────────────────────────

def test_guard_mutation_allowed_false():
    assert m.READ_ONLY_GUARD_MATRIX["mutation_allowed"] is False


def test_guard_side_effect_false():
    assert m.READ_ONLY_GUARD_MATRIX["side_effect_allowed"] is False


def test_guard_server_action_false():
    assert m.READ_ONLY_GUARD_MATRIX["server_action_allowed"] is False


def test_guard_db_write_false():
    assert m.READ_ONLY_GUARD_MATRIX["db_write_allowed"] is False


def test_guard_secret_output_false():
    assert m.READ_ONLY_GUARD_MATRIX["secret_value_output_allowed"] is False


# ── 10. implementation order ──────────────────────────────────────────────────

def test_implementation_order_3():
    assert len(m.IMPLEMENTATION_ORDER_MATRIX) == 3


def test_health_order_1():
    entry = next(e for e in m.IMPLEMENTATION_ORDER_MATRIX if e["order"] == 1)
    assert "health" in entry["endpoint"]


def test_providers_order_2():
    entry = next(e for e in m.IMPLEMENTATION_ORDER_MATRIX if e["order"] == 2)
    assert "providers" in entry["endpoint"]


def test_storage_order_3():
    entry = next(e for e in m.IMPLEMENTATION_ORDER_MATRIX if e["order"] == 3)
    assert "storage" in entry["endpoint"]


def test_all_tests_required():
    for entry in m.IMPLEMENTATION_ORDER_MATRIX:
        assert len(entry.get("tests_required", [])) > 0


# ── 11. 이전 공정 회귀 ────────────────────────────────────────────────────────

def test_no_conflict_with_api_contract_prep():
    import tools.audits.app.audit_app_api_contract_endpoints_prep as a
    report = a.run_audit()
    assert report.verdict in (a.VERDICT_READY, a.VERDICT_WARN)


def test_no_conflict_with_readonly_status_cards():
    import tools.audits.app.audit_app_ui_readonly_backend_status_cards as a
    report = a.run_audit()
    assert report.verdict in (a.VERDICT_READY, a.VERDICT_WARN)


def test_no_conflict_with_mvp_design():
    import tools.audits.app.audit_app_foundation_mvp_design as a
    report = a.run_audit()
    assert report.verdict in (a.VERDICT_READY, a.VERDICT_WARN)


# ── 12. audit verdict ─────────────────────────────────────────────────────────

def test_audit_verdict_ready_or_warn():
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN), \
        f"verdict={report.verdict}"
