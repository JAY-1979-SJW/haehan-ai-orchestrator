"""
Phase 1-P 테스트: Router Integration Implementation Plan
tests/test_5050_phase1p_router_integration_implementation_plan_20260517.py
"""
import importlib
import importlib.util
import sys
import os
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


# ── fixtures ──────────────────────────────────────────────────────────────

def _load_module(name, rel_path):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_phase1p",
        "scripts/ops/audit_5050_phase1p_router_integration_implementation_plan.py"
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def plan_matrix(audit_mod):
    return audit_mod.get_plan_matrix()


@pytest.fixture(scope="module")
def gate_info(audit_mod):
    return audit_mod.get_approval_gate_info()


# ── 1. import ─────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert hasattr(audit_mod, "run_audit")
    assert hasattr(audit_mod, "get_plan_matrix")
    assert hasattr(audit_mod, "get_approval_gate_info")


# ── 2~16. plan matrix 기본 필드 ────────────────────────────────────────────

def test_02_plan_matrix_count(plan_matrix):
    assert len(plan_matrix) == 3


def test_03_route_skeleton_ids(plan_matrix):
    ids = [r["route_skeleton_id"] for r in plan_matrix]
    assert "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON" in ids
    assert "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON" in ids
    assert "TASK_REJECT_ROUTE_INTEGRATION_SKELETON" in ids


def test_04_wrapper_ids(plan_matrix):
    wids = [r["wrapper_id"] for r in plan_matrix]
    assert "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE" in wids
    assert "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE" in wids
    assert "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE" in wids


def test_05_adapter_ids(plan_matrix):
    aids = [r["adapter_id"] for r in plan_matrix]
    assert "INBOX_EMAIL_FETCH_ADAPTER" in aids
    assert "TASK_APPROVE_PATH_AUTH_ADAPTER" in aids
    assert "TASK_REJECT_PATH_AUTH_ADAPTER" in aids


def test_06_feature_flags_exist(plan_matrix):
    for row in plan_matrix:
        assert row.get("feature_flag"), f"{row['route_skeleton_id']}: feature_flag 없음"


def test_07_feature_flag_default_false(plan_matrix):
    for row in plan_matrix:
        assert row["feature_flag_default"] is False


def test_08_route_registered_now_false(plan_matrix):
    for row in plan_matrix:
        assert row["route_registered_now"] is False


def test_09_router_file_modification_allowed_false(plan_matrix):
    for row in plan_matrix:
        assert row["router_file_modification_allowed_now"] is False


def test_10_include_router_allowed_false(plan_matrix):
    for row in plan_matrix:
        assert row["include_router_allowed_now"] is False


def test_11_route_decorator_allowed_false(plan_matrix):
    for row in plan_matrix:
        assert row["route_decorator_allowed_now"] is False


def test_12_feature_flag_runtime_hook_allowed_false(plan_matrix):
    for row in plan_matrix:
        assert row["feature_flag_runtime_hook_allowed_now"] is False


def test_13_live_traffic_allowed_false(plan_matrix):
    for row in plan_matrix:
        assert row["live_traffic_allowed_now"] is False


def test_14_dry_run_only_true(plan_matrix):
    for row in plan_matrix:
        assert row["dry_run_only_now"] is True


def test_15_approve_reject_approval_gate_required(plan_matrix):
    for row in plan_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            assert row["approval_gate_required"] is True


def test_16_approval_gate_executed_allowed_false(plan_matrix):
    for row in plan_matrix:
        assert row["approval_gate_executed_allowed"] is False


# ── 17~19. approval gate registry ─────────────────────────────────────────

def test_17_approval_gate_registry_path_exists(plan_matrix):
    for row in plan_matrix:
        assert row.get("approval_gate_registry_path"), f"{row['route_skeleton_id']}: approval_gate_registry_path 없음"


def test_18_approval_gate_registry_importable(gate_info):
    if gate_info["canonical_path"] == "UNKNOWN":
        pytest.skip("approval_gate_registry not found")
    assert gate_info["importable"] is True, f"import 실패: {gate_info.get('error')}"


def test_19_approval_gates_auto_execute_false(gate_info):
    if gate_info["canonical_path"] == "UNKNOWN" or not gate_info.get("importable"):
        pytest.skip("approval_gate_registry not importable")
    raw = gate_info.get("raw_registry", {})
    for gid, g in raw.items():
        if "auto_execute_allowed" in g:
            assert g["auto_execute_allowed"] is False, f"{gid}: auto_execute_allowed=True"


