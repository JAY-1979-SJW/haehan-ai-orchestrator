"""
Phase 1-J2 테스트: SAME_CONTRACT Response Schema Freeze
tests/test_5050_phase1j2_same_contract_response_schema_freeze_20260517.py

read-only / schema freeze 공정. 실제 비활성화 없음.
"""
import importlib.util
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _load_module(name, rel_path):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_phase1j2",
        "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def freeze_matrix(audit_mod):
    return audit_mod.FREEZE_MATRIX


@pytest.fixture(scope="module")
def caller_inv(audit_mod):
    return audit_mod.CALLER_INVENTORY


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1. import ────────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


# ── 2~4. matrix 기본 ─────────────────────────────────────────────────────────

def test_02_freeze_matrix_has_two_rows(freeze_matrix):
    assert len(freeze_matrix) == 2


def test_03_get_inbox_row_exists(freeze_matrix):
    assert any(r["legacy_path"] == "/api/v1/inbox" for r in freeze_matrix)


def test_04_post_tasks_row_exists(freeze_matrix):
    assert any(r["legacy_path"] == "/api/v1/tasks" for r in freeze_matrix)


# ── 5~9. overlap_class / disable / schema_frozen ────────────────────────────

def test_05_all_rows_same_contract(freeze_matrix):
    for row in freeze_matrix:
        assert row["overlap_class"] == "SAME_CONTRACT"


def test_06_disable_candidate_true(freeze_matrix):
    for row in freeze_matrix:
        assert row["disable_candidate"] is True


def test_07_disable_allowed_now_false(freeze_matrix):
    for row in freeze_matrix:
        assert row["disable_allowed_now"] is False


def test_08_request_schema_frozen_true(freeze_matrix):
    for row in freeze_matrix:
        assert row["request_schema_frozen"] is True


def test_09_response_schema_frozen_true(freeze_matrix):
    for row in freeze_matrix:
        assert row["response_schema_frozen"] is True


# ── 10~12. GET inbox 스키마 ──────────────────────────────────────────────────

def test_10_inbox_body_required_false(freeze_matrix):
    inbox = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/inbox")
    assert inbox["request_schema"]["body_required"] is False


def test_11_inbox_side_effect_read_only(freeze_matrix):
    inbox = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/inbox")
    assert inbox["side_effect_classification"] == "READ_ONLY_EXPECTED"


def test_12_inbox_response_schema_list(freeze_matrix):
    inbox = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/inbox")
    assert inbox["response_schema"]["top_level_type"] == "list"
    assert "item_schema" in inbox["response_schema"]


# ── 13~16. POST tasks 스키마 ─────────────────────────────────────────────────

def test_13_tasks_side_effect_write_possible(freeze_matrix):
    tasks = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert tasks["side_effect_classification"] == "WRITE_POSSIBLE"


def test_14_tasks_disable_allowed_now_false(freeze_matrix):
    tasks = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert tasks["disable_allowed_now"] is False


def test_15_tasks_response_schema_has_required_keys(freeze_matrix):
    tasks = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/tasks")
    resp = tasks["response_schema"]
    for key in ["task_id", "risk_level", "allowed", "requires_approval", "status"]:
        assert key in resp["required_keys"]


def test_16_tasks_request_schema_has_required_keys(freeze_matrix):
    tasks = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/tasks")
    req = tasks["request_schema"]
    for key in ["task_id", "source", "action_type", "target", "description"]:
        assert key in req["required_keys"]


# ── 17~20. status_code / error / auth contract ───────────────────────────────

def test_17_status_code_contract_exists(freeze_matrix):
    for row in freeze_matrix:
        assert row.get("status_code_contract")
        assert "success" in row["status_code_contract"]


def test_18_error_schema_contract_exists(freeze_matrix):
    for row in freeze_matrix:
        assert row.get("error_schema_contract")


def test_19_auth_contract_exists(freeze_matrix):
    for row in freeze_matrix:
        assert row.get("auth_contract")


