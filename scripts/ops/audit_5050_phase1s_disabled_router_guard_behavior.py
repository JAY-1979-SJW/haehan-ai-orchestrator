"""
Phase 1-S: Disabled Router Guard Behavior Audit
Phase 1-R router.py 정적 구조 감사.
"""
from pathlib import Path
import re
import importlib.util

REPO_ROOT = Path(__file__).parent.parent.parent
ROUTER_FILE = "ai_orchestrator/router.py"
PHASE = "PHASE_1S"
AUDIT_ID = "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR"

EXPECTED_FLAGS = [
    "LEGACY_5050_ROUTER_TOUCH_PHASE",
    "LEGACY_5050_ROUTER_TOUCH_ENABLED",
    "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED",
    "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED",
    "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED",
]

ROLLBACK_INSTRUCTIONS = [
    "git revert 847f0ee",
    "or: git checkout 0d74129 -- ai_orchestrator/router.py && git commit -m 'revert(router): remove phase1r disabled wiring guards'",
]

FORBIDDEN_IN_ROUTER = [
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


def _parse_flag_values(content):
    result = {}
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'^(LEGACY_5050_\w+)\s*=\s*(False|True|"[^"]*"|\'[^\']*\')$', line)
        if m:
            key, val = m.group(1), m.group(2)
            result[key] = False if val == "False" else (True if val == "True" else val.strip('"\''))
    return result


def run_audit():
    errors = []
    warnings = []
    content = _read_router()
    flag_values = _parse_flag_values(content)

    # 1. router.py 존재
    if not (REPO_ROOT / ROUTER_FILE).exists():
        errors.append(f"router file not found: {ROUTER_FILE}")
        return {"verdict": "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_FAIL", "errors": errors}

    # 2. feature flag 5개 존재 + False
    for flag in EXPECTED_FLAGS:
        if flag not in content:
            errors.append(f"flag missing: {flag}")
        else:
            val = flag_values.get(flag)
            if flag == "LEGACY_5050_ROUTER_TOUCH_PHASE":
                if val != "PHASE_1R":
                    errors.append(f"{flag} != PHASE_1R: {val}")
            elif val is not False:
                errors.append(f"{flag} not False: {val}")

    # 3. env/secret/HTTP/DB 없음
    for pattern in FORBIDDEN_IN_ROUTER:
        if pattern in content:
            errors.append(f"forbidden: {pattern}")

    # 4. route integration skeleton 실제 호출 없음
    if "route_integration" in content:
        for line in content.splitlines():
            if "route_integration" in line and "import" in line:
                errors.append(f"route_integration import: {line.strip()}")

    # 5. APIRouter 1개만 (신규 생성 없음)
    if content.count("APIRouter(") > 1:
        errors.append(f"multiple APIRouter() found: {content.count('APIRouter(')}")

    # 6. route decorator 신규 없음 (guard 섹션에)
    start = content.find("LEGACY_5050_ROUTER_TOUCH_PHASE")
    end = content.find("router = APIRouter")
    if start >= 0 and end > start:
        section = content[start:end]
        if "@router." in section:
            errors.append("route decorator in phase1r section")

    # 7. 대상 route 3개 path 유지
    for path in ["/inbox/email/fetch", "/tasks/{task_id}/approve", "/tasks/{task_id}/reject"]:
        if path not in content:
            errors.append(f"route path missing: {path}")

    # 8. /execute 신규 route 없음
    if '@router.post("/execute"' in content:
        errors.append("forbidden /execute route added")

    # 9. approval_gate_executed 없음
    if "approval_gate_executed" in content.lower():
        warnings.append("approval_gate_executed found - verify intent")

    # 10. guard always False
    guard_start = content.find("def _legacy_5050_should_use_route_wiring")
    if guard_start < 0:
        errors.append("guard function missing")
    else:
        guard_end = content.find("\ndef ", guard_start + 1)
        guard_src = content[guard_start:guard_end] if guard_end > guard_start else content[guard_start:]
        if "True" in guard_src and "False" not in guard_src:
            errors.append("guard may return True")

    verdict = (
        "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_FAIL" if errors else
        "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_READY_WITH_WARN" if warnings else
        "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_READY"
    )

    return {
        "phase": PHASE,
        "audit_id": AUDIT_ID,
        "router_file": ROUTER_FILE,
        "verdict": verdict,
        "flag_values": flag_values,
        "rollback_instructions": ROLLBACK_INSTRUCTIONS,
        "modified_files": [ROUTER_FILE],
        "server_apply": False,
        "nginx_changed": False,
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-S Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARN: {w}")
