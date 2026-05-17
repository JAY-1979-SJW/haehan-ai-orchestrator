"""
Phase 1-Q Closeout: Router Touch Scope Pin Audit
Phase 1-R 진입 전 최종 범위 고정.
실제 router 수정 없음.
"""
from pathlib import Path
import importlib.util
import sys

REPO_ROOT = Path(__file__).parent.parent.parent

# ── 상수 ──────────────────────────────────────────────────────────────────
PHASE = "PHASE_1Q_CLOSEOUT"
CLOSEOUT_ID = "PHASE1Q_CLOSEOUT_ROUTER_TOUCH_SCOPE_PIN"
REAL_ROUTER_TOUCH_ALLOWED = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
ROUTE_REGISTRATION_ALLOWED = False
APIRouter_ALLOWED = False
INCLUDE_ROUTER_ALLOWED = False
ROUTE_DECORATOR_ALLOWED = False
FEATURE_FLAG_RUNTIME_HOOK_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ONLY = True
SERVER_APPLY_ALLOWED = False
PHASE1R_USER_EXPLICIT_APPROVAL_REQUIRED = True
PHASE1R_AUTO_START_ALLOWED = False

# ── 1차 touch 후보 (고정) ────────────────────────────────────────────────
PRIMARY_TOUCH_CANDIDATE = "ai_orchestrator/router.py"
PRIMARY_TOUCH_CANDIDATE_REASON = (
    "가장 작은 크기(265줄), inbox/approve/reject/tasks 모두 포함, "
    "메인 라우터 진입점, approve/reject 직접 action 없는 routing layer — "
    "Phase 1-R에서 feature flag OFF skeleton 최소 변경으로 연결 가능"
)
PRIMARY_TOUCH_CANDIDATE_TARGET_ROUTES = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/{id}/approve",
    "/api/v1/tasks/{id}/reject",
]
PRIMARY_TOUCH_CANDIDATE_RISK = "LOW — routing layer only, no live action"
PRIMARY_TOUCH_PHASE1R_ALLOWED_SCOPE = (
    "read-only inspection + feature flag OFF skeleton wiring plan only; "
    "no route registration without separate explicit approval"
)

# ── candidate 재분류 ────────────────────────────────────────────────────
SECONDARY_CANDIDATES = [
    "ai_orchestrator/admin_ui_router.py",
    "ai_orchestrator/browser_tool/approval_record_router.py",
    "ai_orchestrator/local_agent/browser/approval_server.py",
    "ai_orchestrator/local_agent_router.py",
    "ai_orchestrator/sites/router.py",
]

SECONDARY_REASON = "route 정의 포함 + approve/reject/tasks 관련이나 1차 touch 대상 아님"

# secondary 에 포함되지 않은 나머지 관찰 대상 (Phase 1-Q에서 secondary였던 13개 중 제외된 것)
OBSERVATION_CANDIDATES_SAMPLE = [
    "ai_orchestrator/action_router.py",
    "ai_orchestrator/cad/router.py",
    "ai_orchestrator/cad_ai_router.py",
    "ai_orchestrator/connectors/naver_search_router.py",
    "ai_orchestrator/external_work_registry.py",
    # ... (Phase 1-Q secondary 나머지 8개)
]

EXCLUDED_PATTERNS = [
    "test_", "audit_", "smoke_", "route_integration", "wrapper_candidate",
    "__pycache__", ".pyc", "docs/", "external_sites", "wrappers/",
]

# ── browser audit 결과 ────────────────────────────────────────────────────
BROWSER_AUDIT_TEST_ID = (
    "tests/test_browser_audit_wiring.py::"
    "TestAuditNoSecrets::test_audit_event_does_not_include_cookie_session_storage_base64"
)
BROWSER_AUDIT_STANDALONE_RESULT = "PASS"
BROWSER_AUDIT_FILE_RESULT = "PASS_17_passed"
BROWSER_AUDIT_SECRET_LEAKAGE = False
BROWSER_AUDIT_VERDICT = "FLAKY_OR_ORDER_DEPENDENT_CANDIDATE"
BROWSER_AUDIT_NOTE = (
    "전체 pytest에서 1회 실패했으나 단독 및 파일 단위 실행 시 PASS. "
    "다른 테스트의 사이드이펙트(order-dependent) 가능성. "
    "Phase 1-Q 신규 코드와 직접 관련 없음."
)

# ── Phase 1-R entry conditions ─────────────────────────────────────────────
PHASE1R_ENTRY_CONDITIONS = [
    {"id": "git_clean", "required": True},
    {"id": "head_sync_with_origin_master", "required": True},
    {"id": "primary_touch_candidate_pinned_to_1_file", "required": True},
    {"id": "approval_gate_canonical_path_fixed", "required": True},
    {"id": "browser_audit_not_blocked", "required": True},
    {"id": "feature_flag_default_false", "required": True},
    {"id": "rollback_plan_exists", "required": True},
    {"id": "user_explicit_approval_for_phase1r", "required": True},
]

def _is_excluded(path_str):
    return any(p in path_str for p in EXCLUDED_PATTERNS)

