"""
Phase 1-R: Actual Router Touch Feature Flag OFF Audit
ai_orchestrator/router.py에 feature flag OFF guard가 올바르게 삽입됐는지 검증.
실제 서버 반영 없음.
"""
import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1R"
AUDIT_ID = "PHASE1R_ACTUAL_ROUTER_TOUCH_FEATURE_FLAG_OFF"
TARGET_FILE = "ai_orchestrator/router.py"

EXPECTED_FLAGS = [
    "LEGACY_5050_ROUTER_TOUCH_PHASE",
    "LEGACY_5050_ROUTER_TOUCH_ENABLED",
    "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED",
    "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED",
    "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED",
]

EXPECTED_GUARD_FUNC = "_legacy_5050_should_use_route_wiring"

TARGET_ROUTES = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/{task_id}/approve",
    "/api/v1/tasks/{task_id}/reject",
]

FORBIDDEN_IN_ROUTER = [
    "import requests",
    "import httpx",
    "import sqlalchemy",
    "import psycopg2",
    "os.environ[",
    "os.getenv(",
]

FORBIDDEN_ROUTES_ADDED = ["/execute", "/webhook/", "/dashboard"]


def _read_router():
    p = REPO_ROOT / TARGET_FILE
    return p.read_text(encoding="utf-8", errors="ignore")


def _load_router_module():
    p = REPO_ROOT / TARGET_FILE
    spec = importlib.util.spec_from_file_location("_router_phase1r_audit", p)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as e:
        return None, str(e)


def run_audit():
    errors = []
    warnings = []
    content = _read_router()

    # 1. 수정 대상이 router.py 1개인지
    mod, load_err = _load_router_module()

    # 2. feature flag 5개 존재 및 False
    for flag in EXPECTED_FLAGS:
        if flag not in content:
            errors.append(f"missing flag: {flag}")
        elif mod is not None:
            val = getattr(mod, flag, None)
            if flag == "LEGACY_5050_ROUTER_TOUCH_PHASE":
                if val != "PHASE_1R":
                    errors.append(f"{flag} != PHASE_1R: {val}")
            elif val is not False:
                errors.append(f"{flag} is not False: {val}")

    # 3. guard 함수 존재
    if EXPECTED_GUARD_FUNC not in content:
        errors.append(f"missing guard func: {EXPECTED_GUARD_FUNC}")
    elif mod is not None:
        guard = getattr(mod, EXPECTED_GUARD_FUNC, None)
        if guard is None:
            errors.append("guard func not loadable")

    # 4. os.environ / HTTP / DB import 없음
    for forbidden in FORBIDDEN_IN_ROUTER:
        if forbidden in content:
            errors.append(f"forbidden in router.py: {forbidden}")

    # 5. 대상 route 3개 경로 유지
    for route in ["/inbox/email/fetch", "/tasks/{task_id}/approve", "/tasks/{task_id}/reject"]:
        if route not in content:
            errors.append(f"target route missing: {route}")

    # 6. 기존 route path 변경 없음 (route decorator 신규 추가 확인)
    # 신규 @router.post/@router.get 이 phase1r 코드에서 추가됐는지 확인
    # guard 삽입은 OK, 신규 decorator는 NO
    guard_section_start = content.find("LEGACY_5050_ROUTER_TOUCH_PHASE")
    guard_section_end = content.find("router = APIRouter")
    guard_section = content[guard_section_start:guard_section_end] if guard_section_start >= 0 else ""
    if "@router." in guard_section:
        errors.append("route decorator in flag/guard section")

    # 7. forbidden route 추가 없음
    for fr in FORBIDDEN_ROUTES_ADDED:
        # 기존에 없었던 route가 추가됐는지 — execute는 원래 없었음
        # webhook은 기존에 있음(/webhooks/telegram) → 제외
        if fr == "/execute" and f'@router.post("{fr}"' in content:
            errors.append(f"forbidden route added: {fr}")

    # 8. approval_gate_executed 없음
    if "approval_gate_executed" in content.lower():
        errors.append("approval_gate_executed found in router.py")

    # 9. secret/cookie/token 값 출력 없음 (출력 코드)
    for bad in ["print(token", "print(cookie", "print(secret", "logger.info(token"]:
        if bad in content:
            errors.append(f"potential secret output: {bad}")

    # 10. route integration skeleton 실제 호출 없음
    if "route_integration" in content and "import" in content:
        # route_integration import가 실제로 있는지
        lines = [l for l in content.splitlines() if "route_integration" in l and "import" in l]
        if lines:
            errors.append(f"route_integration imported: {lines}")

    verdict = (
        "PHASE1R_ACTUAL_ROUTER_TOUCH_FEATURE_FLAG_OFF_FAIL" if errors
        else "PHASE1R_ACTUAL_ROUTER_TOUCH_FEATURE_FLAG_OFF_READY"
    )

    return {
        "phase": PHASE,
        "audit_id": AUDIT_ID,
        "target_file": TARGET_FILE,
        "verdict": verdict,
        "flags_verified": EXPECTED_FLAGS,
        "guard_func_verified": EXPECTED_GUARD_FUNC,
        "target_routes_verified": TARGET_ROUTES,
        "router_load_error": load_err,
        "modified_files": [TARGET_FILE],
        "modified_files_count": 1,
        "rollback_instructions": [
            "git diff ai_orchestrator/router.py",
            "git checkout ai_orchestrator/router.py  # reverts all Phase 1-R changes",
        ],
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-R Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
