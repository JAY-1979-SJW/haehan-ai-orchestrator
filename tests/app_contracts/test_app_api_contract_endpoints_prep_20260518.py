"""APP_API_CONTRACT_ENDPOINTS_PREP_01 테스트.

read-only endpoint 계약·보안경계·redaction 정책 검증.
실제 구현 없음 — 계약 prep 공정.
"""
from __future__ import annotations

import pytest

import tools.audits.app.audit_app_api_contract_endpoints_prep as m

# ── 1. audit script / 전역 플래그 ─────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_api_contract_endpoints_prep  # noqa: F401


def test_audit_id():
    assert m.AUDIT_ID == "APP_API_CONTRACT_ENDPOINTS_PREP"


def test_implementation_allowed_false():
    assert m.IMPLEMENTATION_ALLOWED is False


def test_frontend_wiring_allowed_false():
    assert m.FRONTEND_WIRING_ALLOWED is False


def test_mutation_endpoint_allowed_false():
    assert m.MUTATION_ENDPOINT_ALLOWED is False


def test_server_action_allowed_false():
    assert m.SERVER_ACTION_ALLOWED is False


# ── 2. endpoint contract matrix ───────────────────────────────────────────────

def test_endpoint_matrix_5_plus():
    assert len(m.ENDPOINT_CONTRACT_MATRIX) >= 5


def test_all_endpoints_get():
    for ep in m.ENDPOINT_CONTRACT_MATRIX:
        assert ep["method"] == "GET", f"{ep['endpoint']} method != GET"


def test_all_mutation_allowed_false():
    for ep in m.ENDPOINT_CONTRACT_MATRIX:
        assert ep["mutation_allowed"] is False, f"{ep['endpoint']} mutation_allowed 위반"


def test_all_side_effect_false():
    for ep in m.ENDPOINT_CONTRACT_MATRIX:
        assert ep["side_effect_allowed"] is False, f"{ep['endpoint']} side_effect_allowed 위반"


# ── 3. 필수 endpoint 존재 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("endpoint", [
    "GET /api/v1/app/logs/audit",
    "GET /api/v1/app/storage/status",
    "GET /api/v1/app/providers",
    "GET /api/v1/app/deployment/status",
    "GET /api/v1/app/tasks",
])
def test_required_endpoint_exists(endpoint: str):
    endpoints = [e["endpoint"] for e in m.ENDPOINT_CONTRACT_MATRIX]
    assert endpoint in endpoints, f"{endpoint} 없음"


# ── 4. forbidden endpoint matrix ─────────────────────────────────────────────

def test_forbidden_matrix_exists():
    assert len(m.FORBIDDEN_ENDPOINT_MATRIX) > 0


@pytest.mark.parametrize("endpoint", [
    "POST /api/v1/app/tasks",
    "POST /api/v1/app/deploy",
    "POST /api/v1/app/restart",
    "POST /api/v1/app/execute",
])
def test_forbidden_endpoint_registered(endpoint: str):
    endpoints = [e["endpoint"] for e in m.FORBIDDEN_ENDPOINT_MATRIX]
    assert endpoint in endpoints, f"{endpoint} forbidden 미등록"


# ── 5. redaction policy ───────────────────────────────────────────────────────

@pytest.mark.parametrize("field", [
    "raw_token", "access_token", "refresh_token", "cookie",
    "session_secret", "password", "approval_token_raw",
])
def test_redaction_field_exists(field: str):
    fields = [r["field"] for r in m.REDACTION_POLICY_MATRIX]
    assert field in fields, f"{field} redaction 정책 없음"


def test_redaction_execute_url():
    fields = [r["field"] for r in m.REDACTION_POLICY_MATRIX]
    assert "execute_url" in fields


# ── 6. providers schema ───────────────────────────────────────────────────────

def test_providers_12_required():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "providers" in e["endpoint"])
    assert ep.get("providers_count_required") == 12


def test_providers_cookie_storage_false():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "providers" in e["endpoint"])
    assert ep.get("cookie_storage_allowed") is False


def test_providers_token_storage_false():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "providers" in e["endpoint"])
    assert ep.get("token_storage_allowed") is False


# ── 7. storage schema ─────────────────────────────────────────────────────────

def test_storage_includes_bind_mount():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "storage" in e["endpoint"])
    assert ep.get("schema_includes_bind_mount") is True


def test_storage_includes_named_volume():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "storage" in e["endpoint"])
    assert ep.get("schema_includes_named_volume") is True


# ── 8. deployment schema ──────────────────────────────────────────────────────

def test_deployment_restart_forbidden():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "deployment" in e["endpoint"])
    assert ep.get("restart_allowed") is False


def test_deployment_docker_compose_forbidden():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "deployment" in e["endpoint"])
    assert ep.get("docker_compose_allowed") is False


def test_deployment_server_apply_forbidden():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "deployment" in e["endpoint"])
    assert ep.get("server_apply_allowed") is False


# ── 9. task schema ────────────────────────────────────────────────────────────

def test_task_approval_token_raw_forbidden():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if e["endpoint"] == "GET /api/v1/app/tasks")
    assert ep.get("approval_token_raw_forbidden") is True


def test_task_execute_url_forbidden():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if e["endpoint"] == "GET /api/v1/app/tasks")
    assert ep.get("execute_url_forbidden") is True


def test_task_approval_token_boolean_only():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if e["endpoint"] == "GET /api/v1/app/tasks")
    assert ep.get("approval_token_present_boolean_only") is True


# ── 10. audit logs redaction ──────────────────────────────────────────────────

def test_audit_logs_redaction_required():
    ep = next(e for e in m.ENDPOINT_CONTRACT_MATRIX if "logs/audit" in e["endpoint"])
    assert ep.get("redaction_required") is True


# ── 11. priority matrix ───────────────────────────────────────────────────────

def test_priority_matrix_exists():
    assert len(m.PRIORITY_MATRIX) >= 3


def test_priority_1_includes_health():
    p1 = m.PRIORITY_MATRIX[1]["endpoints"]
    assert "GET /api/v1/app/health/summary" in p1


def test_priority_1_includes_providers():
    p1 = m.PRIORITY_MATRIX[1]["endpoints"]
    assert "GET /api/v1/app/providers" in p1


def test_priority_1_includes_storage():
    p1 = m.PRIORITY_MATRIX[1]["endpoints"]
    assert "GET /api/v1/app/storage/status" in p1


# ── 12. 이전 공정 회귀 ────────────────────────────────────────────────────────

def test_no_conflict_with_readonly_status_cards():
    import tools.audits.app.audit_app_ui_readonly_backend_status_cards as a
    report = a.run_audit()
    assert report.verdict in (a.VERDICT_READY, a.VERDICT_WARN)


def test_no_conflict_with_api_wiring():
    import tools.audits.app.audit_app_ui_shell_readonly_api_wiring as a
    report = a.run_audit()
    assert report.verdict in (a.VERDICT_READY, a.VERDICT_WARN)


def test_no_conflict_with_mvp_design():
    import tools.audits.app.audit_app_foundation_mvp_design as a
    report = a.run_audit()
    assert report.verdict in (a.VERDICT_READY, a.VERDICT_WARN)


# ── 13. audit verdict ─────────────────────────────────────────────────────────

def test_audit_verdict_ready_or_warn():
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN), \
        f"verdict={report.verdict}"
