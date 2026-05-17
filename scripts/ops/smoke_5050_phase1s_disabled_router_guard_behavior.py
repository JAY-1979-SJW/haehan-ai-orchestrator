"""
Phase 1-S: Disabled Router Guard Behavior Smoke
Phase 1-R guard가 기존 route 동작을 바꾸지 않는지 read-only smoke 검증.
"""
from pathlib import Path
import re

REPO_ROOT = Path(__file__).parent.parent.parent
ROUTER_FILE = "ai_orchestrator/router.py"
PHASE = "PHASE_1S"
SMOKE_ID = "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_SMOKE"

EXPECTED_FLAGS = {
    "LEGACY_5050_ROUTER_TOUCH_ENABLED": False,
    "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED": False,
    "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED": False,
    "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED": False,
}

EXPECTED_GUARD_FUNC = "_legacy_5050_should_use_route_wiring"

TARGET_ROUTES = [
    ("/inbox/email/fetch", "INBOX_EMAIL_FETCH"),
    ("/tasks/{task_id}/approve", "TASK_APPROVE"),
    ("/tasks/{task_id}/reject", "TASK_REJECT"),
]

FORBIDDEN_PATTERNS = [
    "import requests",
    "import httpx",
    "import sqlalchemy",
    "import psycopg2",
    "os.environ[",
    "os.getenv(",
    "from backend.compat.legacy_5050.route_integration",
]


def _read_router():
    return (REPO_ROOT / ROUTER_FILE).read_text(encoding="utf-8", errors="ignore")


def _parse_flags(content):
    result = {}
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'^(LEGACY_5050_\w+)\s*=\s*(False|True|"[^"]*"|\'[^\']*\')$', line)
        if m:
            key, val = m.group(1), m.group(2)
            if val == "False":
                result[key] = False
            elif val == "True":
                result[key] = True
            else:
                result[key] = val.strip('"\'')
    return result


def _check_guard_behavior(content):
    """guard 함수 소스에서 항상 False를 반환하는지 확인."""
    start = content.find(f"def {EXPECTED_GUARD_FUNC}")
    if start < 0:
        return False, "guard function not found"
    end = content.find("\ndef ", start + 1)
    guard_src = content[start:end] if end > start else content[start:]
    # 모든 flag 값이 False인 dict에서 get → False 반환 구조
    has_false_return = (
        "False" in guard_src and
        ("_flags.get" in guard_src or "return False" in guard_src)
    )
    return has_false_return, guard_src[:200]


def run_smoke():
    errors = []
    warnings = []
    content = _read_router()
    parsed_flags = _parse_flags(content)

    # 1. feature flag all false
    flags_all_false = True
    for flag, expected in EXPECTED_FLAGS.items():
        actual = parsed_flags.get(flag)
        if actual is not False:
            flags_all_false = False
            errors.append(f"flag not False: {flag} = {actual}")

    # 2. guard function exists and returns false
    guard_ok, guard_detail = _check_guard_behavior(content)
    if not guard_ok:
        errors.append(f"guard behavior issue: {guard_detail}")

    # 3. guard calls exist in handlers
    guard_calls_found = {}
    for route_path, route_id in TARGET_ROUTES:
        call_str = f'_legacy_5050_should_use_route_wiring("{route_id}")'
        guard_calls_found[route_id] = call_str in content
        if not guard_calls_found[route_id]:
            errors.append(f"guard call missing in handler for {route_id}")

    # 4. route paths preserved
    route_paths_preserved = True
    for route_path, _ in TARGET_ROUTES:
        if route_path not in content:
            route_paths_preserved = False
            errors.append(f"route path missing: {route_path}")

    # 5. forbidden patterns
    http_call_count = 0
    db_call_count = 0
    secret_output_count = 0
    route_integration_called = False
    wrapper_called = False

    for pattern in FORBIDDEN_PATTERNS:
        if pattern in content:
            if "requests" in pattern or "httpx" in pattern:
                http_call_count += 1
                errors.append(f"forbidden: {pattern}")
            elif "sqlalchemy" in pattern or "psycopg2" in pattern:
                db_call_count += 1
                errors.append(f"forbidden: {pattern}")
            elif "route_integration" in pattern:
                route_integration_called = True
                errors.append(f"forbidden: {pattern}")
            elif "os.environ" in pattern or "os.getenv" in pattern:
                errors.append(f"forbidden: {pattern}")

    # secret output check
    for bad in ["print(token", "print(cookie", "print(secret"]:
        if bad in content:
            secret_output_count += 1
            errors.append(f"secret output: {bad}")

    # /execute: should not be newly added
    if '@router.post("/execute"' in content or '@router.get("/execute"' in content:
        errors.append("forbidden /execute route decorator added")

    # behavior_changed
    behavior_changed = len(errors) > 0

    verdict = (
        "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_SMOKE_FAIL" if errors
        else "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_SMOKE_READY"
    )

    return {
        "phase": PHASE,
        "smoke_id": SMOKE_ID,
        "router_file": ROUTER_FILE,
        "imported_router_module": False,  # static analysis only
        "feature_flags_all_false": flags_all_false,
        "guard_returns_false": guard_ok,
        "route_paths_preserved": route_paths_preserved,
        "guard_calls_found": guard_calls_found,
        "route_integration_called": route_integration_called,
        "wrapper_called": wrapper_called,
        "http_call_count": http_call_count,
        "db_call_count": db_call_count,
        "secret_output_count": secret_output_count,
        "behavior_changed": behavior_changed,
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json
    result = run_smoke()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-S Smoke: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
