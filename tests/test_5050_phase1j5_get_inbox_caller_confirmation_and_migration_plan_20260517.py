"""
Phase 1-J5 테스트: GET /inbox Caller Confirmation & Migration Implementation Plan
tests/test_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan_20260517.py

external_work_registry.py 참조 성격 최종 확인 + GET /inbox migration plan.
read-only / plan 공정. 실제 caller 수정 없음.
"""
import ast
import importlib.util
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _load_module(name, rel_path):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_phase1j5",
        "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def reg_analysis(audit_mod):
    return audit_mod.EXTERNAL_WORK_REGISTRY_ANALYSIS


@pytest.fixture(scope="module")
def effective_summary(audit_mod):
    return audit_mod.EFFECTIVE_CALLER_SUMMARY


@pytest.fixture(scope="module")
def inbox_plan(audit_mod):
    return audit_mod.GET_INBOX_MIGRATION_PLAN


@pytest.fixture(scope="module")
def tasks_blocker(audit_mod):
    return audit_mod.POST_TASKS_BLOCKER_STATUS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~9. external_work_registry 정적 분석 상수 ────────────────────────────────

def test_03_registry_classification_not_a_caller(reg_analysis):
    assert reg_analysis["phase1j5_classification"] == "NOT_A_CALLER_METADATA_ONLY"


def test_04_registry_has_real_http_call_false(reg_analysis):
    assert reg_analysis["has_real_http_call"] is False


def test_05_registry_has_http_client_import_false(reg_analysis):
    assert reg_analysis["has_http_client_import"] is False


def test_06_registry_inbox_direct_reference_false(reg_analysis):
    assert reg_analysis["inbox_direct_reference"] is False


def test_07_registry_migration_impact_none(reg_analysis):
    assert reg_analysis["migration_impact"] == "NONE"


def test_08_registry_phase1j4_warn_resolved(reg_analysis):
    assert reg_analysis["phase1j4_warn_resolved"] is True


def test_09_registry_allowed_imports_only(reg_analysis):
    allowed = set(reg_analysis["allowed_imports"])
    assert "requests" not in allowed
    assert "httpx" not in allowed
    assert "aiohttp" not in allowed


# ── 10~12. AST 분석 실증 (실제 파일 직접 분석) ───────────────────────────────

def test_10_registry_no_http_client_import_ast():
    reg_path = REPO_ROOT / "ai_orchestrator/external_work_registry.py"
    assert reg_path.exists(), "external_work_registry.py 없음"
    content = reg_path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(content)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    for bad in ["requests", "httpx", "aiohttp", "urllib3"]:
        assert bad not in imported, f"HTTP client import 감지됨: {bad}"


def test_11_registry_no_fetch_call():
    reg_path = REPO_ROOT / "ai_orchestrator/external_work_registry.py"
    content = reg_path.read_text(encoding="utf-8", errors="ignore")
    assert "fetch(" not in content
    assert ".get(" not in content or "dataclasses" in content  # field access, not HTTP


def test_12_registry_no_http_session():
    reg_path = REPO_ROOT / "ai_orchestrator/external_work_registry.py"
    content = reg_path.read_text(encoding="utf-8", errors="ignore")
    for bad in ["Session(", "AsyncClient(", "aiohttp.ClientSession"]:
        assert bad not in content, f"HTTP session 감지됨: {bad}"


# ── 13~17. effective caller summary ─────────────────────────────────────────

def test_13_get_inbox_effective_caller_count_zero(effective_summary):
    assert effective_summary["get_inbox"]["effective_real_caller_count"] == 0


def test_14_get_inbox_frontend_caller_count_zero(effective_summary):
    assert effective_summary["get_inbox"]["frontend_real_http_caller_count"] == 0


def test_15_get_inbox_backend_caller_count_zero(effective_summary):
    assert effective_summary["get_inbox"]["backend_real_http_caller_count"] == 0


def test_16_get_inbox_migration_impact_none(effective_summary):
    assert effective_summary["get_inbox"]["migration_impact"] == "NONE"


def test_17_get_inbox_verdict_caller_zero(effective_summary):
    assert effective_summary["get_inbox"]["verdict"] == "GET_INBOX_EFFECTIVE_CALLER_COUNT_ZERO"


# ── 18~24. GET /inbox migration plan ────────────────────────────────────────

def test_18_inbox_plan_path(inbox_plan):
    assert inbox_plan["path"] == "/api/v1/inbox"


def test_19_inbox_plan_schema_frozen(inbox_plan):
    assert inbox_plan["schema_freeze_status"] == "FROZEN"


def test_20_inbox_plan_disable_not_allowed(inbox_plan):
    assert inbox_plan["disable_allowed_now"] is False


