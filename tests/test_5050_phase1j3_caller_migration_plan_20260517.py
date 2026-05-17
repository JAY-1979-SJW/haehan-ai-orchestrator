"""
Phase 1-J3 테스트: SAME_CONTRACT Caller Migration Plan
tests/test_5050_phase1j3_caller_migration_plan_20260517.py

read-only / plan 공정. 실제 caller 수정 없음.
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
def audit_mod():
    return _load_module(
        "audit_phase1j3",
        "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def plan(audit_mod):
    return audit_mod.MIGRATION_PLAN


@pytest.fixture(scope="module")
def caller_inv(audit_mod):
    return audit_mod.CALLER_INVENTORY


@pytest.fixture(scope="module")
def unknown_mount(audit_mod):
    return audit_mod.UNKNOWN_CALLER_MOUNT_STATUS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1. import ────────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


# ── 2~4. plan 기본 ───────────────────────────────────────────────────────────

def test_02_migration_plan_has_two_rows(plan):
    assert len(plan) == 2


def test_03_get_inbox_row_exists(plan):
    assert any(r["path"] == "/api/v1/inbox" for r in plan)


def test_04_post_tasks_row_exists(plan):
    assert any(r["path"] == "/api/v1/tasks" for r in plan)


# ── 5~7. disable / caller_modification 금지 ──────────────────────────────────

def test_05_disable_allowed_now_false(plan):
    for row in plan:
        assert row["disable_allowed_now"] is False


def test_06_caller_modification_allowed_now_false(plan):
    for row in plan:
        assert row["caller_modification_allowed_now"] is False


def test_07_schema_freeze_status_frozen(plan):
    for row in plan:
        assert row["schema_freeze_status"] == "FROZEN"


# ── 8~11. side_effect / migration_priority ───────────────────────────────────

def test_08_inbox_side_effect_read_only(plan):
    inbox = next(r for r in plan if r["path"] == "/api/v1/inbox")
    assert inbox["side_effect_classification"] == "READ_ONLY_EXPECTED"


def test_09_tasks_side_effect_write_possible(plan):
    tasks = next(r for r in plan if r["path"] == "/api/v1/tasks")
    assert tasks["side_effect_classification"] == "WRITE_POSSIBLE"


def test_10_inbox_migration_priority_first(plan):
    inbox = next(r for r in plan if r["path"] == "/api/v1/inbox")
    assert inbox["migration_priority"] == "FIRST"


def test_11_tasks_migration_priority_later(plan):
    tasks = next(r for r in plan if r["path"] == "/api/v1/tasks")
    assert tasks["migration_priority"] == "LATER"


# ── 12~20. caller inventory ──────────────────────────────────────────────────

def test_12_real_frontend_callers_exist(caller_inv):
    assert len(caller_inv.get("real_frontend_callers", [])) >= 1


def test_13_admin_web_external_tasks_in_frontend(caller_inv):
    fe = caller_inv.get("real_frontend_callers", [])
    assert any(
        ("external-tasks" in str(c) or "admin-web" in str(c)) for c in fe
    )


def test_14_real_backend_callers_exist(caller_inv):
    assert len(caller_inv.get("real_backend_callers", [])) >= 1


def test_15_backend_compat_callers_exist(caller_inv):
    assert len(caller_inv.get("backend_compat_callers", [])) >= 1


def test_16_unknown_callers_exist(caller_inv):
    assert len(caller_inv.get("unknown_callers", [])) >= 1


def test_17_test_callers_exist(caller_inv):
    assert len(caller_inv.get("test_callers", [])) >= 1


def test_18_audit_smoke_callers_exist(caller_inv):
    assert len(caller_inv.get("audit_smoke_callers", [])) >= 1


# ── 19~21. unknown mount status ──────────────────────────────────────────────

_VALID_MOUNT_STATUSES = {
    "RUNTIME_MOUNTED", "POSSIBLY_MOUNTED", "NOT_MOUNTED",
    "TEST_ONLY", "UNKNOWN_NEEDS_FOLLOWUP",
}


def test_19_all_unknown_callers_classified(unknown_mount):
    for fname, info in unknown_mount.items():
        assert info.get("status") in _VALID_MOUNT_STATUSES, \
            f"invalid status for {fname}: {info.get('status')}"


def test_20_unknown_needs_followup_has_reason(unknown_mount):
    for fname, info in unknown_mount.items():
        if info.get("status") == "UNKNOWN_NEEDS_FOLLOWUP":
            assert info.get("basis"), f"UNKNOWN_NEEDS_FOLLOWUP without basis: {fname}"


def test_21_runtime_mounted_keeps_disable_false(audit_mod, unknown_mount):
    for fname, info in unknown_mount.items():
        if info.get("status") in ("RUNTIME_MOUNTED", "POSSIBLY_MOUNTED"):
            assert audit_mod.LEGACY_DISABLE_ALLOWED_NOW is False


# ── 22~27. migration steps / required ────────────────────────────────────────

def test_22_migration_steps_both_rows(plan):
    for row in plan:
        assert len(row.get("migration_steps", [])) >= 1


def test_23_required_before_migration_both_rows(plan):
    for row in plan:
        assert len(row.get("required_before_migration", [])) >= 1


def test_24_required_after_migration_both_rows(plan):
    for row in plan:
        assert len(row.get("required_after_migration", [])) >= 1


def test_25_required_before_disable_both_rows(plan):
    for row in plan:
        assert len(row.get("required_before_disable", [])) >= 1


def test_26_inbox_required_before_disable_has_frontend_smoke(plan):
    inbox = next(r for r in plan if r["path"] == "/api/v1/inbox")
    reqs = " ".join(inbox.get("required_before_disable", []))
    assert "smoke" in reqs.lower() or "frontend" in reqs.lower()


def test_27_tasks_required_before_disable_has_side_effect_confirmation(plan):
    tasks = next(r for r in plan if r["path"] == "/api/v1/tasks")
    reqs = " ".join(tasks.get("required_before_disable", []))
    assert "side effect" in reqs.lower() or "side_effect" in reqs.lower()


def test_28_tasks_required_before_disable_has_approval_token(plan):
    tasks = next(r for r in plan if r["path"] == "/api/v1/tasks")
    reqs = " ".join(tasks.get("required_before_disable", []))
    assert "approval" in reqs.lower() or "token" in reqs.lower()


# ── 29~30. rollback plan ─────────────────────────────────────────────────────

def test_29_rollback_plan_inbox_exists(plan):
    inbox = next(r for r in plan if r["path"] == "/api/v1/inbox")
    assert inbox.get("rollback_plan")


def test_30_rollback_plan_tasks_exists(plan):
    tasks = next(r for r in plan if r["path"] == "/api/v1/tasks")
    assert tasks.get("rollback_plan")


# ── 31~34. 제외 대상 ─────────────────────────────────────────────────────────

def test_31_execute_not_in_plan(plan):
    assert not any("/execute" in r["path"] for r in plan)


def test_32_webhook_not_in_plan(plan):
    assert not any("webhook" in r["path"] for r in plan)


def test_33_dashboard_not_in_plan(plan):
    assert not any("dashboard" in r["path"] for r in plan)


def test_34_adapter_routes_not_in_plan(plan):
    adapter_paths = [
        "/api/v1/inbox/email/fetch",
        "/api/v1/tasks/{task_id}/approve",
        "/api/v1/tasks/{task_id}/reject",
    ]
    plan_paths = [r["path"] for r in plan]
    for ap in adapter_paths:
        assert ap not in plan_paths


# ── 35~41. safety boundary ───────────────────────────────────────────────────

def test_35_no_actual_caller_modification(router_content):
    assert "PHASE_1J3" not in router_content


def test_36_no_route_disable_in_router(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_37_no_5050_route_deleted():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_38_no_frontend_modification():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        content = tsx.read_text(encoding="utf-8", errors="ignore")
        assert "PHASE_1J3" not in content


def test_39_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_40_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_41_no_secret_env_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py"
    ).read_text(encoding="utf-8", errors="ignore")
    for bad in ["os.environ[", "os.getenv(", "print(token", "import requests", "import httpx"]:
        assert bad not in content


# ── 42~43. global constants ──────────────────────────────────────────────────

def test_42_plan_only_true(audit_mod):
    assert audit_mod.PLAN_ONLY is True


def test_43_caller_modification_allowed_now_global_false(audit_mod):
    assert audit_mod.CALLER_MODIFICATION_ALLOWED_NOW is False


# ── 44~47. audit verdict ─────────────────────────────────────────────────────

def test_44_audit_verdict_ready_or_warn(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J3_CALLER_MIGRATION_PLAN_READY",
        "CALLER_MIGRATION_PLAN_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_45_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_46_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


def test_47_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1J3_CALLER_MIGRATION_PLAN_FAIL"


# ── 48~50. 이전 Phase 충돌 없음 ──────────────────────────────────────────────

def test_48_phase1j2_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py").exists()


def test_49_phase1j_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").exists()


def test_50_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_51_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_52_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_53_characterization_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()
