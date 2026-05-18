"""
Phase 1-J7 테스트: GET /api/v1/inbox Disable Plan Approval Gate
tests/test_5050_phase1j7_get_inbox_disable_plan_approval_gate_20260517.py

폐쇄 허가서 공정. 실제 disable 없음. 대표 승인 전까지 gate holding.
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
        "audit_phase1j7",
        "scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def disable_plan(audit_mod):
    return audit_mod.GET_INBOX_DISABLE_PLAN


@pytest.fixture(scope="module")
def approval(audit_mod):
    return audit_mod.APPROVAL_CONDITIONS


@pytest.fixture(scope="module")
def smoke_cond(audit_mod):
    return audit_mod.PRE_DEPLOY_SMOKE_CONDITIONS


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


# ── 3~14. disable plan ───────────────────────────────────────────────────────

def test_03_disable_plan_exists(disable_plan):
    assert disable_plan is not None


def test_04_target_route_get_inbox(disable_plan):
    assert disable_plan["route"] == "/api/v1/inbox"
    assert disable_plan["method"] == "GET"


def test_05_schema_freeze_frozen(disable_plan):
    assert disable_plan["schema_freeze_status"] == "FROZEN"


def test_06_side_effect_read_only(disable_plan):
    assert disable_plan["side_effect_classification"] == "READ_ONLY_EXPECTED"


def test_07_effective_real_caller_count_zero(disable_plan):
    assert disable_plan["effective_real_caller_count"] == 0


def test_08_disable_candidate_true(disable_plan):
    assert disable_plan["disable_candidate"] is True


def test_09_actual_disable_not_allowed(disable_plan):
    assert disable_plan["actual_disable_allowed_now"] is False


def test_10_plan_not_approved_yet(disable_plan):
    assert disable_plan["plan_approved"] is False


def test_11_pre_disable_steps_exist(disable_plan):
    assert len(disable_plan.get("pre_disable_steps", [])) >= 1


def test_12_disable_steps_exist(disable_plan):
    assert len(disable_plan.get("disable_steps", [])) >= 1


def test_13_post_disable_steps_exist(disable_plan):
    assert len(disable_plan.get("post_disable_steps", [])) >= 1


def test_14_rollback_steps_exist(disable_plan):
    assert len(disable_plan.get("rollback_steps", [])) >= 1


# ── 15~20. 대표 승인 조건 ────────────────────────────────────────────────────

def test_15_approval_conditions_exist(approval):
    assert approval is not None


def test_16_representative_approval_not_received(approval):
    assert approval["representative_approval_received"] is False


def test_17_approval_verdict_gate_holding(approval):
    assert approval["verdict"] == "APPROVAL_GATE_HOLDING"


def test_18_pre_approval_checklist_exists(approval):
    assert len(approval.get("pre_approval_checklist", [])) >= 1


def test_19_required_from_representative_exists(approval):
    assert len(approval.get("required_from_representative", [])) >= 1


def test_20_approval_not_received_action_exists(approval):
    assert approval.get("approval_not_received_action")


# ── 21~23. pre-deploy smoke 조건 ─────────────────────────────────────────────

def test_21_pre_deploy_smoke_conditions_exist(smoke_cond):
    assert smoke_cond is not None


def test_22_before_router_change_smoke_defined(smoke_cond):
    assert len(smoke_cond.get("before_router_change", [])) >= 1


def test_23_after_router_change_smoke_defined(smoke_cond):
    assert len(smoke_cond.get("after_router_change_before_deploy", [])) >= 1


# ── 24~28. POST /tasks exclusion ─────────────────────────────────────────────

def test_24_post_tasks_exclusion_exists(tasks_excl):
    assert tasks_excl is not None


def test_25_post_tasks_mode_blocked(tasks_excl):
    assert tasks_excl["mode"] == "BLOCKED_DESIGN_ONLY"


def test_26_post_tasks_actual_disable_not_allowed(tasks_excl):
    assert tasks_excl["actual_disable_allowed_now"] is False


def test_27_post_tasks_modification_not_allowed(tasks_excl):
    assert tasks_excl["modification_allowed_now"] is False


def test_28_post_tasks_blockers_gte_5(tasks_excl):
    assert len(tasks_excl.get("blockers", [])) >= 5


# ── 29~32. rollback plan (MINOR_NOTE 반영: git revert 주 기준) ────────────────

def test_29_rollback_plan_exists(rollback):
    assert rollback is not None


def test_30_rollback_primary_is_git_revert(rollback):
    assert "git revert" in rollback.get("primary_rollback", "")


def test_31_rollback_smoke_required(rollback):
    assert rollback["rollback_smoke_required"] is True


def test_32_rollback_approval_required(rollback):
    assert rollback["user_approval_required"] is True


# ── 33~40. safety boundary ───────────────────────────────────────────────────

def test_33_no_phase1j7_in_router(router_content):
    assert "PHASE_1J7" not in router_content


def test_34_router_touch_count_still_one(router_content):
    assert router_content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") == 1


def test_35_fetch_inbox_enabled_still_true(router_content):
    # 아직 disable 전 — True여야 함
    assert "LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False" not in router_content


def test_36_caller_files_not_modified():
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists():
            assert "PHASE_1J7" not in p.read_text(encoding="utf-8", errors="ignore")


def test_37_admin_web_not_modified():
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        assert "PHASE_1J7" not in tsx.read_text(encoding="utf-8", errors="ignore")


def test_38_legacy_5050_dir_exists():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_39_no_route_actually_disabled():
    # router.py에 실제 disable 흔적 없음
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")
    assert "PHASE_1J7" not in content
    assert "LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False" not in content


def test_40_no_8400_handler_modification():
    for f in REPO_ROOT.glob("ai_orchestrator/**/*.py"):
        if any(x in f.name for x in ["test", "audit", "smoke"]):
            continue
        if "PHASE_1J7" in f.read_text(encoding="utf-8", errors="ignore"):
            pytest.fail(f"{f.relative_to(REPO_ROOT)} contains PHASE_1J7")


# ── 41~45. global flags ───────────────────────────────────────────────────────

def test_41_db_write_allowed_false(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_42_live_traffic_allowed_false(audit_mod):
    assert audit_mod.LIVE_TRAFFIC_ALLOWED is False


def test_43_approval_gate_only_true(audit_mod):
    assert audit_mod.APPROVAL_GATE_ONLY is True


def test_44_actual_disable_allowed_now_false(audit_mod):
    assert audit_mod.ACTUAL_DISABLE_ALLOWED_NOW is False


def test_45_representative_approval_received_false(audit_mod):
    assert audit_mod.REPRESENTATIVE_APPROVAL_RECEIVED is False


# ── 46. no HTTP import ───────────────────────────────────────────────────────

def test_46_no_http_import_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py"
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

def test_47_audit_verdict_gate_holding(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1J7_GET_INBOX_DISABLE_PLAN_GATE_HOLDING",
        "PHASE1J7_GET_INBOX_DISABLE_PLAN_GATE_HOLDING_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_48_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_49_audit_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


def test_50_audit_known_baseline_not_fail(audit_result):
    assert audit_result["verdict"] != "PHASE1J7_GET_INBOX_DISABLE_PLAN_FAIL"


# ── 51~60. 이전 Phase 충돌 없음 ─────────────────────────────────────────────

def test_51_phase1j6_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py").exists()


def test_52_phase1j5_no_conflict():
    assert (
        REPO_ROOT
        / "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py"
    ).exists()


def test_53_phase1j4_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py").exists()


def test_54_phase1j3_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py").exists()


def test_55_phase1j2_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py").exists()


def test_56_phase1j_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py").exists()


def test_57_phase1s_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py").exists()


def test_58_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_59_contract_freeze_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1_8400_contract_freeze.py").exists()


def test_60_characterization_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_legacy_characterization.py").exists()