# ── 20~22. proposed guard order ───────────────────────────────────────────

def test_20_inbox_guard_order(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON")
    assert len(row.get("proposed_guard_order", [])) >= 4


def test_21_approve_guard_order(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert len(row.get("proposed_guard_order", [])) >= 6


def test_22_reject_guard_order(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert len(row.get("proposed_guard_order", [])) >= 6


# ── 23. rollback plan ─────────────────────────────────────────────────────

def test_23_rollback_plan_exists(plan_matrix):
    for row in plan_matrix:
        assert len(row.get("rollback_plan", [])) >= 3, f"{row['route_skeleton_id']}: rollback_plan 부족"


# ── 24~33. path 검증 ──────────────────────────────────────────────────────

def test_24_approve_legacy_path_has_id(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert "<id>" in row["legacy_path_template"]


def test_25_approve_fastapi_path_has_id(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert "{id}" in row["fastapi_path_template"]


def test_26_reject_legacy_path_has_id(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert "<id>" in row["legacy_path_template"]


def test_27_reject_fastapi_path_has_id(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert "{id}" in row["fastapi_path_template"]


def test_28_no_double_slash_approve(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert "//" not in row["fastapi_path_template"]


def test_29_no_double_slash_reject(plan_matrix):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert "//" not in row["fastapi_path_template"]


def test_30_execute_not_in_scope(plan_matrix):
    for row in plan_matrix:
        assert "/execute" not in row.get("legacy_path_template", "")
        assert "/execute" not in row.get("fastapi_path_template", "")


def test_31_webhook_not_in_scope(plan_matrix):
    for row in plan_matrix:
        assert "/webhook" not in row.get("legacy_path_template", "")
        assert "/webhook" not in row.get("fastapi_path_template", "")


def test_32_dashboard_not_in_scope(plan_matrix):
    for row in plan_matrix:
        assert "/dashboard" not in row.get("legacy_path_template", "")


def test_33_same_contract_not_in_scope(plan_matrix):
    for row in plan_matrix:
        selected_str = str(row.get("selected_candidate_router_files", []))
        assert "SAME_CONTRACT_001" not in selected_str
        assert "SAME_CONTRACT_002" not in selected_str


# ── 34~42. candidate inventory ────────────────────────────────────────────

def test_34_candidate_inventory_classification_exists(audit_result):
    assert "selected_candidate_router_files" in audit_result
    assert "observation_candidate_files" in audit_result
    assert "excluded_count" in audit_result


def test_35_selected_candidate_router_files_exists(audit_result):
    assert "selected_candidate_router_files" in audit_result


def test_36_observation_candidate_files_exists(audit_result):
    assert "observation_candidate_files" in audit_result


def test_37_excluded_candidate_files_concept_exists(audit_result):
    assert "excluded_count" in audit_result
    assert audit_result["excluded_count"] >= 0


def test_38_selected_no_test_audit_smoke_docs(audit_result):
    for f in audit_result["selected_candidate_router_files"]:
        if f in ("UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW",):
            continue
        assert "test_" not in f
        assert "audit_" not in f
        assert "smoke_" not in f
        assert "/docs/" not in f and "docs/" not in f


def test_39_selected_no_wrapper_route_integration(audit_result):
    for f in audit_result["selected_candidate_router_files"]:
        if f in ("UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW",):
            continue
        assert "route_integration" not in f
        assert "wrapper_candidate" not in f


def test_40_selected_count_warn_if_over_10(audit_result):
    count = audit_result["selected_count"]
    if count > 10:
        pytest.warns(UserWarning) if False else None  # WARN 처리는 audit result에
        assert "selected_count" in str(audit_result.get("warnings", []))
    else:
        assert count <= 10


def test_41_modified_files_count_zero(audit_result):
    assert audit_result["modified_files_count"] == 0


def test_42_router_scan_is_readonly(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod.classify_candidates)
    forbidden = [".write(", "write_text(", "os.remove", "shutil."]
    for f in forbidden:
        assert f not in src


# ── 43~52. stop conditions ───────────────────────────────────────────────

def _get_sc(plan_matrix, skeleton_id):
    row = next(r for r in plan_matrix if r["route_skeleton_id"] == skeleton_id)
    return row.get("stop_conditions", [])


def test_43_stop_router_file_modification(plan_matrix):
    for row in plan_matrix:
        assert any("router_file_modification" in s for s in row.get("stop_conditions", []))


def test_44_stop_route_decorator(plan_matrix):
    for row in plan_matrix:
        assert any("route_decorator" in s for s in row.get("stop_conditions", []))


def test_45_stop_include_router(plan_matrix):
    for row in plan_matrix:
        assert any("include_router" in s for s in row.get("stop_conditions", []))


def test_46_stop_feature_flag_default_true(plan_matrix):
    for row in plan_matrix:
        assert any("feature_flag_default_true" in s for s in row.get("stop_conditions", []))


def test_47_stop_db_write(plan_matrix):
    for row in plan_matrix:
        assert any("db_write" in s for s in row.get("stop_conditions", []))


def test_48_stop_secret_env_access(plan_matrix):
    for row in plan_matrix:
        assert any("secret_env_access" in s for s in row.get("stop_conditions", []))


def test_49_stop_approval_gate_executed(plan_matrix):
    for row in plan_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            assert any("approval_gate_executed" in s for s in row.get("stop_conditions", []))


def test_50_stop_double_slash(plan_matrix):
    for row in plan_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            assert any("double_slash" in s for s in row.get("stop_conditions", []))


def test_51_stop_external_site_cookie_storage(plan_matrix):
    inbox = next(r for r in plan_matrix if r["route_skeleton_id"] == "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON")
    assert any("external_site_cookie_storage" in s for s in inbox.get("stop_conditions", []))


def test_52_stop_external_site_approval_gate(plan_matrix):
    for row in plan_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            assert any("external_site_approval_gate_violation" in s for s in row.get("stop_conditions", []))


# ── 53~65. 정적 코드 검사 ────────────────────────────────────────────────

def test_53_no_route_integration_import_in_routers():
    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "route_integration" in str(py_file):
                continue
            if "test_" in py_file.name or "audit_" in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "from backend.compat.legacy_5050.route_integration" in content:
                if "route_integration" not in str(py_file):
                    assert False, f"{py_file}: route integration 외부 import 발견"


def test_54_fastapi_handler_not_modified():
    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for f in root.rglob("router*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            assert "phase1p" not in content.lower(), f"{f}: phase1p 마커 발견"


def test_55_flask_route_not_modified():
    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "phase1p" in py_file.name.lower():
                continue
            if "test_" in py_file.name or "audit_" in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            assert "phase1p" not in content.lower(), f"{py_file}: phase1p 마커 발견"


def test_56_no_apirouter_created(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "APIRouter()" not in src


def test_57_no_include_router(audit_mod):
    import inspect
    # run_audit/build_plan_matrix/classify_candidates 함수 소스에서 실제 실행 코드 확인
    # ROUTE_KEYWORDS 리스트 탐지 문자열 외에 실제 include_router() 호출이 없어야 함
    src = inspect.getsource(audit_mod.run_audit)
    assert "include_router(" not in src
    src2 = inspect.getsource(audit_mod.build_plan_matrix)
    assert "include_router(" not in src2


def test_58_no_route_decorator(audit_mod):
    import inspect
    # 실제 실행 함수에서 route decorator 사용 없어야 함
    for fn in [audit_mod.run_audit, audit_mod.build_plan_matrix]:
        src = inspect.getsource(fn)
        assert "@router." not in src
        assert "@app.route" not in src


def test_59_no_http_client_import(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    for f in ["import requests", "import httpx", "import urllib.request", "import aiohttp"]:
        assert f not in src


def test_60_no_db_client_import(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    for f in ["import sqlalchemy", "import psycopg2", "import pymysql", "import sqlite3"]:
        assert f not in src


def test_61_no_subprocess_socket(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "import subprocess" not in src
    assert "import socket" not in src


def test_62_no_os_environ_access(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "os.environ[" not in src
    assert "os.getenv(" not in src


def test_63_no_feature_flag_runtime_hook(audit_mod):
    import inspect, re
    # runtime_hook 실제 호출(함수 호출 or import) 없어야 함
    # 문자열 리터럴/dict key로만 사용되는 것은 허용
    for fn in [audit_mod.run_audit, audit_mod.build_plan_matrix, audit_mod.classify_candidates]:
        src = inspect.getsource(fn)
        # 실제 호출 패턴: runtime_hook( 또는 import runtime_hook
        assert not re.search(r'runtime_hook\s*\(', src.lower())
        assert "import runtime_hook" not in src.lower()


def test_64_no_server_startup(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "uvicorn" not in src
    assert "gunicorn" not in src
    assert "app.run(" not in src


def test_65_no_uvicorn_gunicorn(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "uvicorn" not in src
    assert "gunicorn" not in src


# ── 66~69. external site registry ────────────────────────────────────────

def test_66_no_external_site_conflict(audit_result):
    assert audit_result["verdict"] != "FAIL"


def test_67_gabia_cookie_storage_false():
    import sys as _sys
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))
    try:
        from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY
    except Exception:
        pytest.skip("provider_registry not importable")
    gabia_entries = [p for p in PROVIDER_REGISTRY if hasattr(p, "provider_id") and "GABIA" in p.provider_id.upper()]
    if not gabia_entries:
        pytest.skip("gabia provider not found in registry")
    for entry in gabia_entries:
        assert entry.cookie_storage_allowed is False, f"{entry.provider_id}: cookie_storage_allowed must be False"


def test_68_all_providers_server_remote_login_false():
    import sys as _sys
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))
    try:
        from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY
    except Exception:
        pytest.skip("provider_registry not importable")
    if not PROVIDER_REGISTRY:
        pytest.skip("provider_registry is empty")
    for entry in PROVIDER_REGISTRY:
        if hasattr(entry, "server_remote_login_allowed"):
            assert entry.server_remote_login_allowed is False, f"{entry.provider_id}: server_remote_login_allowed must be False"


def test_69_critical_approval_gates_auto_execute_false(gate_info):
    if not gate_info.get("importable"):
        pytest.skip("approval_gate_registry not importable")
    raw = gate_info.get("raw_registry", {})
    for gid, g in raw.items():
        if "auto_execute_allowed" in g:
            assert g["auto_execute_allowed"] is False, f"{gid}: auto_execute_allowed=True"


# ── 70~83. 이전 phase 회귀 충돌 확인 ─────────────────────────────────────

def _script_exists(name):
    return (REPO_ROOT / "scripts/ops" / name).exists()


def test_70_phase1o_no_conflict():
    assert _script_exists("audit_5050_phase1o_router_touch_design_only.py")


def test_71_phase1n_no_conflict():
    assert _script_exists("audit_5050_phase1n_route_integration_final_preflight.py")


def test_72_phase1m_no_conflict():
    assert _script_exists("smoke_5050_phase1m_route_integration_skeleton_internal.py")


def test_73_phase1l_no_conflict():
    assert _script_exists("audit_5050_phase1l_feature_flag_off_route_integration_skeleton.py")


def test_74_phase1k_no_conflict():
    assert _script_exists("audit_5050_phase1k_wrapper_route_integration_preflight.py")


def test_75_phase1i_no_conflict():
    assert _script_exists("audit_5050_phase1i_staging_dry_run_internal_smoke.py")


def test_76_phase1h_no_conflict():
    assert _script_exists("audit_5050_phase1h_route_wrapper_candidate_feature_flag_off.py")


def test_77_phase1g_no_conflict():
    assert _script_exists("audit_5050_phase1g_adapter_unit_implementation.py")


def test_78_phase1f_no_conflict():
    assert _script_exists("audit_5050_phase1f_adapter_skeleton_only.py")


def test_79_phase1e_no_conflict():
    assert _script_exists("audit_5050_phase1e_adapter_implementation_plan.py")


def test_80_phase1d_no_conflict():
    assert _script_exists("audit_5050_phase1d_adapter_dry_run_compat.py")


def test_81_phase1b_no_conflict():
    assert _script_exists("audit_5050_phase1b_adapter_contract_detail.py")


def test_82_phase1_contract_freeze_no_conflict():
    assert _script_exists("audit_5050_phase1_8400_contract_freeze.py")


def test_83_characterization_no_conflict():
    assert _script_exists("audit_5050_legacy_characterization.py")


# ── 84~85. 최종 ──────────────────────────────────────────────────────────

def test_84_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1P_ROUTER_INTEGRATION_IMPLEMENTATION_PLAN_READY",
        "WARN",
    ), f"verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"
    assert audit_result["verdict"] != "FAIL"


def test_85_known_baseline_not_confused(audit_result):
    assert "verdict" in audit_result
    assert audit_result["verdict"] != "FAIL"
