"""
Phase 1-M Route Integration Skeleton Internal Smoke Tests (2026-05-17)
실제 HTTP 호출 없이 smoke runner, route skeleton, fixture, 정적 검사만 수행.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_smoke():
    import scripts.ops.smoke_5050_phase1m_route_integration_skeleton_internal as m
    return m


def load_audit():
    import scripts.ops.audit_5050_phase1m_route_integration_skeleton_internal_smoke as m
    return m


_smoke_summary = None


def get_summary():
    global _smoke_summary
    if _smoke_summary is None:
        _smoke_summary = load_smoke().run_phase1m_internal_smoke()
    return _smoke_summary


# ── 1~4. import / 함수 존재 ───────────────────────────────────────────────────

def test_01_smoke_runner_importable():
    assert load_smoke() is not None


def test_02_audit_script_importable():
    assert load_audit() is not None


def test_03_build_fixtures_function_exists():
    assert callable(load_smoke().build_phase1m_smoke_fixtures)


def test_04_run_smoke_function_exists():
    assert callable(load_smoke().run_phase1m_internal_smoke)


# ── 5~14. summary 기본 필드 ───────────────────────────────────────────────────

def test_05_smoke_phase():
    assert get_summary()["phase"] == "PHASE_1M"


def test_06_smoke_id():
    assert get_summary()["smoke_id"] == "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE"


def test_07_staging_mode():
    assert get_summary()["staging_mode"] == "INTERNAL_FIXTURE_ONLY"


def test_08_route_skeleton_count():
    assert get_summary()["route_skeleton_count"] == 3


def test_09_total_scenarios_gte_15():
    assert get_summary()["total_scenarios"] >= 15


def test_10_failed_scenarios_zero():
    assert get_summary()["failed_scenarios"] == 0


def test_11_disabled_mode_passed():
    assert get_summary()["disabled_mode_passed"] is True


def test_12_unsafe_mode_passed():
    assert get_summary()["unsafe_mode_passed"] is True


def test_13_dry_run_success_passed():
    assert get_summary()["dry_run_success_passed"] is True


def test_14_bad_fixture_boundary_passed():
    assert get_summary()["bad_fixture_boundary_passed"] is True


# ── 15~27. safety counters ────────────────────────────────────────────────────

def test_15_server_started_false():
    assert get_summary()["server_started"] is False


def test_16_route_registered_false():
    assert get_summary()["route_registered"] is False


def test_17_route_connected_false():
    assert get_summary()["route_connected"] is False


def test_18_live_traffic_allowed_false():
    assert get_summary()["live_traffic_allowed"] is False


def test_19_http_call_count_zero():
    assert get_summary()["http_call_count"] == 0


def test_20_db_read_count_zero():
    assert get_summary()["db_read_count"] == 0


def test_21_db_write_count_zero():
    assert get_summary()["db_write_count"] == 0


def test_22_secret_value_output_count_zero():
    assert get_summary()["secret_value_output_count"] == 0


def test_23_email_fetch_live_call_count_zero():
    assert get_summary()["email_fetch_live_call_count"] == 0


def test_24_approve_live_call_count_zero():
    assert get_summary()["approve_live_call_count"] == 0


def test_25_reject_live_call_count_zero():
    assert get_summary()["reject_live_call_count"] == 0


def test_26_execute_call_count_zero():
    assert get_summary()["execute_call_count"] == 0


def test_27_webhook_call_count_zero():
    assert get_summary()["webhook_call_count"] == 0


# ── 28~40. scenario별 검증 ─────────────────────────────────────────────────────

def _find_scenario(sid):
    for s in get_summary()["scenarios"]:
        if s["id"] == sid:
            return s
    return None


def test_28_disabled_inbox_pass():
    s = _find_scenario("inbox_disabled")
    assert s and s["pass"] is True
    assert s["detail"].get("ok") is False


def test_29_disabled_approve_pass():
    s = _find_scenario("approve_disabled")
    assert s and s["pass"] is True


def test_30_disabled_reject_pass():
    s = _find_scenario("reject_disabled")
    assert s and s["pass"] is True


def test_31_disabled_would_call_wrapper_false():
    for sid in ["inbox_disabled", "approve_disabled", "reject_disabled"]:
        s = _find_scenario(sid)
        assert s["detail"].get("would_call_wrapper") is False, sid


def test_32_unsafe_inbox_error():
    s = _find_scenario("inbox_unsafe_flag")
    assert s and s["pass"] is True


def test_33_unsafe_approve_error():
    s = _find_scenario("approve_unsafe_flag")
    assert s and s["pass"] is True


def test_34_unsafe_reject_error():
    s = _find_scenario("reject_unsafe_flag")
    assert s and s["pass"] is True


def test_35_dry_run_inbox_success():
    s = _find_scenario("inbox_dry_run_success")
    assert s and s["pass"] is True
    assert s["detail"].get("ok") is True


def test_36_dry_run_inbox_wrapper_result():
    s = _find_scenario("inbox_dry_run_success")
    assert "wrapper_result" in s["detail"]


def test_37_dry_run_approve_success():
    s = _find_scenario("approve_dry_run_success")
    assert s and s["pass"] is True


def test_38_dry_run_approve_approval_gate_executed_false():
    s = _find_scenario("approve_dry_run_success")
    nr = s["detail"].get("wrapper_result", {}).get("normalized_response", {})
    assert nr.get("approval_gate_executed") is False


def test_39_dry_run_reject_success():
    s = _find_scenario("reject_dry_run_success")
    assert s and s["pass"] is True


def test_40_dry_run_reject_approval_gate_executed_false():
    s = _find_scenario("reject_dry_run_success")
    nr = s["detail"].get("wrapper_result", {}).get("normalized_response", {})
    assert nr.get("approval_gate_executed") is False


# ── 41~46. bad fixture boundary ───────────────────────────────────────────────

def test_41_inbox_secret_bad_fixture_error():
    s = _find_scenario("inbox_secret_field_error")
    assert s and s["pass"] is True


def test_42_inbox_live_context_key_error():
    s = _find_scenario("inbox_live_context_key_error")
    assert s and s["pass"] is True


def test_43_approve_missing_task_id_error():
    s = _find_scenario("approve_missing_task_id_error")
    assert s and s["pass"] is True


def test_44_reject_missing_task_id_error():
    s = _find_scenario("reject_missing_task_id_error")
    assert s and s["pass"] is True


def test_45_approve_no_double_slash():
    s = _find_scenario("approve_no_double_slash")
    assert s and s["pass"] is True


def test_46_reject_no_double_slash():
    s = _find_scenario("reject_no_double_slash")
    assert s and s["pass"] is True


# ── 47~50. 제외 scope ────────────────────────────────────────────────────────

def test_47_execute_not_in_smoke_scope():
    assert get_summary()["execute_call_count"] == 0
    assert get_summary()["no_forbidden_route"] is True


def test_48_webhook_not_in_smoke_scope():
    assert get_summary()["webhook_call_count"] == 0


def test_49_dashboard_not_in_smoke_scope():
    ids = [s["id"] for s in get_summary()["scenarios"]]
    assert not any("dashboard" in i for i in ids)


def test_50_same_contract_not_in_smoke_scope():
    ids = [s["id"] for s in get_summary()["scenarios"]]
    assert not any("same_contract" in i for i in ids)


# ── 51~63. 정적 검사 ──────────────────────────────────────────────────────────

def _read_smoke_src():
    p = REPO_ROOT / "scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py"
    return p.read_text(encoding="utf-8")


def test_51_no_route_router_imports_smoke():
    m = load_audit()
    result = m.run_static_pattern_scan()
    assert result["verdict"] == "PASS", result["violations"]


def test_52_no_fastapi_handler_modification():
    assert "= FastAPI(" not in _read_smoke_src()


def test_53_no_flask_route_modification():
    assert "= Flask(" not in _read_smoke_src()
    assert "@app.route" not in _read_smoke_src()


def test_54_no_apirouter():
    assert "= APIRouter(" not in _read_smoke_src()
    assert "APIRouter()" not in _read_smoke_src()


def test_55_no_include_router():
    assert "include_router(" not in _read_smoke_src()


def test_56_no_route_decorator():
    assert "@router.get" not in _read_smoke_src()
    assert "@router.post" not in _read_smoke_src()


def test_57_no_http_client_import():
    src = _read_smoke_src()
    assert "import requests" not in src
    assert "import httpx" not in src
    assert "import urllib.request" not in src


def test_58_no_db_client_import():
    src = _read_smoke_src()
    assert "import sqlite3" not in src
    assert "import psycopg" not in src


def test_59_no_subprocess_socket():
    src = _read_smoke_src()
    assert "import subprocess" not in src
    assert "import socket" not in src


def test_60_no_os_environ_value():
    assert "os.environ[" not in _read_smoke_src()
    assert "os.environ.get(" not in _read_smoke_src()


def test_61_no_feature_flag_runtime_hook():
    src = _read_smoke_src()
    assert "app.state" not in src
    assert "add_middleware" not in src


def test_62_no_server_startup():
    src = _read_smoke_src()
    assert "uvicorn.run(" not in src
    assert "app.run(" not in src


def test_63_no_uvicorn_gunicorn():
    src = _read_smoke_src()
    assert "uvicorn" not in src
    assert "gunicorn" not in src


# ── 64~74. Phase 회귀 파일 존재 ──────────────────────────────────────────────

def test_64_phase1l_skeleton_exists():
    for f in [
        "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
        "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
    ]:
        assert (REPO_ROOT / f).exists(), f


def test_65_phase1k_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1k_wrapper_route_integration_preflight.py").exists()


def test_66_phase1i_smoke_exists():
    assert (REPO_ROOT / "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py").exists()


def test_67_phase1h_wrappers_exist():
    for f in [
        "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
        "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
    ]:
        assert (REPO_ROOT / f).exists(), f


def test_68_phase1g_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1g_adapter_unit_implementation.py").exists()


def test_69_phase1f_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py").exists()


def test_70_phase1e_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py").exists()


def test_71_phase1d_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1d_adapter_dry_run_compat.py").exists()


def test_72_phase1b_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1b_adapter_contract_detail.py").exists()


def test_73_phase1_contract_freeze_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_74_characterization_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


# ── 75~76. 최종 판정 ──────────────────────────────────────────────────────────

def test_75_audit_verdict_ready():
    m = load_audit()
    file_errors = m.check_files_exist()
    static_scan = m.run_static_pattern_scan()
    dynamic = m.run_dynamic_smoke_check()
    verdict = m.get_overall_verdict(file_errors, static_scan, dynamic)
    assert verdict == "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE_READY", \
        f"verdict={verdict} errors={file_errors + dynamic['errors']}"


def test_76_known_baseline_not_in_phase1m():
    known = [
        "test_app_foundation_p1_gates",
        "test_cad_local_agent_adapter_20260509",
        "test_mcp_local_cad_adapter_tools_20260509",
    ]
    smoke_id = get_summary()["smoke_id"]
    for k in known:
        assert k not in smoke_id.lower()
