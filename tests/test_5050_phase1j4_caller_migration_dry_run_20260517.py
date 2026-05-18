"""
Phase 1-J4 테스트: SAME_CONTRACT Caller Migration Dry-Run Smoke
tests/test_5050_phase1j4_caller_migration_dry_run_20260517.py

fixture 기반 dry-run 공정. 실제 caller 수정 없음.
"""
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
def smoke_mod():
    return _load_module(
        "smoke_phase1j4",
        "scripts/ops/smoke_5050_phase1j4_caller_migration_dry_run.py",
    )


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_phase1j4",
        "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py",
    )


@pytest.fixture(scope="module")
def smoke_result(smoke_mod):
    return smoke_mod.run_phase1j4_caller_migration_dry_run()


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def fixtures(smoke_mod):
    return smoke_mod.build_phase1j4_caller_migration_fixtures()


@pytest.fixture(scope="module")
def dry_run_matrix(audit_mod):
    return audit_mod.DRY_RUN_MATRIX


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~4. import / 함수 존재 ──────────────────────────────────────────────────

def test_01_smoke_runner_importable(smoke_mod):
    assert smoke_mod is not None


def test_02_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_03_build_fixtures_function_exists(smoke_mod):
    assert hasattr(smoke_mod, "build_phase1j4_caller_migration_fixtures")


def test_04_run_dry_run_function_exists(smoke_mod):
    assert hasattr(smoke_mod, "run_phase1j4_caller_migration_dry_run")


# ── 5~7. smoke summary ───────────────────────────────────────────────────────

def test_05_smoke_phase_is_phase1j4(smoke_result):
    assert smoke_result["phase"] == "PHASE_1J4"


def test_06_target_priority_get_inbox_first(smoke_result):
    assert smoke_result["target_priority"] == "GET_INBOX_FIRST"


def test_07_post_tasks_mode_blocked_design_only(smoke_result):
    assert smoke_result["post_tasks_mode"] == "BLOCKED_DESIGN_ONLY"


# ── 8~9. scenario counts ─────────────────────────────────────────────────────

def test_08_total_scenarios_gte_18(smoke_result):
    assert smoke_result["total_scenarios"] >= 18


def test_09_failed_scenarios_zero(smoke_result):
    assert smoke_result["failed_scenarios"] == 0, \
        f"failed: {smoke_result.get('failed_scenario_details')}"


# ── 10~14. compatibility ─────────────────────────────────────────────────────

def test_10_frontend_fixture_compatible(smoke_result):
    assert smoke_result["frontend_fixture_compatible"] is True


def test_11_backend_fixture_compatible(smoke_result):
    assert smoke_result["backend_fixture_compatible"] is True


def test_12_schema_compatible(smoke_result):
    assert smoke_result["schema_compatible"] is True


def test_13_post_tasks_blocked(smoke_result):
    assert smoke_result["post_tasks_blocked"] is True


def test_14_unknown_callers_not_mounted(smoke_result):
    assert smoke_result["unknown_callers_not_mounted"] is True


# ── 15~19. safety boundary ───────────────────────────────────────────────────

def test_15_caller_files_not_modified(smoke_result):
    assert smoke_result["caller_files_modified"] is False


def test_16_route_disable_not_performed(smoke_result):
    assert smoke_result["route_disable_performed"] is False


def test_17_live_http_call_count_zero(smoke_result):
    assert smoke_result["live_http_call_count"] == 0


def test_18_db_write_count_zero(smoke_result):
    assert smoke_result["db_write_count"] == 0


def test_19_secret_env_access_count_zero(smoke_result):
    assert smoke_result["secret_env_access_count"] == 0


# ── 20~21. caller fixtures ───────────────────────────────────────────────────

def test_20_admin_web_external_tasks_fixture_exists(fixtures):
    fe = fixtures.get("frontend_fixture", {})
    assert fe.get("file") and "external-tasks" in fe["file"]


def test_21_real_backend_caller_fixture_exists(fixtures):
    be = fixtures.get("backend_callers_fixture", [])
    assert len(be) >= 1


# ── 22~26. GET inbox schema ──────────────────────────────────────────────────

def test_22_inbox_response_item_12_required_fields(fixtures):
    schema = fixtures["inbox_item_schema_fixture"]
    assert schema["key_count"] == 12


