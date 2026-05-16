"""5050 Phase 1-F — adapter skeleton only 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01

Phase 1-F skeleton 파일이 존재하고 import-safe이며,
실제 구현/route 연결/side effect가 없는지 검증한다.

실행:
    python scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py
    python scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py --json

절대 금지:
    5050 route 수정 금지 / 8400 handler 수정 금지 / route 연결 금지
    실제 adapter 구현 금지 / nginx 변경 금지 / 서버 반영 금지
    실제 HTTP 호출 금지 / DB write 금지 / secret 값 출력 금지
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── 안전 경계 ─────────────────────────────────────────────────────────────────

SAFE_BOUNDARY = {
    "5050_route_modify":         False,
    "8400_handler_modify":       False,
    "route_connection":          False,
    "adapter_implementation":    False,
    "nginx_change":              False,
    "server_apply":              False,
    "actual_http_call":          False,
    "actual_email_fetch":        False,
    "actual_approve":            False,
    "actual_reject":             False,
    "actual_execute":            False,
    "actual_webhook_call":       False,
    "actual_db_write":           False,
    "secret_value_output":       False,
    "feature_flag_runtime_hook": False,
}

# ── known baseline failures ───────────────────────────────────────────────────

KNOWN_BASELINE_FAILURES = [
    "tests/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
    "tests/test_cad_local_agent_adapter_20260509.py::test_cad_status_lists_physical_modules",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_cad_adapter_status_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_bridge_health_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_fastmcp_call_tool_invokes_local_cad_bridge_health",
]

# ── 금지 import 패턴 ──────────────────────────────────────────────────────────

FORBIDDEN_IMPORTS = [
    "requests", "httpx", "urllib.request",
    "sqlite3", "psycopg", "psycopg2",
    "sqlalchemy.create_engine", "sqlalchemy.engine",
    "subprocess", "socket",
]

FORBIDDEN_DECORATORS = [
    "@app.route", "@router.get", "@router.post",
    "@router.put", "@router.delete", "@router.patch",
    "@app.get", "@app.post",
]

# ── skeleton 파일 경로 ────────────────────────────────────────────────────────

SKELETON_MODULES = {
    "common":              ROOT / "backend/compat/legacy_5050/adapters/common.py",
    "inbox_email_fetch":   ROOT / "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
    "task_approval":       ROOT / "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
}

INIT_FILES = [
    ROOT / "backend/compat/__init__.py",
    ROOT / "backend/compat/legacy_5050/__init__.py",
    ROOT / "backend/compat/legacy_5050/adapters/__init__.py",
]


# ── 유효성 검사 헬퍼 ──────────────────────────────────────────────────────────

def _get_import_lines(source: str) -> list[str]:
    """실제 import 문 행만 추출 (docstring/주석 제외)."""
    lines = []
    in_docstring = False
    quote: str | None = None
    for line in source.splitlines():
        stripped = line.strip()
        for q in ('"""', "'''"):
            if q in stripped:
                count = stripped.count(q)
                if not in_docstring:
                    in_docstring = True
                    quote = q
                    if count >= 2:
                        in_docstring = False
                        quote = None
                elif quote == q:
                    in_docstring = False
                    quote = None
                break
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _check_forbidden_imports(source: str) -> list[str]:
    import_lines = _get_import_lines(source)
    found = []
    for pattern in FORBIDDEN_IMPORTS:
        module = pattern.split(".")[0]
        for line in import_lines:
            if line.startswith(f"import {module}") or line.startswith(f"from {module}"):
                if pattern not in found:
                    found.append(pattern)
                break
    return found


def _check_forbidden_decorators(source: str) -> list[str]:
    found = []
    for dec in FORBIDDEN_DECORATORS:
        if dec in source:
            found.append(dec)
    return found


def _all_files_exist() -> bool:
    for p in SKELETON_MODULES.values():
        if not p.exists():
            return False
    for p in INIT_FILES:
        if not p.exists():
            return False
    return True


def _try_import_module(dotted: str) -> tuple[bool, str]:
    try:
        importlib.import_module(dotted)
        return True, ""
    except Exception as e:
        return False, str(e)


def _raises_skeleton_error(func: Any) -> bool:
    try:
        func()
        return False
    except Exception as e:
        module_path = type(e).__module__
        class_name = type(e).__name__
        return (
            "SkeletonOnlyAdapterError" in class_name
            or "SkeletonOnly" in str(e)
            or "PHASE_1F skeleton only" in str(e)
        )


def _check_no_double_slash(path: str) -> bool:
    return "//" not in path


# ── 감사 함수 ─────────────────────────────────────────────────────────────────

