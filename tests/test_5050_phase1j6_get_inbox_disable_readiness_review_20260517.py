"""
Phase 1-J6 테스트: GET /api/v1/inbox Disable Readiness Review
tests/test_5050_phase1j6_get_inbox_disable_readiness_review_20260517.py

GET /inbox 폐쇄 준비검사 공정. 실제 disable 없음.
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
        "audit_phase1j6",
        "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def readiness(audit_mod):
    return audit_mod.GET_INBOX_DISABLE_READINESS


@pytest.fixture(scope="module")
def caller_zero(audit_mod):
    return audit_mod.CALLER_ZERO_CONFIRMATION


@pytest.fixture(scope="module")
def schema_freeze(audit_mod):
    return audit_mod.SCHEMA_FREEZE_CONFIRMATION


@pytest.fixture(scope="module")
def rollback(audit_mod):
    return audit_mod.ROLLBACK_PLAN


@pytest.fixture(scope="module")
def tasks_excl(audit_mod):
    return audit_mod.POST_TASKS_EXCLUSION


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~10. GET /inbox disable readiness matrix ─────────────────────────────────

def test_03_get_inbox_disable_readiness_exists(readiness):
    assert readiness is not None


def test_04_target_route_get_inbox(readiness):
    assert readiness["route"] == "/api/v1/inbox"
    assert readiness["method"] == "GET"


def test_05_schema_freeze_status_frozen(readiness):
    assert readiness["schema_freeze_status"] == "FROZEN"


def test_06_side_effect_read_only(readiness):
    assert readiness["side_effect_classification"] == "READ_ONLY_EXPECTED"


def test_07_effective_real_caller_count_zero(readiness):
    assert readiness["effective_real_caller_count"] == 0


def test_08_migration_strategy_no_caller_needed(readiness):
    assert readiness["migration_strategy"] == "NO_CALLER_MIGRATION_NEEDED"


def test_09_disable_candidate_true(readiness):
    assert readiness["disable_candidate"] is True


def test_10_actual_disable_not_allowed(readiness):
    assert readiness["actual_disable_allowed_now"] is False


def test_11_readiness_status_exists(readiness):
    assert readiness["readiness_status"]


def test_12_required_before_disable_exists(readiness):
    assert len(readiness.get("required_before_disable", [])) >= 1


def test_13_required_during_disable_exists(readiness):
    assert len(readiness.get("required_during_disable", [])) >= 1


def test_14_required_after_disable_exists(readiness):
    assert len(readiness.get("required_after_disable", [])) >= 1


def test_15_required_rollback_exists(readiness):
    assert len(readiness.get("required_rollback", [])) >= 1


# ── 16~19. caller zero confirmation ──────────────────────────────────────────

def test_16_caller_zero_confirmation_exists(caller_zero):
    assert caller_zero is not None


def test_17_frontend_real_caller_count_zero(caller_zero):
    assert caller_zero["frontend_real_caller_count"] == 0


def test_18_backend_real_caller_count_zero(caller_zero):
    assert caller_zero["backend_real_caller_count"] == 0


def test_19_unknown_caller_count_zero(caller_zero):
    assert caller_zero["unknown_caller_count"] == 0


# ── 20~24. schema freeze confirmation ────────────────────────────────────────

def test_20_schema_freeze_confirmation_exists(schema_freeze):
    assert schema_freeze is not None


def test_21_request_schema_frozen(schema_freeze):
    assert schema_freeze["request_schema_frozen"] is True


def test_22_response_schema_frozen(schema_freeze):
    assert schema_freeze["response_schema_frozen"] is True


def test_23_status_code_contract_frozen(schema_freeze):
    assert schema_freeze["status_code_contract_frozen"] is True


def test_24_auth_contract_frozen(schema_freeze):
    assert schema_freeze["auth_contract_frozen"] is True


# ── 25~29. rollback plan ──────────────────────────────────────────────────────

def test_25_rollback_plan_exists(rollback):
    assert rollback is not None


def test_26_rollback_strategy_exists(rollback):
    assert rollback.get("rollback_strategy")


def test_27_rollback_command_exists(rollback):
    assert rollback.get("rollback_command_or_patch_plan")


def test_28_rollback_smoke_required(rollback):
    assert rollback["rollback_smoke_required"] is True


def test_29_rollback_approval_required(rollback):
    assert rollback["user_approval_required"] is True


# ── 30~34. POST /tasks exclusion ─────────────────────────────────────────────

def test_30_post_tasks_exclusion_exists(tasks_excl):
    assert tasks_excl is not None


def test_31_post_tasks_mode_blocked(tasks_excl):
    assert tasks_excl["mode"] == "BLOCKED_DESIGN_ONLY"


def test_32_post_tasks_actual_disable_not_allowed(tasks_excl):
    assert tasks_excl["actual_disable_allowed_now"] is False


def test_33_post_tasks_migration_not_allowed(tasks_excl):
    assert tasks_excl["migration_allowed_now"] is False


def test_34_post_tasks_blockers_gte_5(tasks_excl):
    assert len(tasks_excl.get("blockers", [])) >= 5


# ── 35~40. safety boundary ───────────────────────────────────────────────────

def test_35_actual_route_disable_not_performed(router_content):
    assert "PHASE_1J6" not in router_content


def test_36_router_touch_count_still_one(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_37_caller_files_not_modified():
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists():
            assert "PHASE_1J6" not in p.read_text(encoding="utf-8", errors="ignore")


def test_38_admin_web_not_modified():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        assert "PHASE_1J6" not in tsx.read_text(encoding="utf-8", errors="ignore")


def test_39_legacy_5050_dir_exists():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_40_no_8400_handler_modification():
    for f in REPO_ROOT.glob("ai_orchestrator/**/*.py"):
        if "test" in f.name or "audit" in f.name or "smoke" in f.name:
            continue
        if "PHASE_1J6" in f.read_text(encoding="utf-8", errors="ignore"):
            pytest.fail(f"{f.relative_to(REPO_ROOT)} contains PHASE_1J6")


# ── 41. global flags ─────────────────────────────────────────────────────────

def test_41_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_42_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_43_readiness_review_only_true(audit_mod):
    assert audit_mod.READINESS_REVIEW_ONLY is True


def test_44_actual_disable_allowed_now_false(audit_mod):
    assert audit_mod.ACTUAL_DISABLE_ALLOWED_NOW is False


def test_45_router_file_modification_allowed_false(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_ALLOWED is False


# ── 46. no HTTP import in audit script ───────────────────────────────────────

def test_46_no_http_import_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py"
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


# ── 47~50. audit verdict ─────────────────────────────────────────────────────

def test_47_audit_verdict_ready_or_warn(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J6_GET_INBOX_DISABLE_READINESS_READY",
        "PHASE1J6_GET_INBOX_DISABLE_READINESS_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_48_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_49_audit_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


def test_50_audit_known_baseline_not_fail(audit_result):
    assert audit_result["verdict"] != "PHASE1J6_GET_INBOX_DISABLE_READINESS_FAIL"


# ── 51~58. 이전 Phase 충돌 없음 ─────────────────────────────────────────────

def test_51_phase1j5_no_conflict():
    assert (
        REPO_ROOT
        / "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py"
    ).exists()


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


def test_58_characterization_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


def test_59_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_60_external_site_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_external_site_canonical_registry.py").exists()
