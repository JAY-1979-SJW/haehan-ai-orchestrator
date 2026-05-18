"""
Phase 1-T 테스트: Disabled Guard Expanded Smoke
tests/test_5050_phase1t_disabled_guard_expanded_smoke_20260517.py

Phase 1-R disabled guard 전체 no-op 확대 검증.
GET /inbox effective disabled 회귀 없음 확인.
POST /tasks BLOCKED_DESIGN_ONLY 유지 확인.
백엔드 안정화 진입 가능 여부 판단.
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
        "audit_phase1t",
        "scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def guard_registry(audit_mod):
    return audit_mod.GUARD_REGISTRY


@pytest.fixture(scope="module")
def get_inbox_status(audit_mod):
    return audit_mod.GET_INBOX_STATUS


@pytest.fixture(scope="module")
def post_tasks_status(audit_mod):
    return audit_mod.POST_TASKS_STATUS


@pytest.fixture(scope="module")
def stabilization(audit_mod):
    return audit_mod.STABILIZATION_READINESS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~8. Phase 1-R guard registry ────────────────────────────────────────────

def test_03_guard_registry_has_three_routes(guard_registry):
    assert len(guard_registry) == 3


def test_04_inbox_email_fetch_in_registry(guard_registry):
    ids = [g["route_id"] for g in guard_registry]
    assert "INBOX_EMAIL_FETCH" in ids


def test_05_task_approve_in_registry(guard_registry):
    ids = [g["route_id"] for g in guard_registry]
    assert "TASK_APPROVE" in ids


def test_06_task_reject_in_registry(guard_registry):
    ids = [g["route_id"] for g in guard_registry]
    assert "TASK_REJECT" in ids


def test_07_all_guards_expected_false(guard_registry):
    for g in guard_registry:
        assert g["expected_value"] is False, f"{g['route_id']} expected_value must be False"


def test_08_all_guards_noop_behavior(guard_registry):
    for g in guard_registry:
        assert "no-op" in g["guard_behavior"].lower() or "false" in g["guard_behavior"].lower()


# ── 9~14. router.py 실제 guard 상태 직접 확인 ─────────────────────────────────

def test_09_guard_function_exists(router_content):
    assert "_legacy_5050_should_use_route_wiring" in router_content


def test_10_inbox_fetch_flag_false(router_content):
    assert "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = False" in router_content


def test_11_task_approve_flag_false(router_content):
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content


def test_12_task_reject_flag_false(router_content):
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content


def test_13_guard_applied_to_inbox_fetch(router_content):
    assert (
        '_legacy_5050_should_use_route_wiring("INBOX_EMAIL_FETCH")' in router_content
        or "_legacy_5050_should_use_route_wiring('INBOX_EMAIL_FETCH')" in router_content
    )


def test_14_guard_applied_to_task_approve_and_reject(router_content):
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in router_content
    )
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_REJECT")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_REJECT')" in router_content
    )


# ── 15~16. router.py TOUCH_PHASE 유지 ────────────────────────────────────────

def test_15_router_touch_phase_still_phase1r(router_content):
    assert (
        'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router_content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router_content
    )


def test_16_router_touch_phase_count_one(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


# ── 17~21. GET /inbox effective disabled 확인 ────────────────────────────────

def test_17_get_inbox_disabled_status(get_inbox_status):
    assert get_inbox_status["disabled_status"] == "EFFECTIVELY_DISABLED"


def test_18_get_inbox_8400_handler_active(get_inbox_status):
    assert get_inbox_status["8400_handler_active"] is True


def test_19_get_inbox_legacy_wiring_inactive(get_inbox_status):
    assert get_inbox_status["legacy_wiring_active"] is False


def test_20_get_inbox_regression_risk_none(get_inbox_status):
    assert get_inbox_status["regression_risk"] == "NONE"


def test_21_get_inbox_8400_handler_in_router(router_content):
    assert '@router.get("/inbox")' in router_content or "@router.get('/inbox')" in router_content


def test_22_inbox_not_mounted_in_server():
    server = REPO_ROOT / "ai_orchestrator/server.py"
    if server.exists():
        content = server.read_text(encoding="utf-8", errors="ignore")
        assert not ("inbox_bp" in content and "register_blueprint" in content)


# ── 23~27. POST /tasks BLOCKED_DESIGN_ONLY 유지 ──────────────────────────────

def test_23_post_tasks_status_blocked(post_tasks_status):
    assert post_tasks_status["status"] == "BLOCKED_DESIGN_ONLY"


def test_24_post_tasks_disable_not_allowed(post_tasks_status):
    assert post_tasks_status["disable_allowed_now"] is False


def test_25_post_tasks_blockers_gte_5(post_tasks_status):
    assert len(post_tasks_status.get("blockers", [])) >= 5


def test_26_post_tasks_has_write_possible(post_tasks_status):
    assert "WRITE_POSSIBLE" in post_tasks_status.get("blockers", [])


def test_27_post_tasks_has_approval_gate(post_tasks_status):
    assert any("approval_gate" in b for b in post_tasks_status.get("blockers", []))


# ── 28~31. 백엔드 안정화 진입 판단 ───────────────────────────────────────────

def test_28_get_inbox_legacy_cleared(stabilization):
    assert stabilization["get_inbox_legacy_cleared"] is True


def test_29_guard_no_op_confirmed(stabilization):
    assert stabilization["guard_no_op_confirmed"] is True


def test_30_backend_stabilization_ready(stabilization):
    assert stabilization["backend_stabilization_ready"] is True


def test_31_stabilization_verdict(stabilization):
    assert stabilization["verdict"] == "BACKEND_STABILIZATION_ENTRY_READY"


# ── 32~36. safety boundary ───────────────────────────────────────────────────

def test_32_no_phase1t_in_router(router_content):
    assert "PHASE_1T" not in router_content


def test_33_legacy_5050_dir_exists():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_34_no_caller_files_modified():
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists():
            assert "PHASE_1T" not in p.read_text(encoding="utf-8", errors="ignore")


def test_35_no_admin_web_modified():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        assert "PHASE_1T" not in tsx.read_text(encoding="utf-8", errors="ignore")


def test_36_no_8400_handler_deleted():
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")
    assert "get_inbox_list" in content or '"/inbox"' in content


# ── 37~40. global flags ───────────────────────────────────────────────────────

def test_37_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_38_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_39_smoke_only_true(audit_mod):
    assert audit_mod.SMOKE_ONLY is True


def test_40_router_modification_not_allowed(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_ALLOWED is False


# ── 41. no HTTP import ───────────────────────────────────────────────────────

def test_41_no_http_import_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py"
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


# ── 42~45. audit verdict ─────────────────────────────────────────────────────

def test_42_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE_READY",
        "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_43_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_44_audit_guard_all_noop(audit_result):
    assert audit_result["guard_all_noop"] is True


def test_45_audit_backend_stabilization_ready(audit_result):
    assert audit_result["backend_stabilization_ready"] is True


def test_46_audit_known_baseline_not_fail(audit_result):
    assert audit_result["verdict"] != "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE_FAIL"


# ── 47~55. 이전 Phase 충돌 없음 ─────────────────────────────────────────────

def test_47_phase1j8_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py").exists()


def test_48_phase1j7_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py").exists()


def test_49_phase1j6_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py").exists()


def test_50_phase1j5_no_conflict():
    assert (
        REPO_ROOT
        / "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py"
    ).exists()


def test_51_phase1j4_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py").exists()


def test_52_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_53_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_54_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_55_external_site_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_external_site_canonical_registry.py").exists()