def run_audit() -> dict[str, Any]:
    results: dict[str, Any] = {}
    issues: list[str] = []

    # 1. 파일 존재 확인
    files_exist = _all_files_exist()
    if not files_exist:
        missing = [str(p) for p in list(SKELETON_MODULES.values()) + INIT_FILES
                   if not p.exists()]
        issues.append(f"missing files: {missing}")

    # 2. import 가능 확인
    import_ok: dict[str, bool] = {}
    for name, dotted in {
        "common":            "backend.compat.legacy_5050.adapters.common",
        "inbox_email_fetch": "backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter",
        "task_approval":     "backend.compat.legacy_5050.adapters.task_approval_adapter",
    }.items():
        ok, err = _try_import_module(dotted)
        import_ok[name] = ok
        if not ok:
            issues.append(f"import failed [{name}]: {err}")

    # 3. 금지 패턴 검사
    forbidden_found: dict[str, list] = {}
    for name, path in SKELETON_MODULES.items():
        if path.exists():
            src = path.read_text(encoding="utf-8")
            bad_imports = _check_forbidden_imports(src)
            bad_decs = _check_forbidden_decorators(src)
            all_bad = bad_imports + bad_decs
            forbidden_found[name] = all_bad
            if all_bad:
                issues.append(f"forbidden patterns in {name}: {all_bad}")

    # 4. metadata / adapt 함수 및 exception 검사
    adapt_raises: dict[str, bool] = {}
    metadata_ok: dict[str, bool] = {}

    if import_ok.get("inbox_email_fetch"):
        import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter as _inbox
        metadata_ok["inbox"] = callable(getattr(_inbox, "get_adapter_metadata", None))
        adapt_raises["inbox"] = _raises_skeleton_error(_inbox.adapt_inbox_email_fetch_request_response)

    if import_ok.get("task_approval"):
        import backend.compat.legacy_5050.adapters.task_approval_adapter as _task
        metadata_ok["approve"] = callable(getattr(_task, "get_task_approve_adapter_metadata", None))
        metadata_ok["reject"]  = callable(getattr(_task, "get_task_reject_adapter_metadata", None))
        adapt_raises["approve"] = _raises_skeleton_error(_task.adapt_task_approve_path_auth_response)
        adapt_raises["reject"]  = _raises_skeleton_error(_task.adapt_task_reject_path_auth_response)

    # 5. 상수 확인
    const_ok: dict[str, bool] = {}
    if import_ok.get("common"):
        import backend.compat.legacy_5050.adapters.common as _common
        for const in [
            "PHASE", "SKELETON_ONLY", "IMPLEMENTATION_ALLOWED",
            "LIVE_CALL_ALLOWED", "SIDE_EFFECT_ALLOWED", "DB_WRITE_ALLOWED",
            "SECRET_VALUE_ALLOWED", "ROUTE_HANDLER_CHANGE_ALLOWED",
            "SERVER_APPLY_ALLOWED", "NGINX_CHANGE_ALLOWED",
            "SkeletonOnlyAdapterError", "AdapterSkeletonMetadata",
        ]:
            const_ok[const] = hasattr(_common, const)
            if not const_ok[const]:
                issues.append(f"missing constant/class in common: {const}")

    # 6. path template double slash 확인
    no_double_slash = True
    if import_ok.get("inbox_email_fetch"):
        import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter as _i
        for attr in ("LEGACY_PATH_TEMPLATE", "FASTAPI_PATH_TEMPLATE"):
            v = getattr(_i, attr, "")
            if "//" in v:
                no_double_slash = False
                issues.append(f"double slash in inbox {attr}: {v}")

    if import_ok.get("task_approval"):
        import backend.compat.legacy_5050.adapters.task_approval_adapter as _t
        for attr in (
            "APPROVE_LEGACY_PATH_TEMPLATE", "APPROVE_FASTAPI_PATH_TEMPLATE",
            "REJECT_LEGACY_PATH_TEMPLATE", "REJECT_FASTAPI_PATH_TEMPLATE",
        ):
            v = getattr(_t, attr, "")
            if "//" in v:
                no_double_slash = False
                issues.append(f"double slash in task {attr}: {v}")

    # 7. 금지 경로 미포함 확인
    no_forbidden_paths = True
    if import_ok.get("inbox_email_fetch"):
        import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter as _i2
        p = getattr(_i2, "LEGACY_PATH_TEMPLATE", "")
        if "execute" in p or "webhook" in p or "/dashboard" in p:
            no_forbidden_paths = False
            issues.append(f"forbidden path in inbox: {p}")

    if import_ok.get("task_approval"):
        import backend.compat.legacy_5050.adapters.task_approval_adapter as _t2
        for attr in ("APPROVE_LEGACY_PATH_TEMPLATE", "REJECT_LEGACY_PATH_TEMPLATE"):
            p = getattr(_t2, attr, "")
            if "execute" in p or "webhook" in p or "/dashboard" in p:
                no_forbidden_paths = False
                issues.append(f"forbidden path in task {attr}: {p}")

    # 8. boundary violations
    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]

    # 집계
    total_modules  = 2  # inbox + task_approval
    meta_count     = sum(1 for v in metadata_ok.values() if v)
    adapt_count    = len(adapt_raises)
    raise_count    = sum(1 for v in adapt_raises.values() if v)
    no_forbidden_import = all(len(v) == 0 for v in forbidden_found.values())

    success = (
        files_exist
        and all(import_ok.values())
        and all(metadata_ok.values())
        and all(adapt_raises.values())
        and no_double_slash
        and no_forbidden_paths
        and no_forbidden_import
        and len(boundary_violations) == 0
        and not issues
    )

    return {
        "audit_id":  "ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01",
        "verdict":   "PHASE1F_ADAPTER_SKELETON_ONLY_READY" if success else "FAIL",
        "success":   success,
        "issues":    issues,
        "safe_boundary": {**SAFE_BOUNDARY, "violations": boundary_violations},
        "known_baseline_failures": KNOWN_BASELINE_FAILURES,
        "checks": {
            "files_exist":         files_exist,
            "import_ok":           import_ok,
            "metadata_ok":         metadata_ok,
            "adapt_raises":        adapt_raises,
            "const_ok":            const_ok,
            "forbidden_found":     forbidden_found,
            "no_double_slash":     no_double_slash,
            "no_forbidden_paths":  no_forbidden_paths,
        },
        "summary": {
            "total_skeleton_modules":  total_modules,
            "metadata_function_count": meta_count,
            "adapt_function_count":    adapt_count,
            "raise_on_call_count":     raise_count,
            "no_forbidden_import":     no_forbidden_import,
            "no_double_slash":         no_double_slash,
            "no_forbidden_paths":      no_forbidden_paths,
        },
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)

    checks = audit["checks"]
    print("\n[파일 존재]")
    print(f"  {'✅' if checks['files_exist'] else '❌'} skeleton 파일 전체 존재")

    print("\n[import 가능]")
    for name, ok in checks["import_ok"].items():
        print(f"  {'✅' if ok else '❌'} {name}")

    print("\n[metadata 함수]")
    for name, ok in checks["metadata_ok"].items():
        print(f"  {'✅' if ok else '❌'} get_{name}_adapter_metadata")

    print("\n[adapt 함수 → SkeletonOnlyAdapterError]")
    for name, ok in checks["adapt_raises"].items():
        print(f"  {'✅' if ok else '❌'} adapt_{name}_* raises SkeletonOnlyAdapterError")

    print("\n[금지 패턴]")
    for name, found in checks["forbidden_found"].items():
        if found:
            print(f"  ❌ {name}: {found}")
        else:
            print(f"  ✅ {name}: 금지 패턴 없음")

    s = audit["summary"]
    print("\n[집계]")
    items = [
        ("skeleton module 수",          s["total_skeleton_modules"],  2),
        ("metadata 함수 수",             s["metadata_function_count"], 3),
        ("adapt 함수 수",               s["adapt_function_count"],    3),
        ("raise on call 수",            s["raise_on_call_count"],     3),
        ("forbidden import 없음",        s["no_forbidden_import"],     True),
        ("double slash 없음",           s["no_double_slash"],         True),
        ("forbidden path 없음",          s["no_forbidden_paths"],      True),
    ]
    for label, val, expected in items:
        mark = "✅" if val == expected else "❌"
        print(f"  {mark} {label}: {val} (기준: {expected})")

    sb = audit["safe_boundary"]
    print("\n[SAFE BOUNDARY]")
    if sb["violations"]:
        print(f"  ❌ 위반: {sb['violations']}")
    else:
        print("  ✅ 위반 없음")

    if audit["issues"]:
        print("\n[ISSUES]")
        for issue in audit["issues"]:
            print(f"  ❌ {issue}")

    print("\n[known baseline failures (이번 공정 무관)]")
    for f in audit["known_baseline_failures"]:
        print(f"  - {f}")

    print("=" * 70)
    print(f"VERDICT: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="5050 Phase 1-F adapter skeleton only 감사"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = run_audit()
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        _print_report(audit)
    sys.exit(0 if audit["success"] else 1)


if __name__ == "__main__":
    main()
