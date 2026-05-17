"""Phase 1-H route wrapper candidate feature flag OFF 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_01

실제 HTTP/DB/secret 접근 없음. wrapper candidate, metadata, fixture, 정적 검사만 수행.
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

PHASE1H_TARGET_PATHS = [
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

WRAPPER_FILES = [
    ROOT / "backend/compat/legacy_5050/wrappers/common.py",
    ROOT / "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
    ROOT / "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
]

FORBIDDEN_IMPORTS = [
    "requests", "httpx", "urllib.request",
    "sqlite3", "psycopg", "sqlalchemy",
    "fastapi", "flask", "subprocess", "socket",
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


# ── 1. wrappers package import ────────────────────────────────────────────────

def test_01_wrappers_package_import():
    import backend.compat.legacy_5050.wrappers  # noqa: F401


# ── 2. wrappers/common.py import ─────────────────────────────────────────────

def test_02_wrappers_common_import():
    import backend.compat.legacy_5050.wrappers.common  # noqa: F401


# ── 3~5. 예외 존재 ────────────────────────────────────────────────────────────

def test_03_route_wrapper_candidate_error_exists():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperCandidateError
    assert issubclass(RouteWrapperCandidateError, Exception)


def test_04_route_wrapper_disabled_error_exists():
    from backend.compat.legacy_5050.wrappers.common import (
        RouteWrapperCandidateError,
        RouteWrapperDisabledError,
    )
    assert issubclass(RouteWrapperDisabledError, RouteWrapperCandidateError)


def test_05_route_wrapper_unsafe_execution_error_exists():
    from backend.compat.legacy_5050.wrappers.common import (
        RouteWrapperCandidateError,
        RouteWrapperUnsafeExecutionError,
    )
    assert issubclass(RouteWrapperUnsafeExecutionError, RouteWrapperCandidateError)


# ── 6~7. wrapper module import ────────────────────────────────────────────────

def test_06_inbox_wrapper_module_import():
    import backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate  # noqa: F401


def test_07_task_approval_wrapper_module_import():
    import backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate  # noqa: F401


# ── 8~10. metadata 함수 존재 ──────────────────────────────────────────────────

def test_08_inbox_wrapper_metadata_exists():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        get_inbox_email_fetch_wrapper_metadata,
    )
    assert callable(get_inbox_email_fetch_wrapper_metadata)


def test_09_approve_wrapper_metadata_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        get_task_approve_wrapper_metadata,
    )
    assert callable(get_task_approve_wrapper_metadata)


def test_10_reject_wrapper_metadata_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        get_task_reject_wrapper_metadata,
    )
    assert callable(get_task_reject_wrapper_metadata)


# ── 11~13. wrapper candidate 함수 존재 ───────────────────────────────────────

def test_11_inbox_wrapper_candidate_exists():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    assert callable(inbox_email_fetch_wrapper_candidate)


def test_12_approve_wrapper_candidate_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    assert callable(task_approve_wrapper_candidate)


def test_13_reject_wrapper_candidate_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    assert callable(task_reject_wrapper_candidate)


# ── 14~17. 상수 검증 ─────────────────────────────────────────────────────────

def test_14_feature_flag_default_false_all_three():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        FEATURE_FLAG_DEFAULT,
    )
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        APPROVE_FEATURE_FLAG_DEFAULT,
        REJECT_FEATURE_FLAG_DEFAULT,
    )
    assert FEATURE_FLAG_DEFAULT is False
    assert APPROVE_FEATURE_FLAG_DEFAULT is False
    assert REJECT_FEATURE_FLAG_DEFAULT is False


def test_15_route_connected_false_all_three():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        ROUTE_CONNECTED,
    )
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        APPROVE_ROUTE_CONNECTED,
        REJECT_ROUTE_CONNECTED,
    )
    assert ROUTE_CONNECTED is False
    assert APPROVE_ROUTE_CONNECTED is False
    assert REJECT_ROUTE_CONNECTED is False


def test_16_live_traffic_allowed_false_all_three():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        LIVE_TRAFFIC_ALLOWED,
    )
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        APPROVE_LIVE_TRAFFIC_ALLOWED,
        REJECT_LIVE_TRAFFIC_ALLOWED,
    )
    assert LIVE_TRAFFIC_ALLOWED is False
    assert APPROVE_LIVE_TRAFFIC_ALLOWED is False
    assert REJECT_LIVE_TRAFFIC_ALLOWED is False


def test_17_dry_run_allowed_true_all_three():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        DRY_RUN_ALLOWED,
    )
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        APPROVE_DRY_RUN_ALLOWED,
        REJECT_DRY_RUN_ALLOWED,
    )
    assert DRY_RUN_ALLOWED is True
    assert APPROVE_DRY_RUN_ALLOWED is True
    assert REJECT_DRY_RUN_ALLOWED is True


# ── 18~21. disabled result ────────────────────────────────────────────────────

def test_18_inbox_dry_run_false_disabled_result():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate()
    assert r["ok"] is False


def test_19_approve_dry_run_false_disabled_result():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate()
    assert r["ok"] is False


def test_20_reject_dry_run_false_disabled_result():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate()
    assert r["ok"] is False


def test_21_disabled_result_would_call_adapter_false():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(dry_run=False)
    assert r["would_call_adapter"] is False


# ── 22~24. feature_flag_enabled=True unsafe error ─────────────────────────────

def test_22_inbox_feature_flag_true_unsafe_error():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    with pytest.raises(RouteWrapperUnsafeExecutionError):
        inbox_email_fetch_wrapper_candidate(feature_flag_enabled=True)


def test_23_approve_feature_flag_true_unsafe_error():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    with pytest.raises(RouteWrapperUnsafeExecutionError):
        task_approve_wrapper_candidate(feature_flag_enabled=True)


def test_24_reject_feature_flag_true_unsafe_error():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    with pytest.raises(RouteWrapperUnsafeExecutionError):
        task_reject_wrapper_candidate(feature_flag_enabled=True)


# ── 25~30. inbox dry-run fixture ──────────────────────────────────────────────

def test_25_inbox_dry_run_true_fixture_success():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture={"limit": 5},
        legacy_response_fixture={"ok": True, "fetched": 2, "items": ["a", "b"]},
        dry_run=True,
    )
    assert r["ok"] is True


def test_26_inbox_dry_run_route_connected_false():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture={"limit": 3}, dry_run=True
    )
    assert r["route_connected"] is False


def test_27_inbox_dry_run_feature_flag_enabled_false():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture={"limit": 3}, dry_run=True
    )
    assert r["feature_flag_enabled"] is False


def test_28_inbox_dry_run_fastapi_request_exists():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture={"limit": 3}, dry_run=True
    )
    assert "fastapi_request" in r


def test_29_inbox_dry_run_normalized_response_exists():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    r = inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture={"limit": 3},
        legacy_response_fixture={"fetched": 1, "items": ["x"]},
        dry_run=True,
    )
    assert "normalized_response" in r


def test_30_inbox_secret_field_raises_error():
    from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
        inbox_email_fetch_wrapper_candidate,
    )
    with pytest.raises(Exception):
        inbox_email_fetch_wrapper_candidate(
            legacy_request_fixture={"password": "secret"},
            dry_run=True,
        )


# ── 31~37. approve dry-run fixture ───────────────────────────────────────────

def test_31_approve_dry_run_true_fixture_success():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate(task_id="T001", dry_run=True)
    assert r["ok"] is True


def test_32_approve_dry_run_path_mapping_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate(task_id="T001", dry_run=True)
    assert "path_mapping" in r


def test_33_approve_dry_run_normalized_response_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate(task_id="T001", dry_run=True)
    assert "normalized_response" in r


def test_34_approve_approval_gate_required_true():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate(task_id="T001", dry_run=True)
    assert r["normalized_response"]["approval_gate_required"] is True


def test_35_approve_approval_gate_executed_false():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate(task_id="T001", dry_run=True)
    assert r["normalized_response"]["approval_gate_executed"] is False


def test_36_approve_sample_path_no_double_slash():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    r = task_approve_wrapper_candidate(task_id="T001", dry_run=True)
    assert "//" not in r["path_mapping"]["legacy_path"]
    assert "//" not in r["path_mapping"]["fastapi_path"]


def test_37_approve_task_id_empty_raises_error():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_approve_wrapper_candidate(task_id="", dry_run=True)


# ── 38~44. reject dry-run fixture ────────────────────────────────────────────

def test_38_reject_dry_run_true_fixture_success():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate(task_id="T002", dry_run=True)
    assert r["ok"] is True


def test_39_reject_dry_run_path_mapping_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate(task_id="T002", dry_run=True)
    assert "path_mapping" in r


def test_40_reject_dry_run_normalized_response_exists():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate(task_id="T002", dry_run=True)
    assert "normalized_response" in r


def test_41_reject_approval_gate_required_true():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate(task_id="T002", dry_run=True)
    assert r["normalized_response"]["approval_gate_required"] is True


def test_42_reject_approval_gate_executed_false():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate(task_id="T002", dry_run=True)
    assert r["normalized_response"]["approval_gate_executed"] is False


def test_43_reject_sample_path_no_double_slash():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    r = task_reject_wrapper_candidate(task_id="T002", dry_run=True)
    assert "//" not in r["path_mapping"]["legacy_path"]
    assert "//" not in r["path_mapping"]["fastapi_path"]


def test_44_reject_task_id_empty_raises_error():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_reject_wrapper_candidate(task_id="", dry_run=True)


# ── 45~46. double slash 생성 금지 ────────────────────────────────────────────

def test_45_no_double_slash_approve_path():
    from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_approve_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_approve_wrapper_candidate(task_id="", dry_run=True)


def test_46_no_double_slash_reject_path():
    from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
        task_reject_wrapper_candidate,
    )
    with pytest.raises(Exception):
        task_reject_wrapper_candidate(task_id="", dry_run=True)


# ── 47~50. 제외 경로 검증 ─────────────────────────────────────────────────────

def test_47_execute_not_in_phase1h_targets():
    assert "/api/v1/tasks/<task_id>/execute" not in PHASE1H_TARGET_PATHS


def test_48_webhook_not_in_phase1h_targets():
    for p in PHASE1H_TARGET_PATHS:
        assert "webhook" not in p


def test_49_dashboard_not_in_phase1h_targets():
    for p in PHASE1H_TARGET_PATHS:
        assert "dashboard" not in p


def test_50_same_contract_not_in_phase1h_targets():
    for sc in ["/api/v1/inbox", "/api/v1/tasks"]:
        assert sc not in PHASE1H_TARGET_PATHS


# ── 51~58. 정적 안전 경계 검사 ───────────────────────────────────────────────

def test_51_route_files_do_not_import_phase1h_wrappers():
    route_dirs = [ROOT / "backend" / "routes", ROOT / "backend" / "api", ROOT / "app"]
    pattern = re.compile(
        r"from\s+backend\.compat\.legacy_5050\.wrappers\."
        r"(inbox_email_fetch_wrapper_candidate|task_approval_wrapper_candidate)\s+import"
    )
    for route_dir in route_dirs:
        if not route_dir.exists():
            continue
        for py_file in route_dir.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert pattern.search(src) is None, (
                f"route 파일이 Phase 1-H wrapper를 import: {py_file}"
            )


def test_52_fastapi_handler_not_modified():
    fastapi_dirs = [ROOT / "backend" / "api", ROOT / "backend" / "routers"]
    for d in fastapi_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert "task_approval_wrapper_candidate" not in src, (
                f"FastAPI handler가 wrapper import: {py_file}"
            )


def test_53_flask_route_not_modified():
    flask_dirs = [ROOT / "backend" / "routes", ROOT / "app"]
    for d in flask_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert "inbox_email_fetch_wrapper_candidate" not in src, (
                f"Flask route가 wrapper import: {py_file}"
            )


def test_54_no_http_client_import_in_wrapper_files():
    http_clients = ["requests", "httpx", "urllib.request"]
    for wf in WRAPPER_FILES:
        if not wf.exists():
            continue
        imports = _get_imports(wf)
        for client in http_clients:
            assert not any(client in imp for imp in imports), (
                f"{wf.name}에 HTTP client import: {client}"
            )


def test_55_no_db_client_import_in_wrapper_files():
    db_clients = ["sqlite3", "psycopg", "sqlalchemy"]
    for wf in WRAPPER_FILES:
        if not wf.exists():
            continue
        imports = _get_imports(wf)
        for client in db_clients:
            assert not any(client in imp for imp in imports), (
                f"{wf.name}에 DB client import: {client}"
            )


def test_56_no_subprocess_socket_import_in_wrapper_files():
    forbidden = ["subprocess", "socket"]
    for wf in WRAPPER_FILES:
        if not wf.exists():
            continue
        imports = _get_imports(wf)
        for f in forbidden:
            assert not any(f == imp for imp in imports), (
                f"{wf.name}에 {f} import"
            )


def test_57_no_os_environ_value_access_in_wrapper_files():
    for wf in WRAPPER_FILES:
        if not wf.exists():
            continue
        src = wf.read_text(encoding="utf-8")
        assert 'os.environ[' not in src, (
            f"{wf.name}에 os.environ[] 직접 접근 있음"
        )


def test_58_no_feature_flag_runtime_hook_in_wrapper_files():
    forbidden_patterns = ["@app.route", "@router.", "APIRouter", "Flask(", "FastAPI("]
    for wf in WRAPPER_FILES:
        if not wf.exists():
            continue
        src = wf.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            assert pat not in src, (
                f"{wf.name}에 route/runtime pattern: {pat!r}"
            )


# ── 59~65. 이전 공정 충돌 검사 ───────────────────────────────────────────────

def test_59_phase1g_pure_function_regression_compatible():
    """Phase 1-G pure function이 여전히 정상 동작."""
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    r = build_inbox_email_fetch_fastapi_request({"limit": 3})
    assert r["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"


def test_60_phase1f_skeleton_guard_compatible():
    """Phase 1-F skeleton guard가 여전히 raise."""
    from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        adapt_inbox_email_fetch_request_response,
    )
    with pytest.raises(SkeletonOnlyAdapterError):
        adapt_inbox_email_fetch_request_response()


def test_61_phase1e_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py").exists()


def test_62_phase1d_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1d_adapter_dry_run_compat.py").exists()


def test_63_phase1b_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1b_adapter_contract_detail.py").exists()


def test_64_phase1_contract_freeze_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_65_characterization_audit_compatible():
    assert (ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


# ── 66. Phase 1-H 감사 스크립트 verdict 검증 ─────────────────────────────────

def test_66_phase1h_audit_script_verdict():
    result = subprocess.run(
        [sys.executable,
         str(ROOT / "scripts/ops/audit_5050_phase1h_route_wrapper_candidate_feature_flag_off.py")],
        capture_output=True, text=True,
    )
    assert "PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_READY" in result.stdout, (
        f"Phase 1-H 감사 verdict 불일치:\n{result.stdout}\n{result.stderr}"
    )
    assert result.returncode == 0, f"Phase 1-H 감사 스크립트 실패:\n{result.stderr}"


# ── 67. known baseline 분리 검증 ─────────────────────────────────────────────

def test_67_known_baseline_failures_are_separated():
    phase1h_test_file = "test_5050_phase1h_route_wrapper_candidate_feature_flag_off_20260517.py"
    for baseline in KNOWN_BASELINE_FAILURES:
        assert phase1h_test_file not in baseline, (
            f"known baseline이 Phase 1-H 테스트와 혼동됨: {baseline}"
        )
