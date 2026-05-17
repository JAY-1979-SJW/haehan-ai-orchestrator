"""
Phase 1-K Wrapper Route Integration Preflight Tests (2026-05-17)
실제 route 연결 없이 preflight matrix, 정적 scan, 기존 산출물 회귀만 검증.
"""

import os
import sys
import importlib
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))

# ──────────────────────────────────────────────
# 보조 함수
# ──────────────────────────────────────────────

def load_audit():
    import scripts.ops.audit_5050_phase1k_wrapper_route_integration_preflight as m
    return m


def load_matrix():
    m = load_audit()
    return m.PREFLIGHT_MATRIX


# ──────────────────────────────────────────────
# 1. import 가능
# ──────────────────────────────────────────────

def test_01_audit_script_importable():
    m = load_audit()
    assert m is not None


# ──────────────────────────────────────────────
# 2. matrix 기본 구조
# ──────────────────────────────────────────────

def test_02_matrix_has_exactly_3_rows():
    assert len(load_matrix()) == 3


def test_03_wrapper_ids_correct():
    ids = {r["wrapper_id"] for r in load_matrix()}
    assert ids == {
        "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE",
        "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE",
        "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE",
    }


def test_04_adapter_ids_correct():
    expected = {
        "INBOX_EMAIL_FETCH_ADAPTER",
        "TASK_APPROVE_PATH_AUTH_ADAPTER",
        "TASK_REJECT_PATH_AUTH_ADAPTER",
    }
    actual = {r["adapter_id"] for r in load_matrix()}
    assert actual == expected


def test_05_feature_flags_correct():
    expected = {
        "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED",
        "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED",
        "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED",
    }
    actual = {r["feature_flag"] for r in load_matrix()}
    assert actual == expected


# ──────────────────────────────────────────────
# 3. 필드 값 검증
# ──────────────────────────────────────────────

def test_06_feature_flag_default_false_all():
    for r in load_matrix():
        assert r["feature_flag_default"] is False, r["wrapper_id"]


def test_07_route_connected_now_false_all():
    for r in load_matrix():
        assert r["route_connected_now"] is False, r["wrapper_id"]


def test_08_integration_allowed_now_false_all():
    for r in load_matrix():
        assert r["integration_allowed_now"] is False, r["wrapper_id"]


def test_09_router_import_allowed_now_false_all():
    for r in load_matrix():
        assert r["router_import_allowed_now"] is False, r["wrapper_id"]


def test_10_live_traffic_allowed_now_false_all():
    for r in load_matrix():
        assert r["live_traffic_allowed_now"] is False, r["wrapper_id"]


def test_11_dry_run_only_now_true_all():
    for r in load_matrix():
        assert r["dry_run_only_now"] is True, r["wrapper_id"]


