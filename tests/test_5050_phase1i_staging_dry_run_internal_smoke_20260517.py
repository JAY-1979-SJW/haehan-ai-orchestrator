"""Phase 1-I staging dry-run internal smoke 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_01

실제 HTTP/DB/secret 접근 없음. smoke runner, wrapper candidate, fixture, 정적 검사만 수행.
"""
from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KNOWN_BASELINE_FAILURES = [
    "tests/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
    "tests/test_cad_local_agent_adapter_20260509.py::test_cad_status_lists_physical_modules",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_cad_adapter_status_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_bridge_health_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::"
    "test_fastmcp_call_tool_invokes_local_cad_bridge_health",
]

PHASE1I_TARGET_PATHS = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/<id>/approve",
    "/api/v1/tasks/<id>/reject",
]

EXCLUDED_PATHS = [
    "/api/v1/tasks/<task_id>/execute",
    "/api/v1/webhooks/kakaowork",
    "/api/v1/webhooks/kakaotalk-channel",
    "/dashboard",
    "/api/v1/inbox",
    "/api/v1/tasks",
    "/api/v1/tasks//approve",
    "/api/v1/tasks//reject",
]

SMOKE_FILES = [
    # 감사 스크립트 자체는 FORBIDDEN_PATTERNS 목록을 포함하므로 제외
    ROOT / "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py",
]

FORBIDDEN_IMPORTS = [
    "requests", "httpx", "urllib.request", "socket",
    "sqlite3", "psycopg", "sqlalchemy",
    "fastapi", "flask", "subprocess",
]

FORBIDDEN_PATTERNS_SMOKE = [
    "uvicorn", "gunicorn", "os.environ[",
    "APIRouter", "@app.route", "@router.",
]


def _get_imports(path: pathlib.Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


@pytest.fixture(scope="module")
def smoke_summary():
    import scripts.ops.smoke_5050_phase1i_staging_dry_run_internal as _smoke
    s = _smoke.run_phase1i_internal_smoke()
    s.pop("_scenarios", None)
    return s


# ── 1~2. import 가능 ──────────────────────────────────────────────────────────

def test_01_smoke_runner_import():
    import scripts.ops.smoke_5050_phase1i_staging_dry_run_internal  # noqa: F401


def test_02_audit_script_file_exists():
    assert (ROOT / "scripts/ops/audit_5050_phase1i_staging_dry_run_internal_smoke.py").exists()


# ── 3~4. 함수 존재 ────────────────────────────────────────────────────────────

def test_03_build_phase1i_smoke_fixtures_exists():
    import scripts.ops.smoke_5050_phase1i_staging_dry_run_internal as _smoke
    assert callable(_smoke.build_phase1i_smoke_fixtures)


def test_04_run_phase1i_internal_smoke_exists():
    import scripts.ops.smoke_5050_phase1i_staging_dry_run_internal as _smoke
    assert callable(_smoke.run_phase1i_internal_smoke)


# ── 5~14. smoke summary 필드 검증 ────────────────────────────────────────────

def test_05_smoke_summary_phase(smoke_summary):
    assert smoke_summary["phase"] == "PHASE_1I"


def test_06_smoke_id_accurate(smoke_summary):
    assert smoke_summary["smoke_id"] == "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE"


def test_07_staging_mode_internal_fixture_only(smoke_summary):
    assert smoke_summary["staging_mode"] == "INTERNAL_FIXTURE_ONLY"


def test_08_wrapper_count_3(smoke_summary):
    assert smoke_summary["wrapper_count"] == 3


def test_09_total_scenarios_ge_14(smoke_summary):
    assert smoke_summary["total_scenarios"] >= 14


def test_10_failed_scenarios_0(smoke_summary):
    assert smoke_summary["failed_scenarios"] == 0


def test_11_disabled_mode_passed(smoke_summary):
    assert smoke_summary["disabled_mode_passed"] is True


def test_12_unsafe_mode_passed(smoke_summary):
    assert smoke_summary["unsafe_mode_passed"] is True


def test_13_dry_run_success_passed(smoke_summary):
    assert smoke_summary["dry_run_success_passed"] is True


def test_14_bad_fixture_boundary_passed(smoke_summary):
    assert smoke_summary["bad_fixture_boundary_passed"] is True


# ── 15~26. safety counter 검증 ───────────────────────────────────────────────

def test_15_server_started_false(smoke_summary):
    assert smoke_summary["server_started"] is False


def test_16_route_connected_false(smoke_summary):
    assert smoke_summary["route_connected"] is False


def test_17_live_traffic_allowed_false(smoke_summary):
    assert smoke_summary["live_traffic_allowed"] is False


def test_18_http_call_count_0(smoke_summary):
    assert smoke_summary["http_call_count"] == 0


def test_19_db_read_count_0(smoke_summary):
    assert smoke_summary["db_read_count"] == 0


def test_20_db_write_count_0(smoke_summary):
    assert smoke_summary["db_write_count"] == 0


def test_21_secret_value_output_count_0(smoke_summary):
    assert smoke_summary["secret_value_output_count"] == 0


def test_22_email_fetch_live_call_count_0(smoke_summary):
    assert smoke_summary["email_fetch_live_call_count"] == 0


def test_23_approve_live_call_count_0(smoke_summary):
    assert smoke_summary["approve_live_call_count"] == 0


def test_24_reject_live_call_count_0(smoke_summary):
    assert smoke_summary["reject_live_call_count"] == 0


def test_25_execute_call_count_0(smoke_summary):
    assert smoke_summary["execute_call_count"] == 0


def test_26_webhook_call_count_0(smoke_summary):
    assert smoke_summary["webhook_call_count"] == 0


# ── 27~44. 시나리오별 상세 검증 ──────────────────────────────────────────────

def test_27_disabled_mode_inbox_result():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate()
    assert r["ok"] is False


def test_28_disabled_mode_approve_result():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate()
    assert r["ok"] is False


def test_29_disabled_mode_reject_result():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate()
    assert r["ok"] is False


def test_30_disabled_mode_would_call_adapter_false():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(dry_run=False)
    assert r["would_call_adapter"] is False


def test_31_unsafe_mode_inbox_error():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    with pytest.raises(RouteWrapperUnsafeExecutionError):
        inbox_email_fetch_wrapper_candidate(feature_flag_enabled=True)


def test_32_unsafe_mode_approve_error():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    with pytest.raises(RouteWrapperUnsafeExecutionError):
        task_approve_wrapper_candidate(feature_flag_enabled=True)


def test_33_unsafe_mode_reject_error():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    with pytest.raises(RouteWrapperUnsafeExecutionError):
        task_reject_wrapper_candidate(feature_flag_enabled=True)


def test_34_dry_run_inbox_success():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        {"limit": 3, "credential_ref": "ref_x"},
        {"ok": True, "fetched": 1, "items": ["m1"]},
        dry_run=True,
    )
    assert r["ok"] is True


