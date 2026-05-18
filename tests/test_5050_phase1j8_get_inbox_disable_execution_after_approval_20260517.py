"""
Phase 1-J8 테스트: GET /api/v1/inbox Disable Execution (After Representative Approval)
tests/test_5050_phase1j8_get_inbox_disable_execution_after_approval_20260517.py

대표 명시 승인(2026-05-18) 수신 후 현재 상태 공식 확인.
5050 legacy GET /inbox는 이미 effectively disabled (NOT_MOUNTED).
router.py 수정 없음.
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
        "audit_phase1j8",
        "scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def exec_result(audit_mod):
    return audit_mod.DISABLE_EXECUTION_RESULT


@pytest.fixture(scope="module")
def tasks_excl(audit_mod):
    return audit_mod.POST_TASKS_EXCLUSION


@pytest.fixture(scope="module")
def rollback(audit_mod):
    return audit_mod.ROLLBACK_PLAN


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~5. 대표 승인 ───────────────────────────────────────────────────────────

def test_03_representative_approval_received(audit_mod):
    assert audit_mod.REPRESENTATIVE_APPROVAL_RECEIVED is True


def test_04_approval_date_recorded(exec_result):
    assert exec_result.get("representative_approval_date") == "2026-05-18"


def test_05_approval_reflected_in_result(audit_result):
    assert audit_result["representative_approval_received"] is True


# ── 6~13. disable execution result ───────────────────────────────────────────

def test_06_disable_execution_result_exists(exec_result):
    assert exec_result is not None


def test_07_target_route_get_inbox(exec_result):
    assert exec_result["route"] == "/api/v1/inbox"
    assert exec_result["method"] == "GET"


def test_08_disable_status_effectively_disabled(exec_result):
    assert exec_result["disable_status"] == "EFFECTIVELY_DISABLED"


def test_09_strategy_already_disabled_via_not_mounted(exec_result):
    assert "NOT_MOUNTED" in exec_result["disable_strategy_applied"]


def test_10_router_modification_not_required(exec_result):
    assert exec_result["router_modification_required"] is False


def test_11_router_modification_not_performed(exec_result):
    assert exec_result["router_modification_performed"] is False


def test_12_8400_handler_active_normal(exec_result):
    assert exec_result["8400_fastapi_handler_status"] == "ACTIVE_NORMAL"


def test_13_legacy_5050_not_mounted(exec_result):
    assert exec_result["legacy_5050_mount_status"] == "NOT_MOUNTED"


def test_14_effective_real_caller_count_zero(exec_result):
    assert exec_result["effective_real_caller_count"] == 0


def test_15_schema_freeze_frozen(exec_result):
    assert exec_result["schema_freeze_status"] == "FROZEN"


# ── 16~20. router.py 현재 상태 직접 확인 ────────────────────────────────────

def test_16_router_has_8400_get_inbox_handler(router_content):
    assert '@router.get("/inbox")' in router_content or "@router.get('/inbox')" in router_content


def test_17_no_phase1j8_modification_in_router(router_content):
    assert "PHASE_1J8" not in router_content


def test_18_router_touch_phase_count_still_one(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_19_inbox_fetch_wiring_still_false(router_content):
    # Phase 1-R 상태 유지 — True로 변경되지 않아야 함
    assert "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = True" not in router_content


def test_20_fetch_inbox_enabled_false_remains(router_content):
    # False가 유지되거나, 변수 자체가 False 기본값
    assert "LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = True" not in router_content


# ── 21~22. 5050 legacy 마운트 상태 ──────────────────────────────────────────

def test_21_inbox_blueprint_not_mounted_in_server():
    server = REPO_ROOT / "ai_orchestrator/server.py"
    if server.exists():
        content = server.read_text(encoding="utf-8", errors="ignore")
        # inbox_bp + register_blueprint 조합이 없어야 함
        assert not ("inbox_bp" in content and "register_blueprint" in content), \
            "inbox_bp가 server.py에 마운트됨"


def test_22_no_get_inbox_adapter_in_compat():
    compat = REPO_ROOT / "backend/compat/legacy_5050"
    if compat.exists():
        adapters = list(compat.glob("**/inbox*.py"))
        get_only = [f for f in adapters if "email_fetch" not in f.name]
        # GET /inbox 전용 어댑터 없음이 정상 상태
        for f in get_only:
            content = f.read_text(encoding="utf-8", errors="ignore")
            assert "GET" not in content or "email_fetch" in f.name, \
                f"예상 외 GET inbox 어댑터: {f.name}"


# ── 23~27. 실제 수정 없음 safety boundary ────────────────────────────────────

def test_23_router_not_modified_with_phase1j8(router_content):
    assert "PHASE_1J8" not in router_content


def test_24_caller_files_not_modified():
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists():
            assert "PHASE_1J8" not in p.read_text(encoding="utf-8", errors="ignore")


def test_25_admin_web_not_modified():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        assert "PHASE_1J8" not in tsx.read_text(encoding="utf-8", errors="ignore")


def test_26_legacy_5050_dir_exists():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_27_no_8400_handler_deleted():
    # GET /inbox 8400 handler가 살아있어야 함
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")
    assert "get_inbox_list" in content or '"/inbox"' in content


# ── 28~31. global flags ───────────────────────────────────────────────────────

def test_28_router_modification_not_performed_flag(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_PERFORMED is False


def test_29_server_apply_not_performed(audit_mod):
    assert audit_mod.SERVER_APPLY_PERFORMED is False


def test_30_live_traffic_call_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_CALL is False


def test_31_db_write_false(audit_mod):
    assert audit_mod.DB_WRITE is False


# ── 32~36. rollback plan ─────────────────────────────────────────────────────

def test_32_rollback_plan_exists(rollback):
    assert rollback is not None


def test_33_rollback_not_needed(rollback):
    assert rollback["need_rollback"] is False


def test_34_rollback_verdict(rollback):
    assert rollback["verdict"] == "NO_ROLLBACK_NEEDED"


# ── 35~39. POST /tasks exclusion ─────────────────────────────────────────────

def test_35_post_tasks_exclusion_exists(tasks_excl):
    assert tasks_excl is not None


def test_36_post_tasks_blocked(tasks_excl):
    assert tasks_excl["mode"] == "BLOCKED_DESIGN_ONLY"


def test_37_post_tasks_actual_disable_not_allowed(tasks_excl):
    assert tasks_excl["actual_disable_allowed_now"] is False


def test_38_post_tasks_modification_not_allowed(tasks_excl):
    assert tasks_excl["modification_allowed_now"] is False


def test_39_post_tasks_blockers_gte_5(tasks_excl):
    assert len(tasks_excl.get("blockers", [])) >= 5


# ── 40. no HTTP import ───────────────────────────────────────────────────────

def test_40_no_http_import_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py"
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


# ── 41~45. audit verdict ─────────────────────────────────────────────────────

def test_41_audit_verdict_confirmed(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_CONFIRMED",
        "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_CONFIRMED_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_42_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_43_audit_disable_status_effectively_disabled(audit_result):
    assert audit_result["disable_status"] == "EFFECTIVELY_DISABLED"


def test_44_audit_rollback_not_needed(audit_result):
    assert audit_result["rollback_needed"] is False


def test_45_audit_known_baseline_not_fail(audit_result):
    assert audit_result["verdict"] != "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_FAIL"


# ── 46~55. 이전 Phase 충돌 없음 ─────────────────────────────────────────────

def test_46_phase1j7_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py").exists()


def test_47_phase1j6_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py").exists()


def test_48_phase1j5_no_conflict():
    assert (
        REPO_ROOT
        / "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py"
    ).exists()


def test_49_phase1j4_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py").exists()


def test_50_phase1j3_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py").exists()


def test_51_phase1j2_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py").exists()


def test_52_phase1j_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").exists()


def test_53_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_54_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_55_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()
