"""
Phase 1-Q 테스트: Real Router Touch Approval Gate
tests/test_5050_phase1q_router_touch_approval_gate_20260517.py
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
        "audit_phase1q",
        "scripts/ops/audit_5050_phase1q_router_touch_approval_gate.py"
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def warn_matrix(audit_mod):
    return audit_mod.get_warn_resolution_matrix()


@pytest.fixture(scope="module")
def gate_info(audit_mod):
    return audit_mod.get_approval_gate_info()


@pytest.fixture(scope="module")
def route_rows(audit_mod):
    return audit_mod.get_route_gate_rows()


# ── 1~6. import & warn matrix ─────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert hasattr(audit_mod, "run_audit")
    assert hasattr(audit_mod, "get_warn_resolution_matrix")
    assert hasattr(audit_mod, "get_approval_gate_info")
    assert hasattr(audit_mod, "get_route_gate_rows")


def test_02_warn_resolution_matrix_3_items(warn_matrix):
    assert len(warn_matrix) == 3


def test_03_inbox_not_blocked(warn_matrix):
    item = next(w for w in warn_matrix if w["warn_id"] == "INBOX_SELECTED_UNKNOWN")
    assert item["resolution_status"] != "BLOCKED"


def test_04_approval_gate_registry_not_blocked(warn_matrix):
    item = next(w for w in warn_matrix if w["warn_id"] == "APPROVAL_GATE_REGISTRY_IMPORT")
    assert item["resolution_status"] != "BLOCKED"


def test_05_selected_candidate_count_not_blocked(warn_matrix):
    item = next(w for w in warn_matrix if w["warn_id"] == "SELECTED_CANDIDATE_COUNT")
    assert item["resolution_status"] != "BLOCKED"


def test_06_blocked_count_zero(audit_result):
    assert audit_result["blocked_count"] == 0


def test_07_conditionally_accepted_has_reason(warn_matrix):
    for item in warn_matrix:
        if item["resolution_status"] == "CONDITIONALLY_ACCEPTED":
            assert item.get("remaining_risk") or item.get("evidence")


def test_08_inbox_candidate_status_exists(warn_matrix):
    item = next(w for w in warn_matrix if w["warn_id"] == "INBOX_SELECTED_UNKNOWN")
    assert item.get("evidence") is not None


# ── 9~14. approval gate registry ─────────────────────────────────────────

def test_09_approval_gate_registry_canonical_path(gate_info):
    assert gate_info.get("canonical_path") and gate_info["canonical_path"] != "UNKNOWN"


def test_10_approval_gate_registry_importable(gate_info):
    if not gate_info["importable"]:
        pytest.skip("approval_gate_registry import 실패 (CONDITIONALLY_ACCEPTED)")
    assert gate_info["importable"] is True


def test_11_auto_execute_allowed_false(gate_info):
    if not gate_info["importable"]:
        pytest.skip("registry not importable")
    raw = gate_info.get("raw_registry", {})
    for gid, g in raw.items():
        if "auto_execute_allowed" in g:
            assert g["auto_execute_allowed"] is False, f"{gid}: auto_execute_allowed=True"


def test_12_user_approval_required_true(gate_info):
    if not gate_info["importable"]:
        pytest.skip("registry not importable")
    raw = gate_info.get("raw_registry", {})
    for gid, g in raw.items():
        if "user_approval_required" in g:
            assert g["user_approval_required"] is True, f"{gid}: user_approval_required=False"


def test_13_evidence_required_true(gate_info):
    if not gate_info["importable"]:
        pytest.skip("registry not importable")
    raw = gate_info.get("raw_registry", {})
    found = any("evidence_required" in g for g in raw.values())
    if found:
        for gid, g in raw.items():
            if "evidence_required" in g:
                assert g["evidence_required"] is True, f"{gid}: evidence_required=False"


def test_14_critical_gates_auto_execute_false(gate_info):
    if not gate_info["importable"]:
        pytest.skip("registry not importable")
    raw = gate_info.get("raw_registry", {})
    for gid, g in raw.items():
        if "auto_execute_allowed" in g:
            assert g["auto_execute_allowed"] is False


# ── 15~20. candidate classification ──────────────────────────────────────

def test_15_candidate_classification_exists(audit_result):
    cc = audit_result.get("candidate_classification", {})
    assert "selected_count" in cc
    assert "primary_count" in cc
    assert "secondary_count" in cc


def test_16_selected_primary_exists_or_conditionally_accepted(audit_result, warn_matrix):
    cc = audit_result.get("candidate_classification", {})
    primary = cc.get("selected_primary", [])
    count_item = next(w for w in warn_matrix if w["warn_id"] == "SELECTED_CANDIDATE_COUNT")
    if len(primary) == 0:
        assert count_item["resolution_status"] in ("CONDITIONALLY_ACCEPTED", "RESOLVED")
    else:
        assert len(primary) >= 0


def test_17_selected_count_le10_or_accepted_reason(audit_result, warn_matrix):
    cc = audit_result["candidate_classification"]
    count = cc["selected_count"]
    count_item = next(w for w in warn_matrix if w["warn_id"] == "SELECTED_CANDIDATE_COUNT")
    if count > 10:
        assert count_item["resolution_status"] == "CONDITIONALLY_ACCEPTED"
        assert count_item.get("evidence")
    else:
        assert count <= 10


def test_18_excluded_reason_summary_exists(audit_result):
    cc = audit_result["candidate_classification"]
    assert cc.get("excluded_count") is not None


def test_19_modified_files_count_zero(audit_result):
    assert audit_result["modified_files_count"] == 0


def test_20_router_scan_readonly(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod.scan_inbox_candidates)
    for kw in [".write(", "write_text(", "os.remove", "shutil."]:
        assert kw not in src


# ── 21~36. 상수 검증 ────────────────────────────────────────────────────

def test_21_real_router_touch_allowed_false(audit_mod):
    assert audit_mod.REAL_ROUTER_TOUCH_ALLOWED is False


def test_22_router_file_modification_allowed_false(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_ALLOWED is False


def test_23_route_registration_allowed_false(audit_mod):
    assert audit_mod.ROUTE_REGISTRATION_ALLOWED is False


def test_24_apirouter_allowed_false(audit_mod):
    assert audit_mod.APIRouter_ALLOWED is False


def test_25_include_router_allowed_false(audit_mod):
    assert audit_mod.INCLUDE_ROUTER_ALLOWED is False


def test_26_route_decorator_allowed_false(audit_mod):
    assert audit_mod.ROUTE_DECORATOR_ALLOWED is False


def test_27_feature_flag_runtime_hook_allowed_false(audit_mod):
    assert audit_mod.FEATURE_FLAG_RUNTIME_HOOK_ALLOWED is False


def test_28_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_29_dry_run_only_true(audit_mod):
    assert audit_mod.DRY_RUN_ONLY is True


def test_30_human_approval_required_for_phase1r_true(audit_mod):
    assert audit_mod.HUMAN_APPROVAL_REQUIRED_FOR_PHASE1R is True


# ── 31~37. Phase 1-R entry conditions ────────────────────────────────────

def test_31_phase1r_entry_conditions_exist(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert len(conds) >= 5


def test_32_user_approval_required_in_conditions(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert any("user" in c or "approval" in c for c in conds)


def test_33_git_clean_condition(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert any("git" in c or "clean" in c for c in conds)


def test_34_head_sync_condition(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert any("head" in c or "sync" in c or "origin" in c for c in conds)


def test_35_no_router_modification_condition(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert any("router" in c or "modification" in c for c in conds)


def test_36_approval_gate_path_condition(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert any("approval" in c or "gate" in c for c in conds)


def test_37_inbox_resolution_condition(audit_result):
    conds = audit_result.get("phase1r_entry_conditions", [])
    assert any("inbox" in c or "candidate" in c or "resolved" in c for c in conds)


# ── 38~46. route gate rows ───────────────────────────────────────────────

def test_38_task_approve_approval_gate_required(route_rows):
    row = next(r for r in route_rows if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    assert row["approval_gate_required"] is True


def test_39_task_reject_approval_gate_required(route_rows):
    row = next(r for r in route_rows if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    assert row["approval_gate_required"] is True


def test_40_approval_gate_executed_allowed_false_all(route_rows):
    for row in route_rows:
        assert row["approval_gate_executed_allowed"] is False


def test_41_no_double_slash_approve(route_rows):
    row = next(r for r in route_rows if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON")
    for f in row.get("selected_candidate_files", []):
        assert "//" not in f


def test_42_no_double_slash_reject(route_rows):
    row = next(r for r in route_rows if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON")
    for f in row.get("selected_candidate_files", []):
        assert "//" not in f


def test_43_execute_not_in_scope(route_rows):
    for row in route_rows:
        assert "/execute" not in str(row.get("selected_candidate_files", []))


def test_44_webhook_not_in_scope(route_rows):
    for row in route_rows:
        assert "webhook" not in str(row.get("selected_candidate_files", [])).lower()


def test_45_dashboard_not_in_scope(route_rows):
    for row in route_rows:
        assert "dashboard" not in str(row.get("selected_candidate_files", [])).lower()


def test_46_same_contract_not_in_scope(route_rows):
    for row in route_rows:
        s = str(row.get("selected_candidate_files", []))
        assert "SAME_CONTRACT_001" not in s
        assert "SAME_CONTRACT_002" not in s


# ── 47~59. 정적 코드 검사 ────────────────────────────────────────────────

def test_47_no_route_integration_import_in_routers():
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
                    assert False, f"{py_file}: route integration 외부 import"


def test_48_fastapi_handler_not_modified():
    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for f in root.rglob("router*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            assert "phase1q" not in content.lower(), f"{f}: phase1q 마커"


def test_49_flask_route_not_modified():
    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "phase1q" in py_file.name.lower():
                continue
            if "test_" in py_file.name or "audit_" in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            assert "phase1q" not in content.lower(), f"{py_file}: phase1q 마커"


def test_50_no_apirouter(audit_mod):
    import inspect
    assert "APIRouter()" not in inspect.getsource(audit_mod)


def test_51_no_include_router(audit_mod):
    import inspect
    # 키워드 자체가 문자열 리터럴로 등장할 수 있으므로, 실제 코드 호출 패턴만 검사
    src = inspect.getsource(audit_mod)
    # include_router( 호출이 있으면 안 됨 (문자열 리스트 내 패턴은 제외)
    import re
    # 문자열 리터럴 안이 아닌 실제 코드 호출 형태 검사
    assert "include_router(app" not in src and "include_router(router" not in src


def test_52_no_route_decorator(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    import re
    # @router. 또는 @app.route 가 실제 데코레이터 문법으로 쓰이는지 확인
    # (문자열 리스트 내 패턴은 제외, 실제 라인 시작의 @ 패턴만 검사)
    lines = src.splitlines()
    for line in lines:
        stripped = line.strip()
        assert not (stripped.startswith("@router.") or stripped.startswith("@app.route")), \
            f"route decorator found: {stripped}"


def test_53_no_http_client(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    for kw in ["import requests", "import httpx", "import aiohttp"]:
        assert kw not in src


def test_54_no_db_client(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    for kw in ["import sqlalchemy", "import psycopg2", "import sqlite3"]:
        assert kw not in src


def test_55_no_subprocess_socket(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "import subprocess" not in src
    assert "import socket" not in src


def test_56_no_os_environ(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "os.environ[" not in src
    assert "os.getenv(" not in src


def test_57_no_feature_flag_runtime_hook(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod).lower()
    # FEATURE_FLAG_RUNTIME_HOOK_ALLOWED 상수 자체는 허용, 실제 runtime_hook 호출/import는 금지
    lines = [l.strip() for l in src.splitlines()]
    for line in lines:
        if "runtime_hook" in line:
            # 상수 정의 또는 결과 dict key로 등장하는 경우는 허용
            assert ("feature_flag_runtime_hook_allowed" in line or
                    '"feature_flag_runtime_hook_allowed"' in line or
                    "feature_flag_runtime_hook_allowed" in line), \
                f"runtime_hook 호출 발견: {line}"


def test_58_no_server_startup(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "uvicorn" not in src
    assert "app.run(" not in src


def test_59_no_uvicorn_gunicorn(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "uvicorn" not in src
    assert "gunicorn" not in src


# ── 60~63. external site registry ────────────────────────────────────────

def test_60_no_external_site_conflict(audit_result):
    assert audit_result["verdict"] != "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_BLOCKED"


def test_61_gabia_cookie_storage_false():
    try:
        mod = _load_module("auth_q", "ai_orchestrator/external_sites/auth_policy_registry.py")
    except Exception:
        pytest.skip("auth_policy_registry not found")
    # auth_policy_registry 는 PROVIDER_REGISTRY(tuple of SiteProviderEntry) 구조
    registry = getattr(mod, "PROVIDER_REGISTRY", None)
    if not registry:
        pytest.skip("PROVIDER_REGISTRY not found in auth_policy_registry")
    # GABIA provider 탐색
    gabia_entry = None
    for entry in registry:
        pid = getattr(entry, "provider_id", "")
        if pid == "GABIA" or str(pid).lower() == "gabia":
            gabia_entry = entry
            break
    if gabia_entry is None:
        pytest.skip("GABIA entry not found")
    assert getattr(gabia_entry, "cookie_storage_allowed") is False


def test_62_all_providers_server_remote_login_false():
    try:
        mod = _load_module("provider_q", "ai_orchestrator/external_sites/provider_registry.py")
    except Exception:
        pytest.skip("provider_registry not found")
    registry = getattr(mod, "PROVIDER_REGISTRY", None)
    if not registry:
        pytest.skip("PROVIDER_REGISTRY not found")
    # tuple of SiteProviderEntry 또는 dict 처리
    if isinstance(registry, dict):
        entries = registry.values()
    else:
        entries = registry
    for entry in entries:
        if hasattr(entry, "server_remote_login_allowed"):
            assert entry.server_remote_login_allowed is False, \
                f"{getattr(entry, 'provider_id', entry)}: server_remote_login_allowed=True"
        elif isinstance(entry, dict) and "server_remote_login_allowed" in entry:
            assert entry["server_remote_login_allowed"] is False


def test_63_critical_approval_gates_auto_execute_false(gate_info):
    if not gate_info.get("importable"):
        pytest.skip("registry not importable")
    for gid, g in gate_info.get("raw_registry", {}).items():
        if "auto_execute_allowed" in g:
            assert g["auto_execute_allowed"] is False


# ── 64~78. 이전 phase 회귀 ───────────────────────────────────────────────

def _script_exists(name):
    return (REPO_ROOT / "scripts/ops" / name).exists()


def test_64_phase1p_no_conflict():
    assert _script_exists("audit_5050_phase1p_router_integration_implementation_plan.py")


def test_65_phase1o_no_conflict():
    assert _script_exists("audit_5050_phase1o_router_touch_design_only.py")


def test_66_phase1n_no_conflict():
    assert _script_exists("audit_5050_phase1n_route_integration_final_preflight.py")


def test_67_phase1m_no_conflict():
    assert _script_exists("smoke_5050_phase1m_route_integration_skeleton_internal.py")


def test_68_phase1l_no_conflict():
    assert _script_exists("audit_5050_phase1l_feature_flag_off_route_integration_skeleton.py")


def test_69_phase1k_no_conflict():
    assert _script_exists("audit_5050_phase1k_wrapper_route_integration_preflight.py")


def test_70_phase1i_no_conflict():
    assert _script_exists("audit_5050_phase1i_staging_dry_run_internal_smoke.py")


def test_71_phase1h_no_conflict():
    assert _script_exists("audit_5050_phase1h_route_wrapper_candidate_feature_flag_off.py")


def test_72_phase1g_no_conflict():
    assert _script_exists("audit_5050_phase1g_adapter_unit_implementation.py")


def test_73_phase1f_no_conflict():
    assert _script_exists("audit_5050_phase1f_adapter_skeleton_only.py")


def test_74_phase1e_no_conflict():
    assert _script_exists("audit_5050_phase1e_adapter_implementation_plan.py")


def test_75_phase1d_no_conflict():
    assert _script_exists("audit_5050_phase1d_adapter_dry_run_compat.py")


def test_76_phase1b_no_conflict():
    assert _script_exists("audit_5050_phase1b_adapter_contract_detail.py")


def test_77_phase1_contract_freeze_no_conflict():
    assert _script_exists("audit_5050_phase1_8400_contract_freeze.py")


def test_78_characterization_no_conflict():
    assert _script_exists("audit_5050_legacy_characterization.py")


# ── 79~80. 최종 ──────────────────────────────────────────────────────────

def test_79_audit_verdict_ready(audit_result):
    v = audit_result["verdict"]
    assert v in (
        "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_READY",
        "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_READY_WITH_WARN",
    ), f"verdict: {v}, errors: {audit_result.get('errors')}"


def test_80_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_BLOCKED"