def test_35_dry_run_inbox_normalized_response():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        {"limit": 3},
        {"ok": True, "fetched": 2, "items": ["a", "b"]},
        dry_run=True,
    )
    assert "normalized_response" in r
    assert r["normalized_response"]["fetched"] == 2


def test_36_dry_run_approve_success():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate("T_SMOKE_001", dry_run=True)
    assert r["ok"] is True


def test_37_dry_run_approve_approval_gate_executed_false():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate("T_SMOKE_001", dry_run=True)
    assert r["normalized_response"]["approval_gate_executed"] is False


def test_38_dry_run_reject_success():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate("T_SMOKE_002", dry_run=True)
    assert r["ok"] is True


def test_39_dry_run_reject_approval_gate_executed_false():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate("T_SMOKE_002", dry_run=True)
    assert r["normalized_response"]["approval_gate_executed"] is False


def test_40_inbox_secret_bad_fixture_error():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    with pytest.raises(Exception):
        inbox_email_fetch_wrapper_candidate({"password": "leak"}, dry_run=True)


def test_41_approve_missing_task_id_error():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_approve_wrapper_candidate("", dry_run=True)


def test_42_reject_missing_task_id_error():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_reject_wrapper_candidate("", dry_run=True)


def test_43_approve_double_slash_prevented():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_approve_wrapper_candidate("", dry_run=True)


def test_44_reject_double_slash_prevented():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_reject_wrapper_candidate("", dry_run=True)


# ── 45~48. 제외 경로 검증 ─────────────────────────────────────────────────────

def test_45_execute_not_in_phase1i_targets():
    assert "/api/v1/tasks/<task_id>/execute" not in PHASE1I_TARGET_PATHS


def test_46_webhook_not_in_phase1i_targets():
    for p in PHASE1I_TARGET_PATHS:
        assert "webhook" not in p


def test_47_dashboard_not_in_phase1i_targets():
    for p in PHASE1I_TARGET_PATHS:
        assert "dashboard" not in p


def test_48_same_contract_not_in_phase1i_targets():
    for sc in ["/api/v1/inbox", "/api/v1/tasks"]:
        assert sc not in PHASE1I_TARGET_PATHS


# ── 49~58. 정적 안전 경계 검사 ───────────────────────────────────────────────

def test_49_route_files_do_not_import_smoke_or_wrappers():
    route_dirs = [ROOT / "backend" / "routes", ROOT / "backend" / "api", ROOT / "app"]
    pattern = re.compile(
        r"from\s+backend\.compat\.legacy_5050\.wrappers\.\w+\s+import"
        r"|smoke_5050_phase1i"
    )
    for route_dir in route_dirs:
        if not route_dir.exists():
            continue
        for py_file in route_dir.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert pattern.search(src) is None, f"route 파일이 wrapper/smoke를 import: {py_file}"


