"""
Phase 1-L Feature Flag OFF Route Integration Skeleton Tests (2026-05-17)
실제 route 등록 없이 skeleton, metadata, fixture, 정적 검사만 수행.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def load_common():
    import backend.compat.legacy_5050.route_integration.common as m
    return m


def load_inbox():
    import backend.compat.legacy_5050.route_integration.inbox_email_fetch_route_skeleton as m
    return m


def load_approval():
    import backend.compat.legacy_5050.route_integration.task_approval_route_skeleton as m
    return m


def load_audit():
    import scripts.ops.audit_5050_phase1l_feature_flag_off_route_integration_skeleton as m
    return m


# ── 1~7. import 가능 ──────────────────────────────────────────────────────────

def test_01_route_integration_package_importable():
    import backend.compat.legacy_5050.route_integration
    assert backend.compat.legacy_5050.route_integration.ROUTE_REGISTERED is False


def test_02_route_integration_common_importable():
    m = load_common()
    assert m is not None


def test_03_error_skeleton_exists():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationSkeletonError
    assert issubclass(RouteIntegrationSkeletonError, Exception)


def test_04_error_disabled_exists():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationDisabledError
    assert issubclass(RouteIntegrationDisabledError, Exception)


def test_05_error_unsafe_exists():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationUnsafeExecutionError
    assert issubclass(RouteIntegrationUnsafeExecutionError, Exception)


def test_06_inbox_skeleton_importable():
    m = load_inbox()
    assert m is not None


def test_07_approval_skeleton_importable():
    m = load_approval()
    assert m is not None


# ── 8~13. 함수 존재 ───────────────────────────────────────────────────────────

def test_08_inbox_metadata_function_exists():
    assert callable(load_inbox().get_inbox_email_fetch_route_skeleton_metadata)


def test_09_approve_metadata_function_exists():
    assert callable(load_approval().get_task_approve_route_skeleton_metadata)


def test_10_reject_metadata_function_exists():
    assert callable(load_approval().get_task_reject_route_skeleton_metadata)


def test_11_inbox_skeleton_function_exists():
    assert callable(load_inbox().inbox_email_fetch_route_integration_skeleton)


def test_12_approve_skeleton_function_exists():
    assert callable(load_approval().task_approve_route_integration_skeleton)


def test_13_reject_skeleton_function_exists():
    assert callable(load_approval().task_reject_route_integration_skeleton)


# ── 14~17. 상수 검증 ──────────────────────────────────────────────────────────

def test_14_feature_flag_default_false_all():
    i = load_inbox()
    a = load_approval()
    assert i.FEATURE_FLAG_DEFAULT is False
    assert a.APPROVE_FEATURE_FLAG_DEFAULT is False
    assert a.REJECT_FEATURE_FLAG_DEFAULT is False


def test_15_route_registered_false_all():
    i = load_inbox()
    a = load_approval()
    assert i.ROUTE_REGISTERED is False
    assert a.APPROVE_ROUTE_REGISTERED is False
    assert a.REJECT_ROUTE_REGISTERED is False


def test_16_live_traffic_allowed_false_all():
    i = load_inbox()
    a = load_approval()
    assert i.LIVE_TRAFFIC_ALLOWED is False
    assert a.APPROVE_LIVE_TRAFFIC_ALLOWED is False
    assert a.REJECT_LIVE_TRAFFIC_ALLOWED is False


def test_17_dry_run_allowed_true_all():
    i = load_inbox()
    a = load_approval()
    assert i.DRY_RUN_ALLOWED is True
    assert a.APPROVE_DRY_RUN_ALLOWED is True
    assert a.REJECT_DRY_RUN_ALLOWED is True


# ── 18~21. disabled result ────────────────────────────────────────────────────

def test_18_inbox_dry_run_false_returns_disabled():
    r = load_inbox().inbox_email_fetch_route_integration_skeleton(dry_run=False)
    assert r["ok"] is False


def test_19_approve_dry_run_false_returns_disabled():
    r = load_approval().task_approve_route_integration_skeleton(dry_run=False)
    assert r["ok"] is False


def test_20_reject_dry_run_false_returns_disabled():
    r = load_approval().task_reject_route_integration_skeleton(dry_run=False)
    assert r["ok"] is False


def test_21_disabled_result_would_call_wrapper_false():
    r = load_inbox().inbox_email_fetch_route_integration_skeleton(dry_run=False)
    assert r["would_call_wrapper"] is False
    r2 = load_approval().task_approve_route_integration_skeleton(dry_run=False)
    assert r2["would_call_wrapper"] is False


# ── 22~24. unsafe error ───────────────────────────────────────────────────────

def test_22_inbox_feature_flag_true_raises():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationUnsafeExecutionError
    with pytest.raises(RouteIntegrationUnsafeExecutionError):
        load_inbox().inbox_email_fetch_route_integration_skeleton(feature_flag_enabled=True)


def test_23_approve_feature_flag_true_raises():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationUnsafeExecutionError
    with pytest.raises(RouteIntegrationUnsafeExecutionError):
        load_approval().task_approve_route_integration_skeleton(feature_flag_enabled=True)


def test_24_reject_feature_flag_true_raises():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationUnsafeExecutionError
    with pytest.raises(RouteIntegrationUnsafeExecutionError):
        load_approval().task_reject_route_integration_skeleton(feature_flag_enabled=True)


# ── 25~36. dry-run fixture mode ───────────────────────────────────────────────

def test_25_inbox_dry_run_true_fixture_success():
    r = load_inbox().inbox_email_fetch_route_integration_skeleton({"mailbox": "inbox"}, dry_run=True)
    assert r["ok"] is True


def test_26_inbox_dry_run_route_registered_false():
    r = load_inbox().inbox_email_fetch_route_integration_skeleton({"mailbox": "inbox"}, dry_run=True)
    assert r["route_registered"] is False


def test_27_inbox_dry_run_wrapper_result_exists():
    r = load_inbox().inbox_email_fetch_route_integration_skeleton({"mailbox": "inbox"}, dry_run=True)
    assert "wrapper_result" in r


def test_28_inbox_secret_field_raises():
    from backend.compat.legacy_5050.route_integration.common import RouteIntegrationUnsafeExecutionError
    with pytest.raises(RouteIntegrationUnsafeExecutionError):
        load_inbox().inbox_email_fetch_route_integration_skeleton({"password": "secret123"}, dry_run=True)


def test_29_approve_dry_run_true_fixture_success():
    r = load_approval().task_approve_route_integration_skeleton("t-1", {"status": "approved"}, dry_run=True)
    assert r["ok"] is True


def test_30_approve_dry_run_wrapper_result_exists():
    r = load_approval().task_approve_route_integration_skeleton("t-1", {"status": "approved"}, dry_run=True)
    assert "wrapper_result" in r


def test_31_approve_approval_gate_executed_false():
    r = load_approval().task_approve_route_integration_skeleton("t-1", {"status": "approved"}, dry_run=True)
    nr = r["wrapper_result"].get("normalized_response", {})
    assert nr.get("approval_gate_executed") is False


def test_32_approve_task_id_required():
    with pytest.raises(Exception):
        load_approval().task_approve_route_integration_skeleton(None, {"status": "ok"}, dry_run=True)


def test_33_reject_dry_run_true_fixture_success():
    r = load_approval().task_reject_route_integration_skeleton("t-2", {"status": "rejected"}, dry_run=True)
    assert r["ok"] is True


def test_34_reject_dry_run_wrapper_result_exists():
    r = load_approval().task_reject_route_integration_skeleton("t-2", {"status": "rejected"}, dry_run=True)
    assert "wrapper_result" in r


def test_35_reject_approval_gate_executed_false():
    r = load_approval().task_reject_route_integration_skeleton("t-2", {"status": "rejected"}, dry_run=True)
    nr = r["wrapper_result"].get("normalized_response", {})
    assert nr.get("approval_gate_executed") is False


def test_36_reject_task_id_required():
    with pytest.raises(Exception):
        load_approval().task_reject_route_integration_skeleton(None, {"status": "ok"}, dry_run=True)


# ── 37~42. double slash / forbidden route ────────────────────────────────────

def test_37_no_double_slash_approve_fastapi():
    a = load_approval()
    assert "//" not in a.APPROVE_FASTAPI_PATH_TEMPLATE


def test_38_no_double_slash_reject_fastapi():
    a = load_approval()
    assert "//" not in a.REJECT_FASTAPI_PATH_TEMPLATE


def test_39_execute_not_in_phase1l_scope():
    ids = [
        load_inbox().ROUTE_SKELETON_ID,
        load_approval().APPROVE_ROUTE_SKELETON_ID,
        load_approval().REJECT_ROUTE_SKELETON_ID,
    ]
    assert not any("execute" in i.lower() for i in ids)


def test_40_webhook_not_in_phase1l_scope():
    ids = [
        load_inbox().ROUTE_SKELETON_ID,
        load_approval().APPROVE_ROUTE_SKELETON_ID,
        load_approval().REJECT_ROUTE_SKELETON_ID,
    ]
    assert not any("webhook" in i.lower() for i in ids)


def test_41_dashboard_not_in_phase1l_scope():
    ids = [
        load_inbox().ROUTE_SKELETON_ID,
        load_approval().APPROVE_ROUTE_SKELETON_ID,
        load_approval().REJECT_ROUTE_SKELETON_ID,
    ]
    assert not any("dashboard" in i.lower() for i in ids)


def test_42_same_contract_not_in_phase1l_scope():
    ids = [
        load_inbox().ROUTE_SKELETON_ID,
        load_approval().APPROVE_ROUTE_SKELETON_ID,
        load_approval().REJECT_ROUTE_SKELETON_ID,
    ]
    assert not any("same_contract" in i.lower() for i in ids)


# ── 43~55. 정적/금지 import 검사 ─────────────────────────────────────────────

def _read_skeleton_sources() -> list[tuple[str, str]]:
    files = [
        REPO_ROOT / "backend/compat/legacy_5050/route_integration/__init__.py",
        REPO_ROOT / "backend/compat/legacy_5050/route_integration/common.py",
        REPO_ROOT / "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
        REPO_ROOT / "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
    ]
    return [(str(f.name), f.read_text(encoding="utf-8")) for f in files if f.exists()]


def test_43_no_route_router_file_imports_skeleton():
    m = load_audit()
    result = m.run_route_integration_import_scan()
    assert result["verdict"] == "PASS", result["violations"]


def test_44_no_fastapi_handler_modification():
    m = load_audit()
    result = m.run_route_integration_import_scan()
    assert result["verdict"] == "PASS"


def test_45_no_flask_route_modification():
    for name, src in _read_skeleton_sources():
        assert "= Flask(" not in src, f"{name}: Flask import found"
        assert "@app.route" not in src, f"{name}: Flask route decorator found"


def test_46_no_apirouter():
    for name, src in _read_skeleton_sources():
        assert "= APIRouter(" not in src, f"{name}: APIRouter found"
        assert "APIRouter()" not in src, f"{name}: APIRouter found"


def test_47_no_include_router():
    for name, src in _read_skeleton_sources():
        assert "include_router(" not in src, f"{name}: include_router found"


def test_48_no_route_decorator():
    for name, src in _read_skeleton_sources():
        assert "@router.get" not in src, f"{name}: route decorator found"
        assert "@router.post" not in src, f"{name}: route decorator found"


def test_49_no_http_client_import():
    for name, src in _read_skeleton_sources():
        assert "import requests" not in src, f"{name}"
        assert "import httpx" not in src, f"{name}"
        assert "import urllib.request" not in src, f"{name}"


def test_50_no_db_client_import():
    for name, src in _read_skeleton_sources():
        assert "import sqlite3" not in src, f"{name}"
        assert "import psycopg" not in src, f"{name}"
        assert "sqlalchemy.create_engine" not in src, f"{name}"


def test_51_no_subprocess_socket():
    for name, src in _read_skeleton_sources():
        assert "import subprocess" not in src, f"{name}"
        assert "import socket" not in src, f"{name}"


def test_52_no_os_environ_value_access():
    for name, src in _read_skeleton_sources():
        assert "os.environ[" not in src, f"{name}"
        assert "os.environ.get(" not in src, f"{name}"


def test_53_no_feature_flag_runtime_hook():
    for name, src in _read_skeleton_sources():
        assert "app.state" not in src, f"{name}"
        assert "add_middleware" not in src, f"{name}"


def test_54_no_server_startup():
    for name, src in _read_skeleton_sources():
        assert "uvicorn.run(" not in src, f"{name}"
        assert "app.run(" not in src, f"{name}"


def test_55_no_uvicorn_gunicorn():
    for name, src in _read_skeleton_sources():
        assert "uvicorn" not in src, f"{name}"
        assert "gunicorn" not in src, f"{name}"


# ── 56~65. Phase 회귀 파일 존재 ──────────────────────────────────────────────

def test_56_phase1k_preflight_exists():
    p = REPO_ROOT / "scripts/ops/audit_5050_phase1k_wrapper_route_integration_preflight.py"
    assert p.exists()


def test_57_phase1i_smoke_runner_exists():
    p = REPO_ROOT / "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py"
    assert p.exists()


def test_58_phase1h_wrapper_candidates_exist():
    for fname in [
        "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
        "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
    ]:
        assert (REPO_ROOT / fname).exists(), fname


def test_59_phase1g_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1g_adapter_unit_implementation.py").exists()


def test_60_phase1f_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py").exists()


def test_61_phase1e_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py").exists()


def test_62_phase1d_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1d_adapter_dry_run_compat.py").exists()


def test_63_phase1b_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1b_adapter_contract_detail.py").exists()


def test_64_phase1_contract_freeze_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_65_characterization_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


# ── 66~67. 최종 판정 ──────────────────────────────────────────────────────────

def test_66_audit_script_verdict_ready():
    m = load_audit()
    file_errors = m.check_files_exist()
    static_scan = m.run_static_forbidden_pattern_scan()
    import_scan = m.run_route_integration_import_scan()
    dynamic_errors = m.run_dynamic_checks()
    verdict = m.get_overall_verdict(file_errors, static_scan, import_scan, dynamic_errors)
    assert verdict == "PHASE1L_FEATURE_FLAG_OFF_ROUTE_INTEGRATION_SKELETON_READY", \
        f"verdict={verdict} errors={file_errors + dynamic_errors}"


def test_67_known_baseline_not_in_phase1l():
    known = [
        "test_app_foundation_p1_gates",
        "test_cad_local_agent_adapter_20260509",
        "test_mcp_local_cad_adapter_tools_20260509",
    ]
    ids = [
        load_inbox().ROUTE_SKELETON_ID,
        load_approval().APPROVE_ROUTE_SKELETON_ID,
        load_approval().REJECT_ROUTE_SKELETON_ID,
    ]
    for k in known:
        assert not any(k in i.lower() for i in ids)