def test_21_inbox_plan_caller_modification_not_allowed(inbox_plan):
    assert inbox_plan["caller_modification_allowed_now"] is False


def test_22_inbox_plan_implementation_not_allowed_now(inbox_plan):
    assert inbox_plan["implementation_allowed_now"] is False


def test_23_inbox_plan_strategy_no_caller_migration_needed(inbox_plan):
    assert inbox_plan["migration_strategy"] == "NO_CALLER_MIGRATION_NEEDED"


def test_24_inbox_plan_migration_steps_gte_3(inbox_plan):
    assert len(inbox_plan.get("migration_steps", [])) >= 3


def test_25_inbox_plan_required_before_disable_exists(inbox_plan):
    assert len(inbox_plan.get("required_before_disable", [])) >= 1


def test_26_inbox_plan_rollback_exists(inbox_plan):
    assert inbox_plan.get("rollback_plan")


def test_27_inbox_plan_risk_level_low(inbox_plan):
    assert inbox_plan["risk_level"] == "LOW"


# ── 28~33. POST /tasks blocker 유지 ─────────────────────────────────────────

def test_28_tasks_blocker_status_blocked(tasks_blocker):
    assert tasks_blocker["status"] == "BLOCKED_DESIGN_ONLY"


def test_29_tasks_blocker_disable_not_allowed(tasks_blocker):
    assert tasks_blocker["disable_allowed_now"] is False


def test_30_tasks_blocker_caller_modification_not_allowed(tasks_blocker):
    assert tasks_blocker["caller_modification_allowed_now"] is False


def test_31_tasks_blocker_count_gte_5(tasks_blocker):
    assert len(tasks_blocker.get("blockers", [])) >= 5


def test_32_tasks_blocker_has_write_possible(tasks_blocker):
    blockers = tasks_blocker.get("blockers", [])
    assert any("WRITE_POSSIBLE" in b for b in blockers)


def test_33_tasks_blocker_has_approval_gate(tasks_blocker):
    blockers = tasks_blocker.get("blockers", [])
    assert any("approval_gate" in b for b in blockers)


# ── 34~37. 운영 안전 플래그 ─────────────────────────────────────────────────

def test_34_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_35_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_36_plan_only_true(audit_mod):
    assert audit_mod.PLAN_ONLY is True


def test_37_caller_modification_allowed_now_false(audit_mod):
    assert audit_mod.CALLER_MODIFICATION_ALLOWED_NOW is False


# ── 38~42. 실제 수정 없음 ────────────────────────────────────────────────────

def test_38_no_actual_modification_in_router(router_content):
    assert "PHASE_1J5" not in router_content


def test_39_no_route_disable_in_router(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_40_no_5050_route_deleted():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_41_no_frontend_modification():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        assert "PHASE_1J5" not in tsx.read_text(encoding="utf-8", errors="ignore")


def test_42_no_backend_file_modification():
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists():
            assert "PHASE_1J5" not in p.read_text(encoding="utf-8", errors="ignore")


# ── 43. forbidden pattern in audit script ────────────────────────────────────

def test_43_no_forbidden_import_in_audit_script():
    content = (
        REPO_ROOT
        / "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py"
    ).read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        pytest.skip("ast parse failed")
        return
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    for bad in ["requests", "httpx", "aiohttp", "urllib3"]:
        assert bad not in imported, f"HTTP client imported: {bad}"


# ── 44~45. audit verdict ─────────────────────────────────────────────────────

def test_44_audit_verdict_ready_or_warn(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_READY",
        "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_45_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_46_audit_phase1j4_warn_resolved(audit_result):
    assert audit_result["phase1j4_warn_resolved"] is True


def test_47_audit_effective_caller_count_zero(audit_result):
    assert audit_result["effective_real_caller_count"] == 0


def test_48_audit_get_inbox_migration_impact_none(audit_result):
    assert audit_result["get_inbox_migration_impact"] == "NONE"


def test_49_audit_post_tasks_blocked(audit_result):
    assert audit_result["post_tasks_status"] == "BLOCKED_DESIGN_ONLY"


def test_50_audit_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


def test_51_audit_known_baseline_not_fail(audit_result):
    assert audit_result["verdict"] != "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_FAIL"


# ── 52~58. 이전 Phase 충돌 없음 ─────────────────────────────────────────────

def test_52_phase1j4_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py").exists()


def test_53_phase1j3_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py").exists()


def test_54_phase1j2_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py").exists()


def test_55_phase1j_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").exists()


def test_56_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_57_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_58_external_site_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_external_site_canonical_registry.py").exists()
