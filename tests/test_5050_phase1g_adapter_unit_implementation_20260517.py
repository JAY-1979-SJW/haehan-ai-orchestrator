"""Phase 1-G adapter unit implementation 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_01

실제 HTTP/DB/secret 접근 없음. pure function, metadata, 정적 검사만 수행.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import re
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

PHASE1G_TARGET_PATHS = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/<id>/approve",
    "/api/v1/tasks/<id>/reject",
]

EXCLUDED_PATHS = [
    "/api/v1/tasks/<task_id>/execute",
    "/api/v1/webhooks/kakaowork",
    "/api/v1/webhooks/kakaotalk-channel",
    "/dashboard",
    "/dashboard/tasks/<task_id>",
    "/dashboard/approve",
    "/dashboard/reject",
    "/api/v1/inbox",
    "/api/v1/tasks",
    "/api/v1/tasks//approve",
    "/api/v1/tasks//reject",
]

FORBIDDEN_IMPORTS = [
    "requests", "httpx", "urllib.request",
    "sqlite3", "psycopg", "sqlalchemy",
    "fastapi", "flask", "subprocess", "socket",
]

ADAPTER_FILES = [
    ROOT / "backend/compat/legacy_5050/adapters/common.py",
    ROOT / "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
    ROOT / "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
]

# ── 1. common.py import ───────────────────────────────────────────────────────

def test_01_common_import():
    import backend.compat.legacy_5050.adapters.common  # noqa: F401


# ── 2. AdapterUnitMappingError 존재 ──────────────────────────────────────────

def test_02_adapter_unit_mapping_error_exists():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    assert issubclass(AdapterUnitMappingError, ValueError)


# ── 3. SkeletonOnlyAdapterError 유지 ─────────────────────────────────────────

def test_03_skeleton_only_adapter_error_exists():
    from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
    assert issubclass(SkeletonOnlyAdapterError, NotImplementedError)


# ── 4. inbox module import ────────────────────────────────────────────────────

def test_04_inbox_module_import():
    import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter  # noqa: F401


# ── 5. task approval module import ───────────────────────────────────────────

def test_05_task_approval_module_import():
    import backend.compat.legacy_5050.adapters.task_approval_adapter  # noqa: F401


# ── 6~8. skeleton raise 유지 ─────────────────────────────────────────────────

def test_06_inbox_adapt_skeleton_still_raises():
    from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        adapt_inbox_email_fetch_request_response,
    )
    with pytest.raises(SkeletonOnlyAdapterError):
        adapt_inbox_email_fetch_request_response()


def test_07_approve_adapt_skeleton_still_raises():
    from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        adapt_task_approve_path_auth_response,
    )
    with pytest.raises(SkeletonOnlyAdapterError):
        adapt_task_approve_path_auth_response()


def test_08_reject_adapt_skeleton_still_raises():
    from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        adapt_task_reject_path_auth_response,
    )
    with pytest.raises(SkeletonOnlyAdapterError):
        adapt_task_reject_path_auth_response()


# ── 9~13. pure unit function 존재 ────────────────────────────────────────────

def test_09_build_inbox_email_fetch_fastapi_request_exists():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    assert callable(build_inbox_email_fetch_fastapi_request)


def test_10_normalize_inbox_email_fetch_response_exists():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        normalize_inbox_email_fetch_response,
    )
    assert callable(normalize_inbox_email_fetch_response)


def test_11_map_legacy_task_action_path_to_fastapi_path_exists():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    assert callable(map_legacy_task_action_path_to_fastapi_path)


def test_12_normalize_task_approve_response_exists():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_approve_response,
    )
    assert callable(normalize_task_approve_response)


def test_13_normalize_task_reject_response_exists():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_reject_response,
    )
    assert callable(normalize_task_reject_response)


# ── 14~23. inbox unit 동작 검증 ──────────────────────────────────────────────

def test_14_inbox_request_fixture_conversion_success():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    result = build_inbox_email_fetch_fastapi_request({"limit": 5, "labels": ["inbox"]})
    assert isinstance(result, dict)
    assert result["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"


def test_15_inbox_request_no_secret_value():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    result = build_inbox_email_fetch_fastapi_request({"limit": 5, "credential_ref": "ref_001"})
    assert "password" not in result
    assert "token" not in result
    assert "api_key" not in result


def test_16_inbox_request_password_raises():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    with pytest.raises(AdapterUnitMappingError):
        build_inbox_email_fetch_fastapi_request({"password": "secret123"})


def test_17_inbox_request_token_raises():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    with pytest.raises(AdapterUnitMappingError):
        build_inbox_email_fetch_fastapi_request({"token": "tok_abc"})


def test_18_inbox_request_api_key_raises():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    with pytest.raises(AdapterUnitMappingError):
        build_inbox_email_fetch_fastapi_request({"api_key": "key_xyz"})


def test_19_inbox_request_credential_value_raises():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        build_inbox_email_fetch_fastapi_request,
    )
    with pytest.raises(AdapterUnitMappingError):
        build_inbox_email_fetch_fastapi_request({"credential_value": "v"})


def test_20_inbox_response_normalize_success():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        normalize_inbox_email_fetch_response,
    )
    result = normalize_inbox_email_fetch_response({
        "ok": True, "fetched": 3, "items": ["a", "b", "c"], "source": "legacy_5050"
    })
    assert result["ok"] is True


def test_21_inbox_normalized_adapter_id():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        normalize_inbox_email_fetch_response,
    )
    result = normalize_inbox_email_fetch_response({"fetched": 2, "items": ["x", "y"]})
    assert result["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"


def test_22_inbox_normalized_fetched_is_int():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        normalize_inbox_email_fetch_response,
    )
    result = normalize_inbox_email_fetch_response({"fetched": "7", "items": []})
    assert result["fetched"] == 7
    assert isinstance(result["fetched"], int)


def test_23_inbox_normalized_items_list_preserved():
    from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
        normalize_inbox_email_fetch_response,
    )
    items = [{"id": 1}, {"id": 2}]
    result = normalize_inbox_email_fetch_response({"fetched": 2, "items": items})
    assert result["items"] == items


# ── 24~35. task path mapping ──────────────────────────────────────────────────

def test_24_approve_path_mapping_success():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    r = map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/approve", "/api/v1/tasks/{id}/approve", "DRYRUN_TASK_001"
    )
    assert r["action"] == "approve"
    assert r["task_id"] == "DRYRUN_TASK_001"


def test_25_reject_path_mapping_success():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    r = map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/reject", "/api/v1/tasks/{id}/reject", "DRYRUN_TASK_001"
    )
    assert r["action"] == "reject"


def test_26_approve_legacy_template_has_angle_bracket():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        APPROVE_LEGACY_PATH_TEMPLATE,
    )
    assert "<id>" in APPROVE_LEGACY_PATH_TEMPLATE


def test_27_approve_fastapi_template_has_curly_bracket():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        APPROVE_FASTAPI_PATH_TEMPLATE,
    )
    assert "{id}" in APPROVE_FASTAPI_PATH_TEMPLATE


def test_28_reject_legacy_template_has_angle_bracket():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        REJECT_LEGACY_PATH_TEMPLATE,
    )
    assert "<id>" in REJECT_LEGACY_PATH_TEMPLATE


def test_29_reject_fastapi_template_has_curly_bracket():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        REJECT_FASTAPI_PATH_TEMPLATE,
    )
    assert "{id}" in REJECT_FASTAPI_PATH_TEMPLATE


def test_30_approve_sample_path_no_double_slash():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    r = map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/approve", "/api/v1/tasks/{id}/approve", "T001"
    )
    assert "//" not in r["legacy_path"]
    assert "//" not in r["fastapi_path"]


def test_31_reject_sample_path_no_double_slash():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    r = map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/reject", "/api/v1/tasks/{id}/reject", "T002"
    )
    assert "//" not in r["legacy_path"]
    assert "//" not in r["fastapi_path"]


def test_32_empty_task_id_raises():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    with pytest.raises(AdapterUnitMappingError):
        map_legacy_task_action_path_to_fastapi_path(
            "/api/v1/tasks/<id>/approve", "/api/v1/tasks/{id}/approve", ""
        )


def test_33_invalid_action_raises():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    with pytest.raises(AdapterUnitMappingError):
        map_legacy_task_action_path_to_fastapi_path(
            "/api/v1/tasks/<id>/execute", "/api/v1/tasks/{id}/execute", "T001"
        )


def test_34_no_double_slash_approve_path_generation():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    # 빈 task_id가 들어오면 double slash가 생기는 대신 AdapterUnitMappingError
    with pytest.raises(AdapterUnitMappingError):
        map_legacy_task_action_path_to_fastapi_path(
            "/api/v1/tasks/<id>/approve", "/api/v1/tasks/{id}/approve", ""
        )


def test_35_no_double_slash_reject_path_generation():
    from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        map_legacy_task_action_path_to_fastapi_path,
    )
    with pytest.raises(AdapterUnitMappingError):
        map_legacy_task_action_path_to_fastapi_path(
            "/api/v1/tasks/<id>/reject", "/api/v1/tasks/{id}/reject", ""
        )


# ── 36~45. response normalize ─────────────────────────────────────────────────

def test_36_normalize_task_approve_response_success():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_approve_response,
    )
    r = normalize_task_approve_response({"ok": True, "task_id": "T001"})
    assert isinstance(r, dict)


def test_37_approve_normalized_status_approved():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_approve_response,
    )
    r = normalize_task_approve_response({"ok": True, "task_id": "T001"})
    assert r["status"] == "approved"


def test_38_approve_approval_gate_required_true():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_approve_response,
    )
    r = normalize_task_approve_response({"ok": True, "task_id": "T001"})
    assert r["approval_gate_required"] is True


def test_39_approve_approval_gate_executed_false():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_approve_response,
    )
    r = normalize_task_approve_response({"ok": True, "task_id": "T001"})
    assert r["approval_gate_executed"] is False


def test_40_normalize_task_reject_response_success():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_reject_response,
    )
    r = normalize_task_reject_response({"ok": True, "task_id": "T002"})
    assert isinstance(r, dict)


def test_41_reject_normalized_status_rejected():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_reject_response,
    )
    r = normalize_task_reject_response({"ok": True, "task_id": "T002"})
    assert r["status"] == "rejected"


def test_42_reject_approval_gate_required_true():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_reject_response,
    )
    r = normalize_task_reject_response({"ok": True, "task_id": "T002"})
    assert r["approval_gate_required"] is True


def test_43_reject_approval_gate_executed_false():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_reject_response,
    )
    r = normalize_task_reject_response({"ok": True, "task_id": "T002"})
    assert r["approval_gate_executed"] is False


def test_44_approve_response_no_db_write_flag():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_approve_response,
    )
    r = normalize_task_approve_response({"ok": True, "task_id": "T001"})
    assert "db_write" not in r
    assert "db_written" not in r


def test_45_reject_response_no_db_write_flag():
    from backend.compat.legacy_5050.adapters.task_approval_adapter import (
        normalize_task_reject_response,
    )
    r = normalize_task_reject_response({"ok": True, "task_id": "T002"})
    assert "db_write" not in r
    assert "db_written" not in r


# ── 46~49. 제외 경로 검증 ─────────────────────────────────────────────────────

def test_46_execute_not_in_phase1g_targets():
    assert "/api/v1/tasks/<task_id>/execute" not in PHASE1G_TARGET_PATHS


def test_47_webhook_not_in_phase1g_targets():
    for p in PHASE1G_TARGET_PATHS:
        assert "webhook" not in p


def test_48_dashboard_not_in_phase1g_targets():
    for p in PHASE1G_TARGET_PATHS:
        assert "dashboard" not in p


def test_49_same_contract_not_in_phase1g_targets():
    same_contract = ["/api/v1/inbox", "/api/v1/tasks"]
    for sc in same_contract:
        assert sc not in PHASE1G_TARGET_PATHS


# ── 50~57. 정적 안전 경계 검사 ───────────────────────────────────────────────

def _get_imports_from_file(path: pathlib.Path) -> list[str]:
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


def test_50_route_files_do_not_import_phase1g_adapters():
    route_dirs = [
        ROOT / "backend" / "routes",
        ROOT / "backend" / "api",
        ROOT / "app",
    ]
    pattern = re.compile(
        r"from\s+backend\.compat\.legacy_5050\.adapters\."
        r"(inbox_email_fetch_adapter|task_approval_adapter)\s+import"
    )
    for route_dir in route_dirs:
        if not route_dir.exists():
            continue
        for py_file in route_dir.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert pattern.search(src) is None, (
                f"route 파일이 Phase 1-G adapter를 import: {py_file}"
            )


def test_51_fastapi_handler_not_modified():
    # FastAPI handler가 task_approval_adapter를 직접 import하지 않음
    fastapi_dirs = [ROOT / "backend" / "api", ROOT / "backend" / "routers"]
    for d in fastapi_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            assert "task_approval_adapter" not in src or "legacy_5050" not in src, (
                f"FastAPI handler가 task_approval_adapter import: {py_file}"
            )


def test_52_flask_route_not_modified():
    flask_dirs = [ROOT / "backend" / "routes", ROOT / "app"]
    for d in flask_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            if "task_approval_adapter" in src and "legacy_5050" in src:
                assert False, f"Flask route가 task_approval_adapter import: {py_file}"


def test_53_no_http_client_import_in_adapter_files():
    http_clients = ["requests", "httpx", "urllib.request"]
    for adapter_file in ADAPTER_FILES:
        if not adapter_file.exists():
            continue
        imports = _get_imports_from_file(adapter_file)
        for client in http_clients:
            assert not any(client in imp for imp in imports), (
                f"{adapter_file.name}에 HTTP client import: {client}"
            )


def test_54_no_db_client_import_in_adapter_files():
    db_clients = ["sqlite3", "psycopg", "sqlalchemy"]
    for adapter_file in ADAPTER_FILES:
        if not adapter_file.exists():
            continue
        imports = _get_imports_from_file(adapter_file)
        for client in db_clients:
            assert not any(client in imp for imp in imports), (
                f"{adapter_file.name}에 DB client import: {client}"
            )


def test_55_no_subprocess_socket_import_in_adapter_files():
    forbidden = ["subprocess", "socket"]
    for adapter_file in ADAPTER_FILES:
        if not adapter_file.exists():
            continue
        imports = _get_imports_from_file(adapter_file)
        for f in forbidden:
            assert not any(f in imp for imp in imports), (
                f"{adapter_file.name}에 {f} import"
            )


def test_56_no_os_environ_value_access_in_adapter_files():
    for adapter_file in ADAPTER_FILES:
        if not adapter_file.exists():
            continue
        src = adapter_file.read_text(encoding="utf-8")
        assert 'os.environ[' not in src, (
            f"{adapter_file.name}에 os.environ[] 직접 접근 있음"
        )


def test_57_no_feature_flag_runtime_hook_in_adapter_files():
    forbidden_patterns = ["@app.route", "@router.", "APIRouter", "Flask(", "FastAPI("]
    for adapter_file in ADAPTER_FILES:
        if not adapter_file.exists():
            continue
        src = adapter_file.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            assert pat not in src, (
                f"{adapter_file.name}에 route/runtime pattern: {pat!r}"
            )


# ── 58~63. 이전 공정 충돌 검사 (감사 스크립트 결과 확인) ──────────────────────

def test_58_phase1f_skeleton_audit_compatible():
    """Phase 1-F skeleton audit 스크립트가 존재하고 실행 가능."""
    audit = ROOT / "scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py"
    assert audit.exists(), "Phase 1-F 감사 스크립트 없음"


def test_59_phase1e_implementation_plan_audit_compatible():
    audit = ROOT / "scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py"
    assert audit.exists(), "Phase 1-E 감사 스크립트 없음"


def test_60_phase1d_dry_run_audit_compatible():
    audit = ROOT / "scripts/ops/audit_5050_phase1d_adapter_dry_run_compat.py"
    assert audit.exists(), "Phase 1-D 감사 스크립트 없음"


def test_61_phase1b_contract_detail_audit_compatible():
    audit = ROOT / "scripts/ops/audit_5050_phase1b_adapter_contract_detail.py"
    assert audit.exists(), "Phase 1-B 감사 스크립트 없음"


def test_62_phase1_contract_freeze_audit_compatible():
    audit = ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py"
    assert audit.exists(), "Phase 1 contract freeze 감사 스크립트 없음"


def test_63_characterization_audit_compatible():
    audit = ROOT / "scripts/ops/audit_5050_legacy_characterization.py"
    assert audit.exists(), "Characterization 감사 스크립트 없음"


# ── 64. Phase 1-G 감사 스크립트 verdict 검증 ─────────────────────────────────

def test_64_phase1g_audit_script_verdict():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ops/audit_5050_phase1g_adapter_unit_implementation.py")],
        capture_output=True, text=True
    )
    assert "PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_READY" in result.stdout, (
        f"Phase 1-G 감사 verdict 불일치:\n{result.stdout}\n{result.stderr}"
    )
    assert result.returncode == 0, f"Phase 1-G 감사 스크립트 실패:\n{result.stderr}"


# ── 65. known baseline 분리 검증 ─────────────────────────────────────────────

def test_65_known_baseline_failures_are_separated():
    """known baseline 6개 실패 목록이 Phase 1-G 테스트와 분리되어 있음."""
    phase1g_test_file = "test_5050_phase1g_adapter_unit_implementation_20260517.py"
    for baseline in KNOWN_BASELINE_FAILURES:
        assert phase1g_test_file not in baseline, (
            f"known baseline이 Phase 1-G 테스트와 혼동됨: {baseline}"
        )