def test_20_tasks_auth_required(freeze_matrix):
    tasks = next(r for r in freeze_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert tasks["auth_contract"]["required"] is True
    assert "roles" in tasks["auth_contract"]


# ── 21~26. caller inventory ──────────────────────────────────────────────────

def test_21_caller_inventory_status_exists(freeze_matrix):
    for row in freeze_matrix:
        assert row.get("caller_inventory_status")


def test_22_real_frontend_callers_exist(caller_inv):
    assert len(caller_inv.get("real_frontend_callers", [])) >= 1


def test_23_admin_web_external_tasks_classified(caller_inv):
    fe = caller_inv.get("real_frontend_callers", [])
    assert any("external-tasks" in c or "admin-web" in c for c in fe)


def test_24_real_backend_callers_exist(caller_inv):
    assert len(caller_inv.get("real_backend_callers", [])) >= 1


def test_25_backend_compat_callers_separated(caller_inv):
    compat = caller_inv.get("backend_compat_callers", [])
    assert len(compat) >= 1


def test_26_test_callers_separated(caller_inv):
    assert len(caller_inv.get("test_callers", [])) >= 1


def test_27_audit_smoke_callers_separated(caller_inv):
    assert len(caller_inv.get("audit_smoke_callers", [])) >= 1


def test_28_unknown_callers_with_reason(caller_inv):
    unknown = caller_inv.get("unknown_callers", [])
    if unknown:
        assert caller_inv.get("unknown_warning_reason"), \
            "unknown_callers present but unknown_warning_reason missing"


# ── 29~30. required_before_disable / rollback ────────────────────────────────

def test_29_required_before_disable_both_rows(freeze_matrix):
    for row in freeze_matrix:
        assert len(row.get("required_before_disable", [])) >= 1


def test_30_rollback_plan_both_rows(freeze_matrix):
    for row in freeze_matrix:
        assert row.get("rollback_plan")


# ── 31~34. 제외 대상 ─────────────────────────────────────────────────────────

def test_31_execute_not_in_matrix(freeze_matrix):
    assert not any("/execute" in r["legacy_path"] for r in freeze_matrix)


def test_32_webhook_not_in_matrix(freeze_matrix):
    assert not any("webhook" in r["legacy_path"] for r in freeze_matrix)


def test_33_dashboard_not_in_matrix(freeze_matrix):
    assert not any("dashboard" in r["legacy_path"] for r in freeze_matrix)


def test_34_adapter_routes_not_in_matrix(freeze_matrix):
    adapter_paths = [
        "/api/v1/inbox/email/fetch",
        "/api/v1/tasks/{task_id}/approve",
        "/api/v1/tasks/{task_id}/reject",
    ]
    matrix_paths = [r["legacy_path"] for r in freeze_matrix]
    for ap in adapter_paths:
        assert ap not in matrix_paths


# ── 35~40. safety boundary ───────────────────────────────────────────────────

def test_35_no_route_disable(router_content):
    assert "PHASE_1J2" not in router_content


def test_36_router_py_no_additional_modification(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_37_no_5050_route_deleted():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_38_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_39_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_40_no_secret_env_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py"
    ).read_text(encoding="utf-8", errors="ignore")
    for bad in ["os.environ[", "os.getenv(", "print(token", "print(cookie", "import requests", "import httpx"]:
        assert bad not in content


# ── 41. global constants ─────────────────────────────────────────────────────

def test_41_schema_freeze_only_true(audit_mod):
    assert audit_mod.SCHEMA_FREEZE_ONLY is True


# ── 42~44. audit verdict ─────────────────────────────────────────────────────

def test_42_audit_verdict_ready_or_warn(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J2_SAME_CONTRACT_RESPONSE_SCHEMA_FREEZE_READY",
        "SCHEMA_FREEZE_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_43_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_44_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


# ── 45~48. 이전 Phase 회귀 충돌 없음 ─────────────────────────────────────────

def test_45_phase1j_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").exists()


def test_46_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_47_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_48_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()