def test_12_approval_gate_required_inbox_false_others_true():
    m = load_matrix()
    inbox = next(r for r in m if r["wrapper_id"] == "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE")
    approve = next(r for r in m if r["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE")
    reject = next(r for r in m if r["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE")
    assert inbox["approval_gate_required"] is False
    assert approve["approval_gate_required"] is True
    assert reject["approval_gate_required"] is True


def test_13_approval_gate_executed_allowed_false_all():
    for r in load_matrix():
        assert r["approval_gate_executed_allowed"] is False, r["wrapper_id"]


def test_14_rollback_required_true_all():
    for r in load_matrix():
        assert r["rollback_required"] is True, r["wrapper_id"]


# ──────────────────────────────────────────────
# 4. proposed boundary
# ──────────────────────────────────────────────

def test_15_inbox_proposed_boundary():
    m = load_matrix()
    inbox = next(r for r in m if r["wrapper_id"] == "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE")
    assert inbox["proposed_future_route_boundary"] == "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY"
    assert inbox["proposed_future_integration_point"] == "FASTAPI_ROUTE_WRAPPER_CANDIDATE_ONLY"


def test_16_approve_proposed_boundary():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE")
    assert row["proposed_future_route_boundary"] == "BEFORE_APPROVAL_SERVICE_BOUNDARY"
    assert row["proposed_future_integration_point"] == "FASTAPI_ROUTE_WRAPPER_CANDIDATE_ONLY"


def test_17_reject_proposed_boundary():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE")
    assert row["proposed_future_route_boundary"] == "BEFORE_APPROVAL_SERVICE_BOUNDARY"
    assert row["proposed_future_integration_point"] == "FASTAPI_ROUTE_WRAPPER_CANDIDATE_ONLY"


# ──────────────────────────────────────────────
# 5. path template 정합성
# ──────────────────────────────────────────────

def test_18_approve_legacy_path_has_bracket_id():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE")
    assert "<id>" in row["legacy_path_template"]


def test_19_approve_fastapi_path_has_brace_id():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE")
    assert "{id}" in row["fastapi_path_template"]


def test_20_reject_legacy_path_has_bracket_id():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE")
    assert "<id>" in row["legacy_path_template"]


def test_21_reject_fastapi_path_has_brace_id():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE")
    assert "{id}" in row["fastapi_path_template"]


def test_22_no_double_slash_approve():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE")
    assert "//" not in row["fastapi_path_template"]
    assert "//" not in row["legacy_path_template"]


def test_23_no_double_slash_reject():
    m = load_matrix()
    row = next(r for r in m if r["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE")
    assert "//" not in row["fastapi_path_template"]
    assert "//" not in row["legacy_path_template"]


# ──────────────────────────────────────────────
# 6. 제외 route 검증
# ──────────────────────────────────────────────

def test_24_execute_not_in_phase1k_scope():
    wrapper_ids = [r["wrapper_id"] for r in load_matrix()]
    assert not any("execute" in wid.lower() for wid in wrapper_ids)


def test_25_webhook_not_in_phase1k_scope():
    wrapper_ids = [r["wrapper_id"] for r in load_matrix()]
    assert not any("webhook" in wid.lower() for wid in wrapper_ids)


def test_26_dashboard_not_in_phase1k_scope():
    wrapper_ids = [r["wrapper_id"] for r in load_matrix()]
    assert not any("dashboard" in wid.lower() for wid in wrapper_ids)


def test_27_same_contract_not_in_phase1k_scope():
    wrapper_ids = [r["wrapper_id"] for r in load_matrix()]
    assert not any("same_contract" in wid.lower() for wid in wrapper_ids)


# ──────────────────────────────────────────────
# 7. forbidden_routes / stop_conditions 검증
# ──────────────────────────────────────────────

def test_28_forbidden_routes_present_all():
    for r in load_matrix():
        assert len(r["forbidden_routes"]) > 0, r["wrapper_id"]


def test_29_stop_conditions_present_all():
    for r in load_matrix():
        assert len(r["stop_conditions"]) > 0, r["wrapper_id"]


def test_30_feature_flag_default_true_stop_condition():
    for r in load_matrix():
        combined = " ".join(r["stop_conditions"])
        assert "feature_flag_default_true" in combined, r["wrapper_id"]


def test_31_route_import_stop_condition():
    for r in load_matrix():
        combined = " ".join(r["stop_conditions"])
        assert "route_import" in combined, r["wrapper_id"]


def test_32_db_write_stop_condition():
    for r in load_matrix():
        combined = " ".join(r["stop_conditions"])
        assert "db" in combined.lower() or "DB" in combined, r["wrapper_id"]


def test_33_secret_env_stop_condition():
    for r in load_matrix():
        combined = " ".join(r["stop_conditions"])
        assert "secret" in combined.lower() or "env" in combined.lower(), r["wrapper_id"]


def test_34_approval_gate_executed_stop_condition_approve_reject():
    m = load_matrix()
    for wid in ["TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE", "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE"]:
        row = next(r for r in m if r["wrapper_id"] == wid)
        combined = " ".join(row["stop_conditions"])
        assert "approval_gate_executed" in combined, wid


def test_35_double_slash_stop_condition_approve_reject():
    m = load_matrix()
    for wid in ["TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE", "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE"]:
        row = next(r for r in m if r["wrapper_id"] == wid)
        combined = " ".join(row["stop_conditions"])
        assert "double_slash" in combined, wid


# ──────────────────────────────────────────────
# 8. static route import scan
# ──────────────────────────────────────────────

def test_36_static_scan_no_violations():
    m = load_audit()
    result = m.run_static_route_import_scan()
    assert result["verdict"] == "PASS", f"violations: {result['violations']}"


def test_37_no_route_router_file_imports_wrapper():
    """route/router 파일이 wrapper candidate를 import하지 않음
    (route_integration은 Phase 1-L 지정 소비자 레이어로 제외)
    """
    m = load_audit()
    result = m.run_static_route_import_scan()
    for v in result["violations"]:
        f = v["file"].replace("\\", "/")
        if "route_integration" in f:
            continue  # Phase 1-L 지정 wrapper 소비자 레이어는 허용
        assert not any(x in f for x in ["router", "route", "handler", "service", "usecase"]), \
            f"route/router file imports wrapper: {v}"


def test_38_no_fastapi_handler_modification():
    """FastAPI handler 파일이 wrapper를 import하지 않음 (정적 확인)"""
    m = load_audit()
    result = m.run_static_route_import_scan()
    assert result["verdict"] == "PASS"


def test_39_no_flask_route_modification():
    """Flask route 파일이 wrapper를 import하지 않음 (정적 확인)"""
    m = load_audit()
    result = m.run_static_route_import_scan()
    assert result["verdict"] == "PASS"


# ──────────────────────────────────────────────
# 9. 금지 import 정적 확인 (audit 스크립트 자체)
# ──────────────────────────────────────────────

def _read_audit_source():
    audit_path = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1k_wrapper_route_integration_preflight.py"
    return audit_path.read_text(encoding="utf-8")


def test_40_no_http_client_import():
    src = _read_audit_source()
    forbidden = ["import requests", "import httpx", "import urllib.request", "import aiohttp"]
    for f in forbidden:
        assert f not in src, f"HTTP client import found: {f}"


def test_41_no_db_client_import():
    src = _read_audit_source()
    forbidden = ["import psycopg2", "import sqlalchemy", "import pymysql", "import sqlite3", "import motor"]
    for f in forbidden:
        assert f not in src, f"DB client import found: {f}"


def test_42_no_subprocess_socket_import():
    src = _read_audit_source()
    forbidden = ["import subprocess", "import socket"]
    for f in forbidden:
        assert f not in src, f"subprocess/socket import found: {f}"


def test_43_no_os_environ_value_access():
    """os.environ 값 직접 조회 없음 (os.environ.get 형태 금지)"""
    src = _read_audit_source()
    assert "os.environ.get" not in src
    assert "os.environ[" not in src


def test_44_no_feature_flag_runtime_hook():
    src = _read_audit_source()
    # runtime hook 연결 패턴
    assert "app.state" not in src
    assert "add_middleware" not in src
    assert "include_router" not in src


def test_45_no_server_startup_code():
    src = _read_audit_source()
    assert "uvicorn.run" not in src
    assert "app.run(" not in src
    assert "gunicorn" not in src


def test_46_no_uvicorn_gunicorn():
    src = _read_audit_source()
    assert "uvicorn" not in src
    assert "gunicorn" not in src


# ──────────────────────────────────────────────
# 10. Phase 회귀 파일 존재 확인
# ──────────────────────────────────────────────

def test_47_phase1i_smoke_runner_exists():
    p = REPO_ROOT / "scripts" / "ops" / "smoke_5050_phase1i_staging_dry_run_internal.py"
    assert p.exists()


def test_48_phase1h_wrapper_candidate_exists():
    for fname in [
        "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
        "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
        "backend/compat/legacy_5050/wrappers/common.py",
    ]:
        assert (REPO_ROOT / fname).exists(), fname


def test_49_phase1g_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1g_adapter_unit_implementation.py"
    assert p.exists()


def test_50_phase1f_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1f_adapter_skeleton_only.py"
    assert p.exists()


def test_51_phase1e_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1e_adapter_implementation_plan.py"
    assert p.exists()


def test_52_phase1d_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1d_adapter_dry_run_compat.py"
    assert p.exists()


def test_53_phase1b_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"
    assert p.exists()


def test_54_phase1_contract_freeze_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"
    assert p.exists()


def test_55_characterization_audit_exists():
    p = REPO_ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"
    assert p.exists()


# ──────────────────────────────────────────────
# 11. overall verdict
# ──────────────────────────────────────────────

def test_56_overall_verdict_preflight_ready():
    m = load_audit()
    errors = m.validate_matrix()
    scan = m.run_static_route_import_scan()
    verdict = m.get_overall_verdict(errors, scan)
    assert verdict == "PHASE1K_WRAPPER_ROUTE_INTEGRATION_PREFLIGHT_READY", \
        f"verdict={verdict}, errors={errors}, violations={scan['violations']}"


def test_57_known_baseline_failures_not_in_phase1k():
    """known baseline 6개 실패는 Phase 1-K 범위 밖"""
    known = [
        "test_app_foundation_p1_gates",
        "test_cad_local_agent_adapter_20260509",
        "test_mcp_local_cad_adapter_tools_20260509",
    ]
    # Phase 1-K wrapper_id 목록
    ids = [r["wrapper_id"] for r in load_matrix()]
    for k in known:
        assert not any(k in wid.lower() for wid in ids)
