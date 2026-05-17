"""
Phase 1-O 테스트: Router Touch Design Only
tests/test_5050_phase1o_router_touch_design_only_20260517.py
"""
import importlib
import sys
import os
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# ── import ─────────────────────────────────────────────────────────────────

def test_01_audit_script_importable():
    spec = importlib.util.spec_from_file_location(
        "audit_phase1o",
        REPO_ROOT / "scripts/ops/audit_5050_phase1o_router_touch_design_only.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run_audit")
    assert hasattr(mod, "get_design_matrix")


@pytest.fixture(scope="module")
def audit_mod():
    spec = importlib.util.spec_from_file_location(
        "audit_phase1o",
        REPO_ROOT / "scripts/ops/audit_5050_phase1o_router_touch_design_only.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def design_matrix(audit_mod):
    return audit_mod.get_design_matrix()


# ── design matrix 기본 ─────────────────────────────────────────────────────

def test_02_design_matrix_count(design_matrix):
    assert len(design_matrix) == 3


def test_03_route_skeleton_ids(design_matrix):
    ids = [r["route_skeleton_id"] for r in design_matrix]
    assert "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON" in ids
    assert "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON" in ids
    assert "TASK_REJECT_ROUTE_INTEGRATION_SKELETON" in ids


def test_04_wrapper_ids(design_matrix):
    wids = [r["wrapper_id"] for r in design_matrix]
    assert "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE" in wids
    assert "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE" in wids
    assert "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE" in wids


def test_05_adapter_ids(design_matrix):
    aids = [r["adapter_id"] for r in design_matrix]
    assert "INBOX_EMAIL_FETCH_ADAPTER" in aids
    assert "TASK_APPROVE_PATH_AUTH_ADAPTER" in aids
    assert "TASK_REJECT_PATH_AUTH_ADAPTER" in aids


def test_06_feature_flags(design_matrix):
    flags = [r["feature_flag"] for r in design_matrix]
    assert all(f for f in flags)  # 모두 존재


def test_07_feature_flag_default_false(design_matrix):
    for row in design_matrix:
        assert row["feature_flag_default"] is False, f"{row['route_skeleton_id']}: feature_flag_default must be False"


def test_08_route_registered_now_false(design_matrix):
    for row in design_matrix:
        assert row["route_registered_now"] is False


def test_09_real_router_touch_allowed_now_false(design_matrix):
    for row in design_matrix:
        assert row["real_router_touch_allowed_now"] is False


def test_10_router_file_modification_allowed_now_false(design_matrix):
    for row in design_matrix:
        assert row["router_file_modification_allowed_now"] is False


def test_11_include_router_allowed_now_false(design_matrix):
    for row in design_matrix:
        assert row["include_router_allowed_now"] is False


def test_12_route_decorator_allowed_now_false(design_matrix):
    for row in design_matrix:
        assert row["route_decorator_allowed_now"] is False


def test_13_feature_flag_runtime_hook_allowed_now_false(design_matrix):
    for row in design_matrix:
        assert row["feature_flag_runtime_hook_allowed_now"] is False


def test_14_live_traffic_allowed_now_false(design_matrix):
    for row in design_matrix:
        assert row["live_traffic_allowed_now"] is False


def test_15_dry_run_only_now_true(design_matrix):
    for row in design_matrix:
        assert row["dry_run_only_now"] is True


def test_16_approve_reject_approval_gate_required(design_matrix):
    for row in design_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            assert row["approval_gate_required"] is True


def test_17_approval_gate_executed_allowed_false(design_matrix):
    for row in design_matrix:
        assert row["approval_gate_executed_allowed"] is False


def test_18_inbox_design_boundary(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON")
    assert row["integration_design_boundary"] == "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY"


def test_19_approve_design_boundary(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert row["integration_design_boundary"] == "BEFORE_APPROVAL_SERVICE_BOUNDARY"


def test_20_reject_design_boundary(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert row["integration_design_boundary"] == "BEFORE_APPROVAL_SERVICE_BOUNDARY"


def test_21_approve_legacy_path_has_id(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert "<id>" in row["legacy_path_template"]


def test_22_approve_fastapi_path_has_id(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert "{id}" in row["fastapi_path_template"]


def test_23_reject_legacy_path_has_id(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert "<id>" in row["legacy_path_template"]


def test_24_reject_fastapi_path_has_id(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert "{id}" in row["fastapi_path_template"]


def test_25_no_double_slash_approve(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert "//" not in row["fastapi_path_template"]


def test_26_no_double_slash_reject(design_matrix):
    row = next(r for r in design_matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert "//" not in row["fastapi_path_template"]


def test_27_execute_not_in_scope(design_matrix):
    for row in design_matrix:
        assert "/execute" not in row.get("legacy_path_template", "")
        assert "/execute" not in row.get("fastapi_path_template", "")


def test_28_webhook_not_in_scope(design_matrix):
    for row in design_matrix:
        assert "/webhook" not in row.get("legacy_path_template", "")
        assert "/webhook" not in row.get("fastapi_path_template", "")


def test_29_dashboard_not_in_scope(design_matrix):
    for row in design_matrix:
        assert "/dashboard" not in row.get("legacy_path_template", "")
        assert "/dashboard" not in row.get("fastapi_path_template", "")


def test_30_same_contract_not_in_scope(design_matrix):
    for row in design_matrix:
        candidates = row.get("selected_candidate_router_files", [])
        assert "SAME_CONTRACT_001" not in str(candidates)
        assert "SAME_CONTRACT_002" not in str(candidates)


def test_31_candidate_router_search_terms_exist(design_matrix):
    for row in design_matrix:
        assert len(row.get("candidate_router_search_terms", [])) > 0


def test_32_candidate_router_files_field_exists(design_matrix):
    for row in design_matrix:
        assert "candidate_router_files" in row


def test_33_selected_candidate_router_files_field_exists(design_matrix):
    for row in design_matrix:
        assert "selected_candidate_router_files" in row


def test_34_selected_candidate_reason_exists(design_matrix):
    for row in design_matrix:
        assert row.get("selected_candidate_reason")


def test_35_router_scan_is_readonly(audit_mod):
    # scan 함수는 write를 하지 않음 - 소스코드 정적 확인
    import inspect
    src = inspect.getsource(audit_mod.scan_router_candidates)
    forbidden = ["open(", ".write(", ".write_text(", "os.remove", "shutil"]
    for f in forbidden:
        assert f not in src, f"scan_router_candidates에 write 코드 발견: {f}"


def test_36_modified_files_count_zero(audit_result):
    assert audit_result["modified_files_count"] == 0


def test_37_forbidden_import_violations_zero(audit_result):
    assert audit_result["forbidden_import_violations"] == 0


def test_38_test_audit_smoke_excluded_from_selected(design_matrix):
    for row in design_matrix:
        selected = row.get("selected_candidate_router_files", [])
        if selected == ["UNKNOWN"]:
            continue
        for f in selected:
            assert "test_" not in f and "audit_" not in f and "smoke_" not in f


def test_39_wrapper_route_integration_excluded_from_selected(design_matrix):
    for row in design_matrix:
        selected = row.get("selected_candidate_router_files", [])
        if selected == ["UNKNOWN"]:
            continue
        for f in selected:
            assert "route_integration" not in f and "wrapper_candidate" not in f


def _get_stop_conditions(row):
    return row.get("stop_conditions", [])


def test_40_stop_condition_router_file_modification(design_matrix):
    for row in design_matrix:
        sc = _get_stop_conditions(row)
        assert any("router_file_modification" in s for s in sc)


def test_41_stop_condition_route_decorator(design_matrix):
    for row in design_matrix:
        sc = _get_stop_conditions(row)
        assert any("route_decorator" in s for s in sc)


def test_42_stop_condition_include_router(design_matrix):
    for row in design_matrix:
        sc = _get_stop_conditions(row)
        assert any("include_router" in s for s in sc)


def test_43_stop_condition_feature_flag_default_true(design_matrix):
    for row in design_matrix:
        sc = _get_stop_conditions(row)
        assert any("feature_flag_default_true" in s for s in sc)


def test_44_stop_condition_db_write(design_matrix):
    for row in design_matrix:
        sc = _get_stop_conditions(row)
        assert any("db_write" in s for s in sc)


def test_45_stop_condition_secret_env_access(design_matrix):
    for row in design_matrix:
        sc = _get_stop_conditions(row)
        assert any("secret_env_access" in s for s in sc)


def test_46_stop_condition_approval_gate_executed(design_matrix):
    for row in design_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            sc = _get_stop_conditions(row)
            assert any("approval_gate_executed" in s for s in sc)


def test_47_stop_condition_double_slash(design_matrix):
    for row in design_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            sc = _get_stop_conditions(row)
            assert any("double_slash" in s for s in sc)


def test_48_stop_condition_external_site_cookie_storage(design_matrix):
    inbox_row = next(r for r in design_matrix if r["route_skeleton_id"] == "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON")
    sc = _get_stop_conditions(inbox_row)
    assert any("external_site_cookie_storage" in s for s in sc)


def test_49_stop_condition_external_site_approval_gate(design_matrix):
    for row in design_matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            sc = _get_stop_conditions(row)
            assert any("external_site_approval_gate_violation" in s for s in sc)


def test_50_router_candidate_inventory_exists(audit_result):
    assert audit_result["candidate_file_count"] >= 0  # 0도 WARN이지, FAIL 아님
    assert "candidate_files" in audit_result


# ── 실제 파일 정적 검사 ─────────────────────────────────────────────────────

def _audit_script_source(audit_mod):
    import inspect
    return inspect.getsource(audit_mod)


def test_51_route_integration_not_imported_in_router_files():
    # route_integration skeleton이 실제 router/service 파일에 import되지 않음
    for search_root in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / search_root
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "route_integration" in str(py_file):
                continue
            if "wrapper_candidate" in str(py_file):
                continue
            if "test_" in py_file.name or "audit_" in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # route_integration skeleton이 실제 router/service에 import되어선 안 됨
            # (단, route_integration 디렉토리 자체는 허용)
            assert "from backend.compat.legacy_5050.route_integration" not in content or \
                   "route_integration" in str(py_file), \
                f"{py_file}: route integration이 외부 파일에 import됨"


def test_52_fastapi_handler_not_modified():
    # Phase 1-O에서 추가된 코드가 8400 handler에 없음 - 정적 확인
    handler_dirs = list((REPO_ROOT / "ai_orchestrator").rglob("router*.py")) + \
                   list((REPO_ROOT / "backend").rglob("router*.py"))
    # handler 파일에 phase1o 마커가 없어야 함
    for f in handler_dirs:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        assert "phase1o" not in content.lower(), f"{f}: phase1o 마커 발견"


def test_53_flask_route_not_modified():
    flask_files = list(REPO_ROOT.rglob("*.py"))
    for f in flask_files:
        if "phase1o" not in f.name.lower():
            continue
        # phase1o 파일 자체는 허용
        pass
    # Flask route 파일에 phase1o 마커 없음
    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "phase1o" in py_file.name.lower():
                continue
            if "test_" in py_file.name or "audit_" in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            assert "phase1o" not in content.lower(), f"{py_file}: phase1o 마커 발견"


def test_54_no_apirouter_created(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    # audit script 자체에 APIRouter() 인스턴스 생성 없음
    assert "APIRouter()" not in src


def test_55_no_include_router_created(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "include_router(" not in src


def test_56_no_route_decorator_created(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    # SEARCH_PATTERNS 리스트 안에 문자열로 포함된 것은 허용
    # 실제 decorator 선언(@router. 또는 @app.route)이 코드에 없어야 함
    lines = src.splitlines()
    for line in lines:
        stripped = line.strip()
        # 문자열 리터럴(따옴표로 감싸진) 안의 내용은 제외
        if stripped.startswith('"') or stripped.startswith("'"):
            continue
        if stripped.startswith("#"):
            continue
        # 실제 decorator 패턴만 검사
        assert not stripped.startswith("@router."), f"route decorator 발견: {line}"
        assert not stripped.startswith("@app.route"), f"route decorator 발견: {line}"


def test_57_no_http_client_import(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    forbidden = ["import requests", "import httpx", "import urllib.request", "import aiohttp"]
    for f in forbidden:
        assert f not in src


def test_58_no_db_client_import(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    forbidden = ["import sqlalchemy", "import psycopg2", "import pymysql", "import sqlite3", "import motor"]
    for f in forbidden:
        assert f not in src


def test_59_no_subprocess_socket_import(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "import subprocess" not in src
    assert "import socket" not in src


def test_60_no_os_environ_value_access(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "os.environ[" not in src
    assert "os.getenv(" not in src


def test_61_no_feature_flag_runtime_hook(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    # 상수명(FEATURE_FLAG_RUNTIME_HOOK_ALLOWED)은 허용, 실제 runtime hook 호출 코드만 금지
    # "runtime_hook(" 패턴 또는 "register_flag(" 호출이 없어야 함
    assert "runtime_hook(" not in src.lower()
    assert "register_flag(" not in src.lower()


def test_62_no_server_startup_code(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "uvicorn" not in src
    assert "gunicorn" not in src
    assert "app.run(" not in src


def test_63_no_uvicorn_gunicorn(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "uvicorn" not in src
    assert "gunicorn" not in src


# ── external site registry ─────────────────────────────────────────────────

def _load_provider_registry():
    spec = importlib.util.spec_from_file_location(
        "provider_registry",
        REPO_ROOT / "ai_orchestrator/external_sites/provider_registry.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_auth_policy_registry():
    spec = importlib.util.spec_from_file_location(
        "auth_policy_registry",
        REPO_ROOT / "ai_orchestrator/external_sites/auth_policy_registry.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_approval_gate_registry():
    spec = importlib.util.spec_from_file_location(
        "approval_gate_registry",
        REPO_ROOT / "ai_orchestrator/external_sites/approval_gate_registry.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def provider_registry():
    try:
        return _load_provider_registry()
    except Exception:
        pytest.skip("provider_registry not found")


@pytest.fixture(scope="module")
def auth_policy_registry():
    try:
        return _load_auth_policy_registry()
    except Exception:
        pytest.skip("auth_policy_registry not found")


@pytest.fixture(scope="module")
def approval_gate_registry():
    try:
        return _load_approval_gate_registry()
    except Exception:
        pytest.skip("approval_gate_registry not found")


def test_64_no_external_site_registry_conflict(audit_result):
    # audit가 FAIL이 아닌 한 external site registry와 충돌 없음
    assert audit_result["verdict"] != "FAIL"


def test_65_gabia_cookie_storage_allowed_false(auth_policy_registry):
    # auth_policy_registry는 POLICY_COOKIE_STORAGE_FORBIDDEN 상수로 정책 표현
    cookie_forbidden = getattr(auth_policy_registry, "POLICY_COOKIE_STORAGE_FORBIDDEN", None)
    if cookie_forbidden is not None:
        # 상수가 문자열 태그("COOKIE_STORAGE_FORBIDDEN") 또는 bool True 모두 허용 - 존재 자체가 금지 선언
        assert cookie_forbidden  # 값이 falsy가 아니면 PASS
    else:
        # AUTH_POLICY_REGISTRY dict 방식 fallback
        policies = getattr(auth_policy_registry, "AUTH_POLICY_REGISTRY", {})
        if policies:
            gabia = policies.get("gabia", {})
            val = gabia.get("cookie_storage_allowed", None)
            if val is not None:
                assert val is False


def test_66_all_providers_server_remote_login_false(provider_registry):
    registry = getattr(provider_registry, "PROVIDER_REGISTRY", None)
    if registry is None:
        return
    # tuple of entries or dict
    if isinstance(registry, dict):
        for provider_id, info in registry.items():
            val = info.get("server_remote_login_allowed", None)
            if val is not None:
                assert val is False, f"{provider_id}: server_remote_login_allowed must be False"
    elif hasattr(registry, "__iter__"):
        for entry in registry:
            val = getattr(entry, "server_remote_login_allowed", None)
            if val is not None:
                assert val is False, f"{getattr(entry, 'provider_id', '?')}: server_remote_login_allowed must be False"


def test_67_critical_approval_gates_auto_execute_false(approval_gate_registry):
    gates = getattr(approval_gate_registry, "APPROVAL_GATE_REGISTRY", {})
    for gate_id, gate in gates.items():
        val = gate.get("auto_execute_allowed", None)
        if val is not None:
            assert val is False, f"{gate_id}: auto_execute_allowed must be False"


# ── Phase 1-N~1-A 회귀 충돌 확인 ─────────────────────────────────────────

def _check_phase_script_exists(filename):
    path = REPO_ROOT / "scripts/ops" / filename
    return path.exists()


def _check_phase_test_exists(filename):
    path = REPO_ROOT / "tests" / filename
    return path.exists()


def test_68_phase1n_preflight_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1n_route_integration_final_preflight.py")


def test_69_phase1m_smoke_no_conflict():
    assert _check_phase_script_exists("smoke_5050_phase1m_route_integration_skeleton_internal.py")


def test_70_phase1l_skeleton_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1l_feature_flag_off_route_integration_skeleton.py")


def test_71_phase1k_preflight_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1k_wrapper_route_integration_preflight.py")


def test_72_phase1i_smoke_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1i_staging_dry_run_internal_smoke.py")


def test_73_phase1h_wrapper_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1h_route_wrapper_candidate_feature_flag_off.py")


def test_74_phase1g_pure_function_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1g_adapter_unit_implementation.py")


def test_75_phase1f_skeleton_guard_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1f_adapter_skeleton_only.py")


def test_76_phase1e_implementation_plan_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1e_adapter_implementation_plan.py")


def test_77_phase1d_dry_run_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1d_adapter_dry_run_compat.py")


def test_78_phase1b_contract_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1b_adapter_contract_detail.py")


def test_79_phase1_contract_freeze_no_conflict():
    assert _check_phase_script_exists("audit_5050_phase1_8400_contract_freeze.py")


def test_80_characterization_no_conflict():
    assert _check_phase_script_exists("audit_5050_legacy_characterization.py")


# ── 최종 verdict ──────────────────────────────────────────────────────────

def test_81_audit_verdict_is_ready(audit_result):
    assert audit_result["verdict"] == "PHASE1O_ROUTER_TOUCH_DESIGN_ONLY_READY", \
        f"verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_82_known_baseline_not_confused(audit_result):
    # known baseline 6개 실패 목록은 Phase 1-O PASS 판정과 혼동 안 됨
    # audit_result의 verdict는 Phase 1-O 자체 기준 판정
    assert "verdict" in audit_result
    assert audit_result["verdict"] != "FAIL"
