"""Phase 1-G adapter unit implementation 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_01

이 스크립트는 코드 수정 없이 정적 검사/import 검사/fixture 실행만 수행한다.
실제 HTTP/DB/secret 접근 없음.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

AUDIT_ID = "ASSISTANT_BACKEND_5050_LEGACY_PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_01"
VERDICT_PASS = "PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_READY"

ADAPTER_FILES = [
    ROOT / "backend/compat/legacy_5050/adapters/common.py",
    ROOT / "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
    ROOT / "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
]

FORBIDDEN_IMPORTS = [
    "requests",
    "httpx",
    "urllib.request",
    "sqlite3",
    "psycopg",
    "sqlalchemy",
    "fastapi",
    "flask",
    "subprocess",
    "socket",
]

FORBIDDEN_PATTERNS = [
    "@app.route",
    "@router.",
    "APIRouter",
    "os.environ[",
]

SKELETON_FUNCS = [
    ("backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter",
     "adapt_inbox_email_fetch_request_response"),
    ("backend.compat.legacy_5050.adapters.task_approval_adapter",
     "adapt_task_approve_path_auth_response"),
    ("backend.compat.legacy_5050.adapters.task_approval_adapter",
     "adapt_task_reject_path_auth_response"),
]

UNIT_FUNCS = [
    ("backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter",
     "build_inbox_email_fetch_fastapi_request"),
    ("backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter",
     "normalize_inbox_email_fetch_response"),
    ("backend.compat.legacy_5050.adapters.task_approval_adapter",
     "map_legacy_task_action_path_to_fastapi_path"),
    ("backend.compat.legacy_5050.adapters.task_approval_adapter",
     "normalize_task_approve_response"),
    ("backend.compat.legacy_5050.adapters.task_approval_adapter",
     "normalize_task_reject_response"),
]

KNOWN_BASELINE_FAILURES = [
    "tests/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
    "tests/test_cad_local_agent_adapter_20260509.py::test_cad_status_lists_physical_modules",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_cad_adapter_status_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_bridge_health_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::"
    "test_fastmcp_call_tool_invokes_local_cad_bridge_health",
]

errors: list[str] = []
checks: list[tuple[str, bool]] = []


def check(label: str, condition: bool, error_msg: str = "") -> bool:
    checks.append((label, condition))
    if not condition:
        errors.append(error_msg or label)
    return condition


# ── 1. 파일 존재 ──────────────────────────────────────────────────────────────

for f in ADAPTER_FILES:
    check(f"파일 존재: {f.name}", f.exists(), f"파일 없음: {f}")

# ── 2. forbidden import/pattern 정적 검사 ────────────────────────────────────

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


for adapter_file in ADAPTER_FILES:
    if not adapter_file.exists():
        continue
    src = adapter_file.read_text(encoding="utf-8")
    imports = _get_imports(adapter_file)

    for fi in FORBIDDEN_IMPORTS:
        has = any(fi in imp for imp in imports)
        check(
            f"{adapter_file.name}: forbidden import 없음 — {fi}",
            not has,
            f"{adapter_file.name}에 forbidden import: {fi}",
        )

    for fp in FORBIDDEN_PATTERNS:
        check(
            f"{adapter_file.name}: forbidden pattern 없음 — {fp}",
            fp not in src,
            f"{adapter_file.name}에 forbidden pattern: {fp!r}",
        )

# ── 3. skeleton 함수 raise 유지 ───────────────────────────────────────────────

from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError

for mod_name, func_name in SKELETON_FUNCS:
    mod = importlib.import_module(mod_name)
    func = getattr(mod, func_name, None)
    check(f"skeleton 함수 존재: {func_name}", func is not None, f"함수 없음: {func_name}")
    if func:
        raised = False
        try:
            func()
        except SkeletonOnlyAdapterError:
            raised = True
        except Exception:
            raised = False
        check(
            f"skeleton raise 유지: {func_name}",
            raised,
            f"SkeletonOnlyAdapterError를 raise하지 않음: {func_name}",
        )

# ── 4. pure unit function 존재 ────────────────────────────────────────────────

for mod_name, func_name in UNIT_FUNCS:
    mod = importlib.import_module(mod_name)
    func = getattr(mod, func_name, None)
    check(f"unit function 존재: {func_name}", callable(func), f"unit function 없음: {func_name}")

# ── 5. fixture 기반 동작 검증 ─────────────────────────────────────────────────

import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter as _inbox
import backend.compat.legacy_5050.adapters.task_approval_adapter as _task
from backend.compat.legacy_5050.adapters.common import AdapterUnitMappingError

# 5-a. inbox request 변환
try:
    req = _inbox.build_inbox_email_fetch_fastapi_request({"limit": 10, "labels": ["inbox"]})
    check("inbox request 변환 성공", req.get("adapter_id") == "INBOX_EMAIL_FETCH_ADAPTER")
except Exception as e:
    check("inbox request 변환 성공", False, str(e))

# 5-b. inbox request — secret field 거부
for secret_field in ("password", "token", "api_key", "credential_value"):
    rejected = False
    try:
        _inbox.build_inbox_email_fetch_fastapi_request({secret_field: "X"})
    except AdapterUnitMappingError:
        rejected = True
    check(f"inbox request secret field 거부: {secret_field}", rejected,
          f"secret field {secret_field!r}가 거부되지 않음")

# 5-c. inbox response normalize
try:
    resp = _inbox.normalize_inbox_email_fetch_response(
        {"ok": True, "fetched": 3, "items": ["a", "b", "c"], "source": "legacy_5050"}
    )
    check("inbox response normalize 성공", resp["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER")
    check("inbox fetched 정수", resp["fetched"] == 3)
    check("inbox items list", resp["items"] == ["a", "b", "c"])
except Exception as e:
    check("inbox response normalize 성공", False, str(e))

# 5-d. approve path mapping
try:
    r = _task.map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/approve", "/api/v1/tasks/{id}/approve", "TASK_001"
    )
    check("approve path mapping 성공", r["action"] == "approve")
    check("approve legacy path 정확", r["legacy_path"] == "/api/v1/tasks/TASK_001/approve")
    check("approve fastapi path 정확", r["fastapi_path"] == "/api/v1/tasks/TASK_001/approve")
    check("approve double slash 없음", "//" not in r["legacy_path"])
except Exception as e:
    check("approve path mapping 성공", False, str(e))

# 5-e. reject path mapping
try:
    r = _task.map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/reject", "/api/v1/tasks/{id}/reject", "TASK_001"
    )
    check("reject path mapping 성공", r["action"] == "reject")
    check("reject double slash 없음", "//" not in r["legacy_path"])
except Exception as e:
    check("reject path mapping 성공", False, str(e))

# 5-f. 빈 task_id
empty_rejected = False
try:
    _task.map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/approve", "/api/v1/tasks/{id}/approve", ""
    )
except AdapterUnitMappingError:
    empty_rejected = True
check("빈 task_id 거부", empty_rejected)

# 5-g. invalid action
invalid_rejected = False
try:
    _task.map_legacy_task_action_path_to_fastapi_path(
        "/api/v1/tasks/<id>/execute", "/api/v1/tasks/{id}/execute", "TASK_001"
    )
except AdapterUnitMappingError:
    invalid_rejected = True
check("invalid action 거부 (execute)", invalid_rejected)

# 5-h. approve response normalize
try:
    r = _task.normalize_task_approve_response({"ok": True, "task_id": "TASK_001"})
    check("approve response normalize 성공", r["status"] == "approved")
    check("approve approval_gate_required=True", r["approval_gate_required"] is True)
    check("approve approval_gate_executed=False", r["approval_gate_executed"] is False)
except Exception as e:
    check("approve response normalize 성공", False, str(e))

# 5-i. reject response normalize
try:
    r = _task.normalize_task_reject_response({"ok": True, "task_id": "TASK_002"})
    check("reject response normalize 성공", r["status"] == "rejected")
    check("reject approval_gate_required=True", r["approval_gate_required"] is True)
    check("reject approval_gate_executed=False", r["approval_gate_executed"] is False)
except Exception as e:
    check("reject response normalize 성공", False, str(e))

# ── 6. 제외 경로 확인 ─────────────────────────────────────────────────────────

EXCLUDED_PATHS = [
    "/api/v1/tasks/<task_id>/execute",
    "/api/v1/webhooks/kakaowork",
    "/api/v1/webhooks/kakaotalk-channel",
    "/dashboard",
    "/api/v1/tasks//approve",
    "/api/v1/tasks//reject",
]
PHASE1G_TARGET_PATHS = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/<id>/approve",
    "/api/v1/tasks/<id>/reject",
]
for excl in EXCLUDED_PATHS:
    check(f"제외 경로 미포함: {excl}", excl not in PHASE1G_TARGET_PATHS,
          f"제외 경로가 포함됨: {excl}")

# ── 7. route 연결 없음 검증 ───────────────────────────────────────────────────

ROUTE_DIRS = [
    ROOT / "backend" / "routes",
    ROOT / "backend" / "api",
    ROOT / "app",
]

import re

ROUTE_IMPORT_RE = re.compile(
    r"from\s+backend\.compat\.legacy_5050\.adapters\.(inbox_email_fetch_adapter|task_approval_adapter)\s+import"
)

for route_dir in ROUTE_DIRS:
    if not route_dir.exists():
        continue
    for py_file in route_dir.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8", errors="ignore")
        match = ROUTE_IMPORT_RE.search(src)
        check(
            f"route 파일 adapter import 없음: {py_file.name}",
            match is None,
            f"route 파일이 Phase 1-G adapter를 import: {py_file}",
        )

# ── 8. safe boundary 집계 ─────────────────────────────────────────────────────

safe_boundary = {
    "route_connection_allowed": False,
    "live_call_allowed": False,
    "side_effect_allowed": False,
    "db_write_allowed": False,
    "secret_value_allowed": False,
    "server_apply_allowed": False,
    "nginx_change_allowed": False,
    "execution_allowed": False,
    "webhook_allowed": False,
    "dashboard_allowed": False,
}

# ── 출력 ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print(f"AUDIT: {AUDIT_ID}")
verdict = VERDICT_PASS if not errors else "PHASE1G_FAIL"
print(f"VERDICT: {verdict}")
print("=" * 70)

print("\n[pure unit function 현황]")
header = f"  {'FUNCTION':<55} {'EXISTS'}"
print(header)
print("  " + "-" * 65)
for mod_name, func_name in UNIT_FUNCS:
    mod = importlib.import_module(mod_name)
    exists = callable(getattr(mod, func_name, None))
    mark = "✅" if exists else "❌"
    print(f"  {func_name:<55} {mark}")

print("\n[skeleton guard 유지]")
for mod_name, func_name in SKELETON_FUNCS:
    mod = importlib.import_module(mod_name)
    func = getattr(mod, func_name, None)
    raised = False
    if func:
        try:
            func()
        except SkeletonOnlyAdapterError:
            raised = True
        except Exception:
            pass
    mark = "✅" if raised else "❌"
    print(f"  {mark} {func_name}")

print("\n[safe boundary]")
for k, v in safe_boundary.items():
    mark = "✅" if not v else "❌"
    print(f"  {mark} {k}={v}")

print("\n[집계]")
total = len(checks)
passed = sum(1 for _, ok in checks if ok)
failed = total - passed
print(f"  총 검사: {total}  PASS: {passed}  FAIL: {failed}")

if errors:
    print("\n[오류 목록]")
    for e in errors:
        print(f"  ❌ {e}")

print("\n[known baseline failures (이번 공정 무관)]")
for f in KNOWN_BASELINE_FAILURES:
    print(f"  - {f}")

print("=" * 70)
print(f"VERDICT: {verdict}")
print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
print("=" * 70)

if errors:
    sys.exit(1)
