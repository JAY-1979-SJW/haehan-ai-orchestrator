"""Phase 1-N: Route Integration Final Preflight Tests (2026-05-17).

[ASSISTANT_BACKEND_5050_LEGACY_PHASE1N_ROUTE_INTEGRATION_FINAL_PREFLIGHT_BEFORE_REAL_ROUTER_TOUCH_01]

실제 router 수정 없음. HTTP/DB/secret/env 접근 없음.
final preflight matrix, router candidate inventory, 정적 검사만 수행.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_audit():
    import scripts.ops.audit_5050_phase1n_route_integration_final_preflight as m
    return m


def matrix():
    return load_audit().FINAL_PREFLIGHT_MATRIX


def _row(sid):
    for r in matrix():
        if r["route_skeleton_id"] == sid:
            return r
    return None


INBOX   = "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON"
APPROVE = "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON"
REJECT  = "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"

# ── 1~2. import / row 수 ──────────────────────────────────────────────────────

def test_01_audit_importable():
    assert load_audit() is not None


def test_02_matrix_exactly_3_rows():
    assert len(matrix()) == 3


# ── 3~5. route_skeleton_id ────────────────────────────────────────────────────

def test_03_inbox_skeleton_id():
    assert _row(INBOX) is not None


def test_04_approve_skeleton_id():
    assert _row(APPROVE) is not None


def test_05_reject_skeleton_id():
    assert _row(REJECT) is not None


# ── 6~8. wrapper_id ──────────────────────────────────────────────────────────

def test_06_inbox_wrapper_id():
    assert _row(INBOX)["wrapper_id"] == "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE"


def test_07_approve_wrapper_id():
    assert _row(APPROVE)["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE"


def test_08_reject_wrapper_id():
    assert _row(REJECT)["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE"


# ── 9~11. adapter_id ─────────────────────────────────────────────────────────

def test_09_inbox_adapter_id():
    assert _row(INBOX)["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"


def test_10_approve_adapter_id():
    assert _row(APPROVE)["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"


def test_11_reject_adapter_id():
    assert _row(REJECT)["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"


# ── 12~14. feature_flag ───────────────────────────────────────────────────────

def test_12_inbox_feature_flag():
    assert _row(INBOX)["feature_flag"] == "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED"


def test_13_approve_feature_flag():
    assert _row(APPROVE)["feature_flag"] == "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED"


def test_14_reject_feature_flag():
    assert _row(REJECT)["feature_flag"] == "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED"


# ── 15~17. feature_flag_default=false ────────────────────────────────────────

def test_15_inbox_feature_flag_default_false():
    assert _row(INBOX)["feature_flag_default"] is False


def test_16_approve_feature_flag_default_false():
    assert _row(APPROVE)["feature_flag_default"] is False


def test_17_reject_feature_flag_default_false():
    assert _row(REJECT)["feature_flag_default"] is False


# ── 18~20. route_registered_now=false ────────────────────────────────────────

def test_18_inbox_route_registered_false():
    assert _row(INBOX)["route_registered_now"] is False


def test_19_approve_route_registered_false():
    assert _row(APPROVE)["route_registered_now"] is False


def test_20_reject_route_registered_false():
    assert _row(REJECT)["route_registered_now"] is False


# ── 21~23. real_router_touch_allowed_now=false ───────────────────────────────

def test_21_inbox_real_router_touch_false():
    assert _row(INBOX)["real_router_touch_allowed_now"] is False


def test_22_approve_real_router_touch_false():
    assert _row(APPROVE)["real_router_touch_allowed_now"] is False


def test_23_reject_real_router_touch_false():
    assert _row(REJECT)["real_router_touch_allowed_now"] is False


# ── 24~26. include_router/decorator/hook/live_traffic/dry_run ────────────────

def test_24_all_include_router_allowed_false():
    for r in matrix():
        assert r["include_router_allowed_now"] is False, r["route_skeleton_id"]


def test_25_all_route_decorator_allowed_false():
    for r in matrix():
        assert r["route_decorator_allowed_now"] is False, r["route_skeleton_id"]


def test_26_all_feature_flag_runtime_hook_false():
    for r in matrix():
        assert r["feature_flag_runtime_hook_allowed_now"] is False, r["route_skeleton_id"]


def test_27_all_live_traffic_allowed_false():
    for r in matrix():
        assert r["live_traffic_allowed_now"] is False, r["route_skeleton_id"]


def test_28_all_dry_run_only_true():
    for r in matrix():
        assert r["dry_run_only_now"] is True, r["route_skeleton_id"]


# ── 29~31. approval gate ─────────────────────────────────────────────────────

def test_29_approve_approval_gate_required_true():
    assert _row(APPROVE)["approval_gate_required"] is True


def test_30_reject_approval_gate_required_true():
    assert _row(REJECT)["approval_gate_required"] is True


def test_31_all_approval_gate_executed_allowed_false():
    for r in matrix():
        assert r["approval_gate_executed_allowed"] is False, r["route_skeleton_id"]


# ── 32~34. proposed_future_integration_boundary ──────────────────────────────

def test_32_inbox_boundary():
    assert _row(INBOX)["proposed_future_integration_boundary"] == "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY"


def test_33_approve_boundary():
    assert _row(APPROVE)["proposed_future_integration_boundary"] == "BEFORE_APPROVAL_SERVICE_BOUNDARY"


def test_34_reject_boundary():
    assert _row(REJECT)["proposed_future_integration_boundary"] == "BEFORE_APPROVAL_SERVICE_BOUNDARY"


# ── 35~40. path template 형식 ────────────────────────────────────────────────

def test_35_approve_legacy_has_angle_id():
    assert "<id>" in _row(APPROVE)["legacy_path_template"]


def test_36_approve_fastapi_has_brace_id():
    assert "{id}" in _row(APPROVE)["fastapi_path_template"]


def test_37_reject_legacy_has_angle_id():
    assert "<id>" in _row(REJECT)["legacy_path_template"]


def test_38_reject_fastapi_has_brace_id():
    assert "{id}" in _row(REJECT)["fastapi_path_template"]


def test_39_approve_no_double_slash():
    assert "//" not in _row(APPROVE)["fastapi_path_template"]


def test_40_reject_no_double_slash():
    assert "//" not in _row(REJECT)["fastapi_path_template"]


# ── 41~44. 금지 route 제외 ───────────────────────────────────────────────────

def test_41_execute_not_in_matrix():
    ids = [r["route_skeleton_id"].lower() for r in matrix()]
    assert not any("execute" in i for i in ids)


def test_42_webhook_not_in_matrix():
    ids = [r["route_skeleton_id"].lower() for r in matrix()]
    assert not any("webhook" in i for i in ids)


def test_43_dashboard_not_in_matrix():
    ids = [r["route_skeleton_id"].lower() for r in matrix()]
    assert not any("dashboard" in i for i in ids)


def test_44_same_contract_not_in_matrix():
    ids = [r["route_skeleton_id"].lower() for r in matrix()]
    assert not any("same_contract" in i for i in ids)


# ── 45~50. forbidden_routes / stop_conditions ────────────────────────────────

def test_45_forbidden_routes_in_all_rows():
    for r in matrix():
        assert len(r["forbidden_routes"]) > 0, r["route_skeleton_id"]


def test_46_stop_conditions_in_all_rows():
    for r in matrix():
        assert len(r["stop_conditions"]) > 0, r["route_skeleton_id"]


def test_47_feature_flag_default_true_stop_condition():
    for r in matrix():
        conds = " ".join(r["stop_conditions"])
        assert "feature flag default true" in conds, r["route_skeleton_id"]


def test_48_route_decorator_stop_condition():
    for r in matrix():
        conds = " ".join(r["stop_conditions"])
        assert "route decorator" in conds, r["route_skeleton_id"]


def test_49_include_router_stop_condition():
    for r in matrix():
        conds = " ".join(r["stop_conditions"])
        assert "include_router" in conds, r["route_skeleton_id"]


def test_50_db_write_stop_condition():
    for r in matrix():
        conds = " ".join(r["stop_conditions"])
        assert "DB write" in conds, r["route_skeleton_id"]


def test_51_secret_env_stop_condition():
    for r in matrix():
        conds = " ".join(r["stop_conditions"])
        assert "secret" in conds or "env" in conds, r["route_skeleton_id"]


def test_52_approval_gate_executed_stop_condition():
    # approve/reject에만 있음
    for sid in [APPROVE, REJECT]:
        conds = " ".join(_row(sid)["stop_conditions"])
        assert "approval gate executed" in conds, sid


def test_53_double_slash_stop_condition():
    for sid in [APPROVE, REJECT]:
        conds = " ".join(_row(sid)["stop_conditions"])
        assert "double slash" in conds, sid


def test_54_external_site_cookie_stop_condition():
    conds = " ".join(_row(INBOX)["stop_conditions"])
    assert "cookie" in conds.lower()


def test_55_external_site_approval_gate_stop_condition():
    for sid in [APPROVE, REJECT]:
        conds = " ".join(_row(sid)["stop_conditions"])
        assert "external site" in conds, sid


# ── 56~57. router candidate inventory ────────────────────────────────────────

def test_56_router_candidate_inventory_exists():
    scan = load_audit().scan_router_candidates()
    assert "candidate_count" in scan
    assert scan["scan_readonly"] is True


def test_57_router_candidate_scan_no_modification():
    scan = load_audit().scan_router_candidates()
    assert scan["files_modified"] is False


# ── 58~73. 정적 안전 경계 ────────────────────────────────────────────────────

def _read_src():
    # smoke runner 파일 검사 — audit 스크립트 자체는 패턴 목록 문자열을 포함하므로 제외
    p = REPO_ROOT / "scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py"
    return p.read_text(encoding="utf-8")


def test_58_no_fastapi_handler_modification():
    assert "= FastAPI(" not in _read_src()


def test_59_no_flask_route_modification():
    assert "= Flask(" not in _read_src()
    assert "@app.route" not in _read_src()


def test_60_no_apirouter():
    assert "= APIRouter(" not in _read_src()


def test_61_no_include_router():
    assert "include_router(" not in _read_src()


def test_62_no_route_decorator():
    assert "@router.get" not in _read_src()
    assert "@router.post" not in _read_src()


def test_63_no_http_client_import():
    src = _read_src()
    assert "import requests" not in src
    assert "import httpx" not in src
    assert "import urllib.request" not in src


def test_64_no_db_client_import():
    src = _read_src()
    assert "import sqlite3" not in src
    assert "import psycopg" not in src


def test_65_no_subprocess_socket():
    src = _read_src()
    assert "import subprocess" not in src
    assert "import socket" not in src


def test_66_no_os_environ_value():
    src = _read_src()
    assert "os.environ[" not in src
    assert "os.environ.get(" not in src


def test_67_no_feature_flag_runtime_hook():
    src = _read_src()
    assert "app.state" not in src
    assert "add_middleware" not in src


def test_68_no_server_startup():
    src = _read_src()
    assert "uvicorn.run(" not in src
    assert "app.run(" not in src


def test_69_no_uvicorn_gunicorn():
    src = _read_src()
    assert "uvicorn" not in src
    assert "gunicorn" not in src


# ── 74~76. external site registry 충돌 없음 ──────────────────────────────────

def test_70_gabia_cookie_storage_false():
    from ai_orchestrator.external_sites.provider_registry import get_provider
    p = get_provider("GABIA")
    assert p.cookie_storage_allowed is False


def test_71_all_provider_server_remote_login_false():
    from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY
    for p in PROVIDER_REGISTRY:
        assert p.server_remote_login_allowed is False, p.provider_id


def test_72_critical_gates_auto_execute_false():
    from ai_orchestrator.external_sites.approval_gate_registry import assert_all_critical_gates_blocked
    assert assert_all_critical_gates_blocked() == []


# ── 77~79. Phase 회귀 파일 존재 ──────────────────────────────────────────────

def test_73_phase1m_smoke_exists():
    assert (REPO_ROOT / "scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py").exists()


def test_74_phase1l_skeletons_exist():
    for f in [
        "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
        "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
    ]:
        assert (REPO_ROOT / f).exists(), f


def test_75_phase1k_audit_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1k_wrapper_route_integration_preflight.py").exists()


# ── known baseline 분리 ───────────────────────────────────────────────────────

def test_76_known_baseline_not_in_phase1n():
    known = [
        "test_app_foundation_p1_gates",
        "test_cad_local_agent_adapter_20260509",
        "test_mcp_local_cad_adapter_tools_20260509",
    ]
    audit = load_audit()
    smoke_id = audit.PREFLIGHT_ID
    for k in known:
        assert k not in smoke_id.lower()


# ── 최종 audit verdict ────────────────────────────────────────────────────────

def test_77_audit_overall_verdict_ready():
    a = load_audit()
    matrix_errors = a.check_matrix_integrity()
    static_scan = a.run_static_pattern_scan()
    phase1m_errors = a.check_phase1m_smoke_ready()
    ext_errors = a.check_external_site_registry()
    verdict = a.get_overall_verdict([], static_scan, matrix_errors, phase1m_errors, ext_errors)
    assert verdict == a.VERDICT_READY, (
        f"verdict={verdict} matrix={matrix_errors} "
        f"static={static_scan['violations']} phase1m={phase1m_errors} ext={ext_errors}"
    )