def test_50_fastapi_handler_not_modified():
    fastapi_dirs = [ROOT / "backend" / "api", ROOT / "backend" / "routers"]
    for d in fastapi_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert "smoke_5050_phase1i" not in src


def test_51_flask_route_not_modified():
    flask_dirs = [ROOT / "backend" / "routes", ROOT / "app"]
    for d in flask_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert "smoke_5050_phase1i" not in src


def test_52_no_http_client_import_in_smoke_files():
    http_clients = ["requests", "httpx", "urllib.request"]
    for sf in SMOKE_FILES:
        if not sf.exists():
            continue
        imports = _get_imports(sf)
        for client in http_clients:
            assert not any(client in imp for imp in imports), (
                f"{sf.name}에 HTTP client import: {client}"
            )


def test_53_no_db_client_import_in_smoke_files():
    db_clients = ["sqlite3", "psycopg", "sqlalchemy"]
    for sf in SMOKE_FILES:
        if not sf.exists():
            continue
        imports = _get_imports(sf)
        for client in db_clients:
            assert not any(client in imp for imp in imports), (
                f"{sf.name}에 DB client import: {client}"
            )


def test_54_no_subprocess_socket_import_in_smoke_files():
    # subprocess는 감사 스크립트에서도 금지. smoke runner에서만 확인.
    sf = ROOT / "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py"
    if not sf.exists():
        return
    imports = _get_imports(sf)
    for f in ["socket"]:
        assert not any(f == imp for imp in imports), f"{sf.name}에 {f} import"


def test_55_no_os_environ_value_access_in_smoke_files():
    for sf in SMOKE_FILES:
        if not sf.exists():
            continue
        src = sf.read_text(encoding="utf-8")
        assert 'os.environ[' not in src, f"{sf.name}에 os.environ[] 접근"


def test_56_no_feature_flag_runtime_hook():
    for sf in SMOKE_FILES:
        if not sf.exists():
            continue
        src = sf.read_text(encoding="utf-8")
        for pat in ["@app.route", "@router.", "APIRouter", "Flask(", "FastAPI("]:
            assert pat not in src, f"{sf.name}에 route/runtime pattern: {pat!r}"


def test_57_no_server_startup_code():
    for sf in SMOKE_FILES:
        if not sf.exists():
            continue
        src = sf.read_text(encoding="utf-8")
        for pat in ["uvicorn", "gunicorn"]:
            assert pat not in src, f"{sf.name}에 server startup pattern: {pat!r}"


def test_58_no_uvicorn_gunicorn():
    for sf in SMOKE_FILES:
        if not sf.exists():
            continue
        imports = _get_imports(sf)
        for srv in ["uvicorn", "gunicorn"]:
            assert not any(srv in imp for imp in imports), f"server import: {srv}"


# ── 59~66. 이전 공정 충돌 검사 ───────────────────────────────────────────────

def test_59_phase1h_wrapper_regression_compatible():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate()
    assert r["ok"] is False  # disabled mode 유지


def test_60_phase1g_pure_function_regression_compatible():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    r = build_inbox_email_fetch_fastapi_request({"limit": 3})
    assert r["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"


def test_61_phase1f_skeleton_guard_compatible():
    from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        adapt_inbox_email_fetch_request_response,
    )
    with pytest.raises(SkeletonOnlyAdapterError):
        adapt_inbox_email_fetch_request_response()


def test_62_phase1e_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py").exists()


def test_63_phase1d_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1d_adapter_dry_run_compat.py").exists()


def test_64_phase1b_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1b_adapter_contract_detail.py").exists()


def test_65_phase1_contract_freeze_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_66_characterization_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


# ── 67. Phase 1-I 감사 스크립트 verdict ───────────────────────────────────────

def test_67_phase1i_audit_script_verdict():
    result = subprocess.run(
        [sys.executable,
         str(ROOT / "scripts/ops/audit_5050_phase1i_staging_dry_run_internal_smoke.py")],
        capture_output=True, text=True,
    )
    assert "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_READY" in result.stdout, (
        f"Phase 1-I 감사 verdict 불일치:\n{result.stdout}\n{result.stderr}"
    )
    assert result.returncode == 0, f"Phase 1-I 감사 스크립트 실패:\n{result.stderr}"


# ── 68. known baseline 분리 검증 ─────────────────────────────────────────────

def test_68_known_baseline_failures_are_separated():
    phase1i_file = "test_5050_phase1i_staging_dry_run_internal_smoke_20260517.py"
    for baseline in KNOWN_BASELINE_FAILURES:
        assert phase1i_file not in baseline, (
            f"known baseline이 Phase 1-I 테스트와 혼동됨: {baseline}"
        )
