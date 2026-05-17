"""Phase 1-I staging dry-run internal smoke 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_01

이 스크립트는 코드 수정 없이 정적 검사/import 검사/smoke 실행만 수행한다.
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

AUDIT_ID = "ASSISTANT_BACKEND_5050_LEGACY_PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_01"
VERDICT_PASS = "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_READY"

SMOKE_FILE = ROOT / "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py"

SMOKE_FILES = [
    SMOKE_FILE,
    # 감사 스크립트 자체는 FORBIDDEN_PATTERNS 목록을 포함하므로 자체 검사 제외
]

FORBIDDEN_IMPORTS = [
    "requests", "httpx", "urllib.request", "socket",
    "sqlite3", "psycopg", "sqlalchemy",
    "fastapi", "flask", "subprocess",
]

FORBIDDEN_PATTERNS = [
    "APIRouter", "@app.route", "@router.",
    "uvicorn", "gunicorn", "os.environ[",
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

check("smoke runner 파일 존재", SMOKE_FILE.exists(), f"파일 없음: {SMOKE_FILE}")


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


for sf in SMOKE_FILES:
    if not sf.exists():
        continue
    src = sf.read_text(encoding="utf-8")
    imports = _get_imports(sf)
    for fi in FORBIDDEN_IMPORTS:
        has = any(fi in imp for imp in imports)
        check(f"{sf.name}: forbidden import 없음 — {fi}", not has,
              f"{sf.name}에 forbidden import: {fi}")
    for fp in FORBIDDEN_PATTERNS:
        check(f"{sf.name}: forbidden pattern 없음 — {fp}", fp not in src,
              f"{sf.name}에 forbidden pattern: {fp!r}")


# ── 3. smoke runner 함수 존재 ─────────────────────────────────────────────────

import scripts.ops.smoke_5050_phase1i_staging_dry_run_internal as _smoke

check("build_phase1i_smoke_fixtures 존재", callable(getattr(_smoke, "build_phase1i_smoke_fixtures", None)))
check("run_phase1i_internal_smoke 존재", callable(getattr(_smoke, "run_phase1i_internal_smoke", None)))
check("main 존재", callable(getattr(_smoke, "main", None)))


# ── 4. smoke 실행 및 summary 검증 ────────────────────────────────────────────

try:
    summary = _smoke.run_phase1i_internal_smoke()
    summary.pop("_scenarios", None)

    check("phase=PHASE_1I", summary.get("phase") == "PHASE_1I")
    check("smoke_id 정확", summary.get("smoke_id") == "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE")
    check("staging_mode=INTERNAL_FIXTURE_ONLY", summary.get("staging_mode") == "INTERNAL_FIXTURE_ONLY")
    check("wrapper_count=3", summary.get("wrapper_count") == 3)
    check("total_scenarios>=14", summary.get("total_scenarios", 0) >= 14)
    check("failed_scenarios=0", summary.get("failed_scenarios") == 0)
    check("disabled_mode_passed=True", summary.get("disabled_mode_passed") is True)
    check("unsafe_mode_passed=True", summary.get("unsafe_mode_passed") is True)
    check("dry_run_success_passed=True", summary.get("dry_run_success_passed") is True)
    check("bad_fixture_boundary_passed=True", summary.get("bad_fixture_boundary_passed") is True)

    # safety counters
    check("server_started=False", summary.get("server_started") is False)
    check("route_connected=False", summary.get("route_connected") is False)
    check("live_traffic_allowed=False", summary.get("live_traffic_allowed") is False)
    for counter in [
        "http_call_count", "db_read_count", "db_write_count",
        "secret_value_output_count", "email_fetch_live_call_count",
        "approve_live_call_count", "reject_live_call_count",
        "execute_call_count", "webhook_call_count",
    ]:
        check(f"{counter}=0", summary.get(counter) == 0)

    check("no_double_slash=True", summary.get("no_double_slash") is True)
    check("no_forbidden_route=True", summary.get("no_forbidden_route") is True)
    check("verdict READY", summary.get("verdict") == VERDICT_PASS,
          f"verdict={summary.get('verdict')}")

except Exception as e:
    check("smoke 실행 성공", False, f"smoke 실행 오류: {e}")


# ── 5. Phase 1-H wrapper candidate 유지 검증 ──────────────────────────────────

import backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate as _iw
import backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate as _tw

check("inbox FEATURE_FLAG_DEFAULT=False", _iw.FEATURE_FLAG_DEFAULT is False)
check("approve FEATURE_FLAG_DEFAULT=False", _tw.APPROVE_FEATURE_FLAG_DEFAULT is False)
check("reject FEATURE_FLAG_DEFAULT=False", _tw.REJECT_FEATURE_FLAG_DEFAULT is False)
check("inbox ROUTE_CONNECTED=False", _iw.ROUTE_CONNECTED is False)
check("approve ROUTE_CONNECTED=False", _tw.APPROVE_ROUTE_CONNECTED is False)
check("reject ROUTE_CONNECTED=False", _tw.REJECT_ROUTE_CONNECTED is False)


# ── 6. Phase 1-F skeleton guard 유지 ─────────────────────────────────────────

from backend.compat.legacy_5050.adapters.common import SkeletonOnlyAdapterError
from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
    adapt_inbox_email_fetch_request_response,
)

raised = False
try:
    adapt_inbox_email_fetch_request_response()
except SkeletonOnlyAdapterError:
    raised = True
check("Phase 1-F skeleton guard 유지", raised)


# ── 7. route 파일 wrapper import 없음 ────────────────────────────────────────

ROUTE_DIRS = [ROOT / "backend" / "routes", ROOT / "backend" / "api", ROOT / "app"]
WRAPPER_IMPORT_RE = re.compile(
    r"from\s+backend\.compat\.legacy_5050\.wrappers\.\w+\s+import"
)
for route_dir in ROUTE_DIRS:
    if not route_dir.exists():
        continue
    for py_file in route_dir.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8", errors="ignore")
        check(f"route 파일 wrapper import 없음: {py_file.name}",
              WRAPPER_IMPORT_RE.search(src) is None,
              f"route 파일이 Phase 1-H wrapper를 import: {py_file}")


# ── 출력 ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print(f"AUDIT: {AUDIT_ID}")
verdict = VERDICT_PASS if not errors else "PHASE1I_FAIL"
print(f"VERDICT: {verdict}")
print("=" * 70)

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
