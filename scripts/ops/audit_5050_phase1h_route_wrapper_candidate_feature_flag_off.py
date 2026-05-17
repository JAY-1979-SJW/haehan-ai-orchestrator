"""Phase 1-H route wrapper candidate feature flag OFF 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_01

이 스크립트는 코드 수정 없이 정적 검사/import 검사/fixture 실행만 수행한다.
실제 HTTP/DB/secret 접근 없음.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

AUDIT_ID = (
    "ASSISTANT_BACKEND_5050_LEGACY_PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_01"
)
VERDICT_PASS = "PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_READY"

WRAPPER_FILES = [
    ROOT / "backend/compat/legacy_5050/wrappers/__init__.py",
    ROOT / "backend/compat/legacy_5050/wrappers/common.py",
    ROOT / "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
    ROOT / "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
]

FORBIDDEN_IMPORTS = [
    "requests", "httpx", "urllib.request",
    "sqlite3", "psycopg", "sqlalchemy",
    "fastapi", "flask", "subprocess", "socket",
]

FORBIDDEN_PATTERNS = [
    "@app.route", "@router.", "APIRouter",
    "os.environ[",
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

PHASE1H_TARGET_PATHS = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/<id>/approve",
    "/api/v1/tasks/<id>/reject",
]

errors: list[str] = []
checks: list[tuple[str, bool]] = []


def check(label: str, condition: bool, error_msg: str = "") -> bool:
    checks.append((label, condition))
    if not condition:
        errors.append(error_msg or label)
    return condition


# ── 1. 파일 존재 ──────────────────────────────────────────────────────────────

for f in WRAPPER_FILES:
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


for wf in WRAPPER_FILES:
    if not wf.exists():
        continue
    src = wf.read_text(encoding="utf-8")
    imports = _get_imports(wf)
    for fi in FORBIDDEN_IMPORTS:
        has = any(fi in imp for imp in imports)
        check(
            f"{wf.name}: forbidden import 없음 — {fi}",
            not has,
            f"{wf.name}에 forbidden import: {fi}",
        )
    for fp in FORBIDDEN_PATTERNS:
        check(
            f"{wf.name}: forbidden pattern 없음 — {fp}",
            fp not in src,
            f"{wf.name}에 forbidden pattern: {fp!r}",
        )


# ── 3. module import 및 상수 검증 ────────────────────────────────────────────

import backend.compat.legacy_5050.wrappers.common as _wc
import backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate as _inbox_w
import backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate as _task_w

check("FEATURE_FLAG_DEFAULT_ENABLED=False", _wc.FEATURE_FLAG_DEFAULT_ENABLED is False)
check("ROUTE_CONNECTED=False", _wc.ROUTE_CONNECTED is False)
check("LIVE_TRAFFIC_ALLOWED=False", _wc.LIVE_TRAFFIC_ALLOWED is False)
check("DRY_RUN_ALLOWED=True", _wc.DRY_RUN_ALLOWED is True)

check("inbox FEATURE_FLAG_DEFAULT=False", _inbox_w.FEATURE_FLAG_DEFAULT is False)
check("inbox ROUTE_CONNECTED=False", _inbox_w.ROUTE_CONNECTED is False)
check("inbox LIVE_TRAFFIC_ALLOWED=False", _inbox_w.LIVE_TRAFFIC_ALLOWED is False)
check("inbox DRY_RUN_ALLOWED=True", _inbox_w.DRY_RUN_ALLOWED is True)

check("approve FEATURE_FLAG_DEFAULT=False", _task_w.APPROVE_FEATURE_FLAG_DEFAULT is False)
check("approve ROUTE_CONNECTED=False", _task_w.APPROVE_ROUTE_CONNECTED is False)
check("approve LIVE_TRAFFIC_ALLOWED=False", _task_w.APPROVE_LIVE_TRAFFIC_ALLOWED is False)
check("approve DRY_RUN_ALLOWED=True", _task_w.APPROVE_DRY_RUN_ALLOWED is True)

check("reject FEATURE_FLAG_DEFAULT=False", _task_w.REJECT_FEATURE_FLAG_DEFAULT is False)
check("reject ROUTE_CONNECTED=False", _task_w.REJECT_ROUTE_CONNECTED is False)
check("reject LIVE_TRAFFIC_ALLOWED=False", _task_w.REJECT_LIVE_TRAFFIC_ALLOWED is False)
check("reject DRY_RUN_ALLOWED=True", _task_w.REJECT_DRY_RUN_ALLOWED is True)


# ── 4. 예외 존재 ──────────────────────────────────────────────────────────────

from backend.compat.legacy_5050.wrappers.common import (
    RouteWrapperCandidateError,
    RouteWrapperDisabledError,
    RouteWrapperUnsafeExecutionError,
)

check("RouteWrapperCandidateError 존재", issubclass(RouteWrapperCandidateError, Exception))
check("RouteWrapperDisabledError 존재", issubclass(RouteWrapperDisabledError, RouteWrapperCandidateError))
check("RouteWrapperUnsafeExecutionError 존재", issubclass(RouteWrapperUnsafeExecutionError, RouteWrapperCandidateError))


# ── 5. metadata 함수 존재 ─────────────────────────────────────────────────────

check("get_inbox_email_fetch_wrapper_metadata 존재", callable(getattr(_inbox_w, "get_inbox_email_fetch_wrapper_metadata", None)))
check("get_task_approve_wrapper_metadata 존재", callable(getattr(_task_w, "get_task_approve_wrapper_metadata", None)))
check("get_task_reject_wrapper_metadata 존재", callable(getattr(_task_w, "get_task_reject_wrapper_metadata", None)))


# ── 6. wrapper candidate 함수 존재 ───────────────────────────────────────────

check("inbox_email_fetch_wrapper_candidate 존재", callable(getattr(_inbox_w, "inbox_email_fetch_wrapper_candidate", None)))
check("task_approve_wrapper_candidate 존재", callable(getattr(_task_w, "task_approve_wrapper_candidate", None)))
check("task_reject_wrapper_candidate 존재", callable(getattr(_task_w, "task_reject_wrapper_candidate", None)))


# ── 7. dry_run=False disabled result ─────────────────────────────────────────

r = _inbox_w.inbox_email_fetch_wrapper_candidate()
check("inbox disabled result ok=False", r.get("ok") is False)
check("inbox disabled would_call_adapter=False", r.get("would_call_adapter") is False)

r = _task_w.task_approve_wrapper_candidate()
check("approve disabled result ok=False", r.get("ok") is False)
check("approve disabled would_call_adapter=False", r.get("would_call_adapter") is False)

r = _task_w.task_reject_wrapper_candidate()
check("reject disabled result ok=False", r.get("ok") is False)
check("reject disabled would_call_adapter=False", r.get("would_call_adapter") is False)


# ── 8. feature_flag_enabled=True unsafe error ─────────────────────────────────

for label, fn, kwargs in [
    ("inbox", _inbox_w.inbox_email_fetch_wrapper_candidate, {}),
    ("approve", _task_w.task_approve_wrapper_candidate, {}),
    ("reject", _task_w.task_reject_wrapper_candidate, {}),
]:
    raised = False
    try:
        fn(feature_flag_enabled=True, **kwargs)
    except RouteWrapperUnsafeExecutionError:
        raised = True
    check(f"{label} feature_flag=True → unsafe error", raised,
          f"{label} wrapper가 feature_flag=True에서 unsafe error를 raise하지 않음")


# ── 9. dry-run fixture mode ───────────────────────────────────────────────────

try:
    r = _inbox_w.inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture={"limit": 5},
        legacy_response_fixture={"ok": True, "fetched": 2, "items": ["a", "b"]},
        dry_run=True,
    )
    check("inbox dry-run 성공", r.get("ok") is True)
    check("inbox dry-run route_connected=False", r.get("route_connected") is False)
    check("inbox dry-run feature_flag_enabled=False", r.get("feature_flag_enabled") is False)
    check("inbox dry-run fastapi_request 존재", "fastapi_request" in r)
    check("inbox dry-run normalized_response 존재", "normalized_response" in r)
except Exception as e:
    check("inbox dry-run 성공", False, str(e))

try:
    r = _task_w.task_approve_wrapper_candidate(
        task_id="AUDIT_TASK_001",
        response_fixture={"ok": True, "task_id": "AUDIT_TASK_001"},
        dry_run=True,
    )
    check("approve dry-run 성공", r.get("ok") is True)
    check("approve dry-run path_mapping 존재", "path_mapping" in r)
    nr = r.get("normalized_response", {})
    check("approve approval_gate_required=True", nr.get("approval_gate_required") is True)
    check("approve approval_gate_executed=False", nr.get("approval_gate_executed") is False)
    check("approve double slash 없음", "//" not in r.get("path_mapping", {}).get("legacy_path", ""))
except Exception as e:
    check("approve dry-run 성공", False, str(e))

try:
    r = _task_w.task_reject_wrapper_candidate(
        task_id="AUDIT_TASK_002",
        response_fixture={"ok": True, "task_id": "AUDIT_TASK_002"},
        dry_run=True,
    )
    check("reject dry-run 성공", r.get("ok") is True)
    check("reject dry-run path_mapping 존재", "path_mapping" in r)
    nr = r.get("normalized_response", {})
    check("reject approval_gate_required=True", nr.get("approval_gate_required") is True)
    check("reject approval_gate_executed=False", nr.get("approval_gate_executed") is False)
    check("reject double slash 없음", "//" not in r.get("path_mapping", {}).get("legacy_path", ""))
except Exception as e:
    check("reject dry-run 성공", False, str(e))


# ── 10. 제외 경로 확인 ────────────────────────────────────────────────────────

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

for excl in EXCLUDED_PATHS:
    check(f"제외 경로 미포함: {excl}", excl not in PHASE1H_TARGET_PATHS,
          f"제외 경로가 포함됨: {excl}")


# ── 11. route 파일에서 wrapper import 없음 ────────────────────────────────────

ROUTE_DIRS = [ROOT / "backend" / "routes", ROOT / "backend" / "api", ROOT / "app"]
WRAPPER_IMPORT_RE = re.compile(
    r"from\s+backend\.compat\.legacy_5050\.wrappers\."
    r"(inbox_email_fetch_wrapper_candidate|task_approval_wrapper_candidate)\s+import"
)

for route_dir in ROUTE_DIRS:
    if not route_dir.exists():
        continue
    for py_file in route_dir.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8", errors="ignore")
        match = WRAPPER_IMPORT_RE.search(src)
        check(
            f"route 파일 wrapper import 없음: {py_file.name}",
            match is None,
            f"route 파일이 Phase 1-H wrapper를 import: {py_file}",
        )


# ── 12. safe boundary 집계 ────────────────────────────────────────────────────

safe_boundary = {
    "route_connected": False,
    "feature_flag_default_enabled": False,
    "live_traffic_allowed": False,
    "db_write_allowed": False,
    "http_call_allowed": False,
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
verdict = VERDICT_PASS if not errors else "PHASE1H_FAIL"
print(f"VERDICT: {verdict}")
print("=" * 70)

print("\n[wrapper candidate 현황]")
for wid, fn_name, mod in [
    ("INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE", "inbox_email_fetch_wrapper_candidate", _inbox_w),
    ("TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE", "task_approve_wrapper_candidate", _task_w),
    ("TASK_REJECT_ROUTE_WRAPPER_CANDIDATE", "task_reject_wrapper_candidate", _task_w),
]:
    exists = callable(getattr(mod, fn_name, None))
    mark = "✅" if exists else "❌"
    print(f"  {mark} {wid}")

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