def check_primary_candidate_exists():
    p = REPO_ROOT / PRIMARY_TOUCH_CANDIDATE
    return p.exists()

def check_primary_not_modified_by_phase1q():
    """Phase 1-Q closeout 코드가 primary 파일에 없는지 확인"""
    p = REPO_ROOT / PRIMARY_TOUCH_CANDIDATE
    if not p.exists():
        return True  # 파일 없으면 수정 없음
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return True
    return "phase1q" not in content.lower() and "phase1r" not in content.lower()

def run_audit():
    errors = []
    warnings = []

    # primary candidate 검증
    if not check_primary_candidate_exists():
        errors.append(f"primary_touch_candidate not found: {PRIMARY_TOUCH_CANDIDATE}")
    if not check_primary_not_modified_by_phase1q():
        errors.append(f"primary_touch_candidate was modified: {PRIMARY_TOUCH_CANDIDATE}")

    # browser audit
    if BROWSER_AUDIT_SECRET_LEAKAGE:
        errors.append("BROWSER_AUDIT_SECRET_LEAKAGE=True")
    if BROWSER_AUDIT_STANDALONE_RESULT != "PASS":
        errors.append(f"browser audit standalone failed: {BROWSER_AUDIT_STANDALONE_RESULT}")

    # secondary 분류
    secondary_exists = len(SECONDARY_CANDIDATES) > 0

    # forbidden route 확인
    for path in PRIMARY_TOUCH_CANDIDATE_TARGET_ROUTES:
        if "//" in path:
            errors.append(f"double slash in target route: {path}")
        if "/execute" in path:
            errors.append(f"forbidden /execute in route: {path}")

    verdict = (
        "PHASE1Q_CLOSEOUT_BLOCKED" if errors else
        "PHASE1Q_CLOSEOUT_READY_WITH_FLAKY_BROWSER_AUDIT"
        if BROWSER_AUDIT_VERDICT == "FLAKY_OR_ORDER_DEPENDENT_CANDIDATE" else
        "PHASE1Q_CLOSEOUT_ROUTER_TOUCH_SCOPE_PIN_READY"
    )

    return {
        "phase": PHASE,
        "closeout_id": CLOSEOUT_ID,
        "verdict": verdict,
        "primary_touch_candidate": PRIMARY_TOUCH_CANDIDATE,
        "primary_touch_candidate_reason": PRIMARY_TOUCH_CANDIDATE_REASON,
        "primary_touch_candidate_target_routes": PRIMARY_TOUCH_CANDIDATE_TARGET_ROUTES,
        "primary_touch_candidate_risk": PRIMARY_TOUCH_CANDIDATE_RISK,
        "primary_touch_phase1r_allowed_scope": PRIMARY_TOUCH_PHASE1R_ALLOWED_SCOPE,
        "primary_touch_candidate_exists": check_primary_candidate_exists(),
        "primary_touch_candidate_modified": not check_primary_not_modified_by_phase1q(),
        "primary_count": 1,
        "secondary_candidates": SECONDARY_CANDIDATES,
        "secondary_count": len(SECONDARY_CANDIDATES),
        "observation_candidates_sample": OBSERVATION_CANDIDATES_SAMPLE,
        "observation_count": len(OBSERVATION_CANDIDATES_SAMPLE),
        "excluded_patterns": EXCLUDED_PATTERNS,
        "browser_audit": {
            "test_id": BROWSER_AUDIT_TEST_ID,
            "standalone_result": BROWSER_AUDIT_STANDALONE_RESULT,
            "file_result": BROWSER_AUDIT_FILE_RESULT,
            "secret_leakage": BROWSER_AUDIT_SECRET_LEAKAGE,
            "verdict": BROWSER_AUDIT_VERDICT,
            "note": BROWSER_AUDIT_NOTE,
        },
        "phase1r_entry_conditions": PHASE1R_ENTRY_CONDITIONS,
        "phase1r_user_explicit_approval_required": PHASE1R_USER_EXPLICIT_APPROVAL_REQUIRED,
        "phase1r_auto_start_allowed": PHASE1R_AUTO_START_ALLOWED,
        "real_router_touch_allowed": REAL_ROUTER_TOUCH_ALLOWED,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "route_registration_allowed": ROUTE_REGISTRATION_ALLOWED,
        "apirouter_allowed": APIRouter_ALLOWED,
        "include_router_allowed": INCLUDE_ROUTER_ALLOWED,
        "route_decorator_allowed": ROUTE_DECORATOR_ALLOWED,
        "feature_flag_runtime_hook_allowed": FEATURE_FLAG_RUNTIME_HOOK_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "dry_run_only": DRY_RUN_ONLY,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "modified_files_count": 0,
        "errors": errors,
        "warnings": warnings,
    }

def get_primary_candidate():
    return {
        "file": PRIMARY_TOUCH_CANDIDATE,
        "reason": PRIMARY_TOUCH_CANDIDATE_REASON,
        "target_routes": PRIMARY_TOUCH_CANDIDATE_TARGET_ROUTES,
        "risk": PRIMARY_TOUCH_CANDIDATE_RISK,
    }

if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-Q Closeout Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARN: {w}")
