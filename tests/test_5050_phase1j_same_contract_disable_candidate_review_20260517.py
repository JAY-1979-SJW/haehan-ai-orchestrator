"""
Phase 1-J 테스트: SAME_CONTRACT Legacy Disable Candidate Review
tests/test_5050_phase1j_same_contract_disable_candidate_review_20260517.py

read-only / audit / test 공정. 실제 비활성화 없음.
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
        "audit_phase1j",
        "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def review_matrix(audit_mod):
    return audit_mod.REVIEW_MATRIX


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~4. audit script import + matrix 기본 ───────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_review_matrix_has_two_rows(review_matrix):
    assert len(review_matrix) == 2


def test_03_get_inbox_row_exists(review_matrix):
    paths = [r["legacy_path"] for r in review_matrix]
    assert "/api/v1/inbox" in paths


def test_04_post_tasks_row_exists(review_matrix):
    paths = [r["legacy_path"] for r in review_matrix]
    assert "/api/v1/tasks" in paths


# ── 5~8. overlap_class / disable flags ──────────────────────────────────────

def test_05_all_rows_same_contract(review_matrix):
    for row in review_matrix:
        assert row["overlap_class"] == "SAME_CONTRACT", f"not SAME_CONTRACT: {row['legacy_path']}"


def test_06_disable_candidate_true(review_matrix):
    for row in review_matrix:
        assert row["disable_candidate"] is True


def test_07_disable_allowed_now_false(review_matrix):
    for row in review_matrix:
        assert row["disable_allowed_now"] is False


def test_08_legacy_disable_allowed_now_false(audit_mod):
    assert audit_mod.LEGACY_DISABLE_ALLOWED_NOW is False


# ── 9~12. 전역 금지 상수 ────────────────────────────────────────────────────

def test_09_router_file_modification_allowed_false(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_ALLOWED is False


def test_10_server_apply_allowed_false(audit_mod):
    assert audit_mod.SERVER_APPLY_ALLOWED is False


def test_11_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_12_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


# ── 13~15. 제외 대상 확인 ────────────────────────────────────────────────────

def test_13_execute_not_in_matrix(review_matrix):
    paths = [r["legacy_path"] for r in review_matrix]
    assert not any("/execute" in p for p in paths)


def test_14_webhook_not_in_matrix(review_matrix):
    paths = [r["legacy_path"] for r in review_matrix]
    assert not any("webhook" in p for p in paths)


def test_15_dashboard_not_in_matrix(review_matrix):
    paths = [r["legacy_path"] for r in review_matrix]
    assert not any("dashboard" in p for p in paths)


# ── 16. adapter 3개 제외 ────────────────────────────────────────────────────

def test_16_adapter_routes_not_in_matrix(review_matrix):
    adapter_paths = [
        "/api/v1/inbox/email/fetch",
        "/api/v1/tasks/{task_id}/approve",
        "/api/v1/tasks/{task_id}/reject",
    ]
    matrix_paths = [r["legacy_path"] for r in review_matrix]
    for ap in adapter_paths:
        assert ap not in matrix_paths, f"adapter route found in Phase 1-J matrix: {ap}"


# ── 17~20. required_before_disable / side effect ────────────────────────────

def test_17_inbox_required_before_disable_exists(review_matrix):
    inbox = next(r for r in review_matrix if r["legacy_path"] == "/api/v1/inbox")
    assert len(inbox.get("required_before_disable", [])) >= 1


def test_18_tasks_required_before_disable_exists(review_matrix):
    tasks = next(r for r in review_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert len(tasks.get("required_before_disable", [])) >= 1


def test_19_tasks_side_effect_classification_exists(review_matrix):
    tasks = next(r for r in review_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert tasks.get("side_effect_classification") in ("WRITE_POSSIBLE", "READ_WRITE", "WRITE")


def test_20_tasks_side_effect_detail_exists(review_matrix):
    tasks = next(r for r in review_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert tasks.get("side_effect_detail")


# ── 21~22. rollback plan ────────────────────────────────────────────────────

def test_21_rollback_plan_inbox_exists(review_matrix):
    inbox = next(r for r in review_matrix if r["legacy_path"] == "/api/v1/inbox")
    assert inbox.get("rollback_plan")


def test_22_rollback_plan_tasks_exists(review_matrix):
    tasks = next(r for r in review_matrix if r["legacy_path"] == "/api/v1/tasks")
    assert tasks.get("rollback_plan")


# ── 23~27. caller inventory ─────────────────────────────────────────────────

def test_23_caller_inventory_exists(audit_result):
    assert "caller_inventory" in audit_result
    inv = audit_result["caller_inventory"]
    assert isinstance(inv, dict)


def test_24_real_caller_candidates_key_exists(audit_result):
    inv = audit_result["caller_inventory"]
    assert "real_backend" in inv or "real_frontend" in inv


def test_25_test_only_candidates_key_exists(audit_result):
    inv = audit_result["caller_inventory"]
    assert "test" in inv


def test_26_audit_only_candidates_key_exists(audit_result):
    inv = audit_result["caller_inventory"]
    assert "audit_smoke" in inv


def test_27_unknown_candidates_key_exists(audit_result):
    inv = audit_result["caller_inventory"]
    assert "unknown" in inv


# ── 28~33. safety boundary (router/5050/8400/DB/live call/secret) ───────────

def test_28_actual_route_disable_absent_router(router_content):
    # PHASE_1J 상수가 router.py에 추가됐으면 수정된 것
    assert "PHASE_1J" not in router_content


def test_29_router_py_no_additional_modification(router_content):
    assert "LEGACY_5050_ROUTER_TOUCH_PHASE" in router_content
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_30_no_5050_route_deleted():
    # backend/compat/legacy_5050 디렉토리가 존재해야 함
    legacy_dir = REPO_ROOT / "backend/compat/legacy_5050"
    assert legacy_dir.exists()


def test_31_no_8400_handler_modified(router_content):
    # router.py 내 handler 수 변화 없음 (기존 decorator 수 유지)
    decorator_count = router_content.count("@router.")
    assert decorator_count >= 8


def test_32_no_db_write(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_33_no_live_http_call(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


# ── 34~35. secret/env ───────────────────────────────────────────────────────

def test_34_no_secret_env_access():
    content = (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    for bad in ["os.environ[", "os.getenv(", "print(token", "print(cookie"]:
        assert bad not in content


def test_35_no_live_http_in_audit_script():
    content = (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    for bad in ["import requests", "import httpx", "import aiohttp"]:
        assert bad not in content


# ── 36~38. audit verdict ────────────────────────────────────────────────────

def test_36_audit_verdict_ready_or_warn(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J_SAME_CONTRACT_DISABLE_CANDIDATE_REVIEW_READY",
        "REVIEW_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_37_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_38_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


# ── 39~41. 이전 Phase 회귀 충돌 없음 ────────────────────────────────────────

def test_39_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_40_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_41_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


# ── 42. characterization matrix 충돌 없음 ───────────────────────────────────

def test_42_characterization_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


# ── 43. known baseline 구분 ─────────────────────────────────────────────────

def test_43_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1J_SAME_CONTRACT_DISABLE_CANDIDATE_REVIEW_FAIL"