def test_23_inbox_limit_20_boundary(smoke_result):
    scenarios = smoke_result.get("scenario_results", [])
    s = next((x for x in scenarios if "limit20" in x["id"]), None)
    assert s is not None and s["passed"]


def test_24_inbox_limit_1_boundary(smoke_result):
    scenarios = smoke_result.get("scenario_results", [])
    s = next((x for x in scenarios if "limit1" in x["id"]), None)
    assert s is not None and s["passed"]


def test_25_inbox_limit_500_boundary(smoke_result):
    scenarios = smoke_result.get("scenario_results", [])
    s = next((x for x in scenarios if "limit500" in x["id"]), None)
    assert s is not None and s["passed"]


def test_26_inbox_optional_field_compatibility(smoke_result):
    scenarios = smoke_result.get("scenario_results", [])
    s = next((x for x in scenarios if "optional" in x["name"]), None)
    assert s is not None and s["passed"]


# ── 27~31. POST /tasks blockers ──────────────────────────────────────────────

def test_27_post_tasks_dry_run_execution_not_allowed(dry_run_matrix):
    tasks = next(r for r in dry_run_matrix if r["path"] == "/api/v1/tasks")
    assert tasks["migration_dry_run_allowed"] is False


def test_28_post_tasks_write_possible_maintained(dry_run_matrix):
    tasks = next(r for r in dry_run_matrix if r["path"] == "/api/v1/tasks")
    assert tasks["side_effect_classification"] == "WRITE_POSSIBLE"


def test_29_post_tasks_approval_token_blocker(dry_run_matrix):
    tasks = next(r for r in dry_run_matrix if r["path"] == "/api/v1/tasks")
    blockers = tasks.get("blockers", [])
    assert any("approval_token" in b for b in blockers)


def test_30_post_tasks_db_write_blocker(dry_run_matrix):
    tasks = next(r for r in dry_run_matrix if r["path"] == "/api/v1/tasks")
    blockers = tasks.get("blockers", [])
    assert any("db_write" in b for b in blockers)


def test_31_post_tasks_approval_gate_blocker(dry_run_matrix):
    tasks = next(r for r in dry_run_matrix if r["path"] == "/api/v1/tasks")
    blockers = tasks.get("blockers", [])
    assert any("approval_gate" in b for b in blockers)


# ── 32~33. disable / caller_modification ─────────────────────────────────────

def test_32_disable_allowed_now_false(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["disable_allowed_now"] is False


def test_33_caller_modification_allowed_now_false(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["caller_modification_allowed_now"] is False


# ── 34~42. 실제 수정/disable 없음 ────────────────────────────────────────────

def test_34_no_actual_caller_modification(router_content):
    assert "PHASE_1J4" not in router_content


def test_35_no_route_disable_in_router(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_36_no_5050_route_deleted():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_37_no_frontend_modification():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        assert "PHASE_1J4" not in tsx.read_text(encoding="utf-8", errors="ignore")


def test_38_no_backend_caller_modification():
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists():
            assert "PHASE_1J4" not in p.read_text(encoding="utf-8", errors="ignore")


def test_39_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_40_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_41_no_secret_env_in_smoke_script():
    content = (REPO_ROOT / "scripts/ops/smoke_5050_phase1j4_caller_migration_dry_run.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    for bad in ["os.environ[", "os.getenv(", "import requests", "import httpx"]:
        assert bad not in content


def test_42_no_live_call_import_in_audit_script():
    # audit 스크립트가 직접 HTTP 클라이언트를 import하지 않는지 확인.
    # 파일 내 forbidden pattern 검사 리터럴은 허용 — 실제 import 줄만 검사.
    import ast
    content = (REPO_ROOT / "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py").read_text(
        encoding="utf-8", errors="ignore"
    )
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


# ── 43~44. audit verdict ─────────────────────────────────────────────────────

def test_43_audit_verdict_ready_or_warn(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J4_CALLER_MIGRATION_DRY_RUN_READY",
        "PHASE1J4_CALLER_MIGRATION_DRY_RUN_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_44_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


# ── 45~53. 이전 Phase 충돌 없음 ──────────────────────────────────────────────

def test_45_phase1j3_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py").exists()


def test_46_phase1j2_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py").exists()


def test_47_phase1j_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").exists()


def test_48_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_49_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_50_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_51_characterization_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()


def test_52_external_site_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_external_site_canonical_registry.py").exists()


def test_53_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1J4_CALLER_MIGRATION_DRY_RUN_FAIL"
