"""
Backend Operation Stabilization Final Audit 테스트
tests/test_backend_operation_stabilization_final_20260517.py

5050 → 8400 이관 공정 전체 종합 감리.
앱 착공 전 백엔드 준공 기준 확정.
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
        "audit_stabilization_final",
        "scripts/ops/audit_backend_operation_stabilization_final.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def phase_history(audit_mod):
    return audit_mod.PHASE_HISTORY


@pytest.fixture(scope="module")
def completed(audit_mod):
    return audit_mod.COMPLETED_ITEMS


@pytest.fixture(scope="module")
def pending(audit_mod):
    return audit_mod.PENDING_ITEMS


@pytest.fixture(scope="module")
def completion(audit_mod):
    return audit_mod.COMPLETION_CRITERIA


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~6. Phase 이력 ──────────────────────────────────────────────────────────

def test_03_phase_history_complete(phase_history):
    assert len(phase_history) >= 12


def test_04_all_phases_complete_status(phase_history):
    for ph in phase_history:
        assert ph["status"] == "COMPLETE", f"{ph['phase']} not COMPLETE"


def test_05_phase_1r_in_history(phase_history):
    phases = [p["phase"] for p in phase_history]
    assert "PHASE_1R" in phases


def test_06_phase_1t_in_history(phase_history):
    phases = [p["phase"] for p in phase_history]
    assert "PHASE_1T" in phases


# ── 7~12. GET /inbox 완료 확인 ───────────────────────────────────────────────

def test_07_get_inbox_effectively_disabled(completed):
    gi = completed["GET /api/v1/inbox"]
    assert gi["effective_disabled"] is True


def test_08_get_inbox_caller_count_zero(completed):
    assert completed["GET /api/v1/inbox"]["caller_count"] == 0


def test_09_get_inbox_schema_frozen(completed):
    assert completed["GET /api/v1/inbox"]["schema_frozen"] is True


def test_10_get_inbox_migration_not_needed(completed):
    assert completed["GET /api/v1/inbox"]["migration_needed"] is False


def test_11_get_inbox_legacy_not_mounted(completed):
    assert completed["GET /api/v1/inbox"]["legacy_wiring"] == "NOT_MOUNTED"


def test_12_get_inbox_8400_active(completed):
    assert completed["GET /api/v1/inbox"]["8400_handler"] == "ACTIVE_NORMAL"


# ── 13~16. Phase 1-R guard 완료 확인 ────────────────────────────────────────

def test_13_guard_inbox_fetch_noop(completed):
    assert "false" in completed["Phase_1R_guards"]["INBOX_EMAIL_FETCH"].lower() or \
           "no-op" in completed["Phase_1R_guards"]["INBOX_EMAIL_FETCH"].lower()


def test_14_guard_task_approve_noop(completed):
    assert "false" in completed["Phase_1R_guards"]["TASK_APPROVE"].lower() or \
           "no-op" in completed["Phase_1R_guards"]["TASK_APPROVE"].lower()


def test_15_guard_task_reject_noop(completed):
    assert "false" in completed["Phase_1R_guards"]["TASK_REJECT"].lower() or \
           "no-op" in completed["Phase_1R_guards"]["TASK_REJECT"].lower()


def test_16_schema_freeze_complete(completed):
    sf = completed["schema_freeze"]
    assert sf["GET_inbox_request"] == "FROZEN"
    assert sf["GET_inbox_response"] == "FROZEN"


# ── 17~21. POST /tasks 보류 확인 ─────────────────────────────────────────────

def test_17_post_tasks_blocked_design_only(pending):
    assert pending["POST /api/v1/tasks"]["status"] == "BLOCKED_DESIGN_ONLY"


def test_18_post_tasks_disable_not_allowed(pending):
    assert pending["POST /api/v1/tasks"]["disable_allowed_now"] is False


def test_19_post_tasks_blockers_gte_5(pending):
    assert len(pending["POST /api/v1/tasks"].get("blockers", [])) >= 5


def test_20_post_tasks_has_write_possible(pending):
    assert "WRITE_POSSIBLE" in pending["POST /api/v1/tasks"]["blockers"]


def test_21_post_tasks_has_approval_gate_blocker(pending):
    blockers = pending["POST /api/v1/tasks"]["blockers"]
    assert any("approval_gate" in b for b in blockers)


# ── 22~28. 준공 기준 ──────────────────────────────────────────────────────────

def test_22_completion_get_inbox_done(completion):
    assert completion["backend_phase1_legacy_GET_inbox"] == "COMPLETE"


def test_23_completion_guard_noop_done(completion):
    assert completion["backend_phase1r_guard_noop"] == "COMPLETE"


def test_24_completion_schema_freeze_done(completion):
    assert completion["backend_schema_freeze"] == "COMPLETE"


def test_25_completion_caller_analysis_done(completion):
    assert completion["backend_caller_analysis"] == "COMPLETE"


def test_26_completion_external_site_registry_done(completion):
    assert completion["backend_external_site_registry"] == "COMPLETE"


def test_27_completion_layer_audit_pass(completion):
    assert completion["backend_layer_audit"] == "PASS"


def test_28_completion_overall_verdict(completion):
    assert completion["overall_verdict"] == "BACKEND_PHASE1_LEGACY_INTEGRATION_AUDIT_COMPLETE"


# ── 29~34. router.py 안정성 직접 확인 ───────────────────────────────────────

def test_29_router_touch_phase_1r(router_content):
    assert (
        'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router_content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router_content
    )


def test_30_router_inbox_fetch_flag_false(router_content):
    assert "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = True" not in router_content


def test_31_router_task_approve_flag_false(router_content):
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = True" not in router_content


def test_32_router_task_reject_flag_false(router_content):
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = True" not in router_content


def test_33_router_8400_inbox_handler_exists(router_content):
    assert '@router.get("/inbox")' in router_content or "@router.get('/inbox')" in router_content


def test_34_router_guard_function_exists(router_content):
    assert "_legacy_5050_should_use_route_wiring" in router_content


# ── 35~38. safety boundary ───────────────────────────────────────────────────

def test_35_legacy_5050_dir_exists():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_36_no_unauthorized_router_modification(router_content):
    # 이 공정에서 새 Phase 태그 추가 없음
    assert "BACKEND_STABILIZATION" not in router_content


def test_37_inbox_not_mounted_in_server():
    server = REPO_ROOT / "ai_orchestrator/server.py"
    if server.exists():
        content = server.read_text(encoding="utf-8", errors="ignore")
        assert not ("inbox_bp" in content and "register_blueprint" in content)


def test_38_external_site_registry_exists():
    assert (REPO_ROOT / "scripts/ops/audit_external_site_canonical_registry.py").exists()


# ── 39~42. global flags ───────────────────────────────────────────────────────

def test_39_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_40_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_41_audit_only_true(audit_mod):
    assert audit_mod.AUDIT_ONLY is True


def test_42_router_modification_not_allowed(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_ALLOWED is False


# ── 43. no HTTP import ───────────────────────────────────────────────────────

def test_43_no_http_import_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_backend_operation_stabilization_final.py"
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


# ── 44~48. audit verdict ─────────────────────────────────────────────────────

def test_44_audit_verdict_complete(audit_result):
    assert audit_result["verdict"] in (
        "BACKEND_STABILIZATION_FINAL_AUDIT_COMPLETE",
        "BACKEND_STABILIZATION_FINAL_AUDIT_COMPLETE_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_45_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_46_audit_completed_phases_12(audit_result):
    assert audit_result["completed_phases"] >= 12


def test_47_audit_get_inbox_complete(audit_result):
    assert audit_result["get_inbox_status"] is True


def test_48_audit_guard_noop_all(audit_result):
    assert audit_result["guard_noop_all"] is True


def test_49_audit_post_tasks_blocked(audit_result):
    assert audit_result["post_tasks_status"] == "BLOCKED_DESIGN_ONLY"


def test_50_audit_known_baseline_not_fail(audit_result):
    assert audit_result["verdict"] != "BACKEND_STABILIZATION_FINAL_AUDIT_FAIL"


# ── 51~60. 전체 Phase 파일 존재 확인 ────────────────────────────────────────

def test_51_phase1t_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py").exists()


def test_52_phase1j8_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py").exists()


def test_53_phase1j7_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py").exists()


def test_54_phase1j6_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py").exists()


def test_55_phase1j5_exists():
    assert (
        REPO_ROOT
        / "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py"
    ).exists()


def test_56_phase1j4_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py").exists()


def test_57_phase1j3_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py").exists()


def test_58_phase1s_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_59_phase1r_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_60_characterization_exists():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()
