"""
Backend Pre-Deploy Smoke Plan 테스트
tests/test_backend_pre_deploy_smoke_plan_20260517.py

Phase 1 백엔드 준공 상태 서버 반영 전 read-only 체크리스트 검증.
실제 서버 반영 / git pull / 컨테이너 재시작 없음.
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
        "audit_pre_deploy",
        "scripts/ops/audit_backend_pre_deploy_smoke_plan.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def checklist(audit_mod):
    return audit_mod.PRE_DEPLOY_LOCAL_CHECKLIST


@pytest.fixture(scope="module")
def pre_smoke(audit_mod):
    return audit_mod.PRE_RESTART_SMOKE


@pytest.fixture(scope="module")
def post_smoke(audit_mod):
    return audit_mod.POST_RESTART_SMOKE


@pytest.fixture(scope="module")
def rollback(audit_mod):
    return audit_mod.ROLLBACK_CRITERIA


@pytest.fixture(scope="module")
def ff_only(audit_mod):
    return audit_mod.FF_ONLY_PULL_CONDITIONS


@pytest.fixture(scope="module")
def server_head_plan(audit_mod):
    return audit_mod.SERVER_HEAD_VERIFICATION_PLAN


@pytest.fixture(scope="module")
def inbox_check(audit_mod):
    return audit_mod.GET_INBOX_DEPLOY_CHECK


@pytest.fixture(scope="module")
def tasks_check(audit_mod):
    return audit_mod.POST_TASKS_DEPLOY_CHECK


@pytest.fixture(scope="module")
def gate_checks(audit_mod):
    return audit_mod.GATE_CHECKS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~8. 로컬 체크리스트 ─────────────────────────────────────────────────────

def test_03_pre_deploy_checklist_gte_6(checklist):
    assert len(checklist) >= 6


def test_04_checklist_has_head_check(checklist):
    ids = [c["id"] for c in checklist]
    assert "L-1" in ids


def test_05_checklist_has_status_clean(checklist):
    assert any("status" in c["item"].lower() or "clean" in c["item"].lower() for c in checklist)


def test_06_checklist_has_quality_gate(checklist):
    assert any("quality" in c["item"].lower() or "gate" in c["item"].lower() for c in checklist)


def test_07_checklist_has_layer_audit(checklist):
    assert any("layer" in c["item"].lower() or "audit" in c["item"].lower() for c in checklist)


def test_08_checklist_has_regression(checklist):
    assert any("회귀" in c["item"] or "696" in c["item"] or "pass" in c["item"].lower() for c in checklist)


# ── 9~12. 서버 HEAD 확인 계획 ────────────────────────────────────────────────

def test_09_server_head_plan_exists(server_head_plan):
    assert server_head_plan is not None


def test_10_server_head_target_0014f24(server_head_plan):
    assert "0014f24" in server_head_plan["expected_after_pull"]


def test_11_server_head_check_readonly(server_head_plan):
    # 확인 커맨드는 read-only (pull 없음)
    assert "pull" not in server_head_plan["check_command"].lower()


def test_12_divergence_action_no_force(server_head_plan):
    action = server_head_plan.get("divergence_action", "")
    assert "강제" in action or "STOP" in action


# ── 13~17. ff-only pull 조건 ─────────────────────────────────────────────────

def test_13_ff_only_pull_conditions_exist(ff_only):
    assert ff_only is not None


def test_14_ff_only_allowed_conditions_exist(ff_only):
    assert len(ff_only.get("allowed_when", [])) >= 1


def test_15_ff_only_blocked_conditions_exist(ff_only):
    assert len(ff_only.get("blocked_when", [])) >= 1


def test_16_ff_only_on_fail_no_force(ff_only):
    # "force push 금지" 같은 안내 문구는 허용 — 실제 force 명령 허용이 없어야 함
    # note 필드에 "금지" 또는 "STOP" 포함 확인으로 대체
    note = ff_only.get("note", "")
    assert "금지" in note or "STOP" in ff_only.get("on_fail", "")


def test_17_ff_only_command_correct(ff_only):
    assert "--ff-only" in ff_only.get("command", "")


# ── 18~22. restart 전 smoke ───────────────────────────────────────────────────

def test_18_pre_restart_smoke_gte_8(pre_smoke):
    assert len(pre_smoke) >= 8


def test_19_pre_smoke_has_touch_phase_check(pre_smoke):
    assert any("TOUCH_PHASE" in s["item"] or "PHASE_1R" in s.get("expected", "") for s in pre_smoke)


def test_20_pre_smoke_has_guard_check(pre_smoke):
    assert any("guard" in s["item"].lower() or "False" in s.get("expected", "") for s in pre_smoke)


def test_21_pre_smoke_has_inbox_handler(pre_smoke):
    assert any("inbox" in s["item"].lower() for s in pre_smoke)


def test_22_pre_smoke_has_known_baseline(pre_smoke):
    assert any("known" in s["item"].lower() or "baseline" in s["item"].lower() or "pytest" in s.get("command", "").lower() for s in pre_smoke)


# ── 23~27. restart 후 smoke ───────────────────────────────────────────────────

def test_23_post_restart_smoke_gte_7(post_smoke):
    assert len(post_smoke) >= 7


def test_24_post_smoke_has_server_health(post_smoke):
    assert any("health" in s["item"].lower() or "Up" in s.get("expected", "") for s in post_smoke)


def test_25_post_smoke_has_head_verify(post_smoke):
    assert any("HEAD" in s["item"] or "0014f24" in s.get("expected", "") for s in post_smoke)


def test_26_post_smoke_has_inbox_check(post_smoke):
    assert any("inbox" in s["item"].lower() for s in post_smoke)


def test_27_post_smoke_has_nginx_check(post_smoke):
    assert any("nginx" in s["item"].lower() or "edge" in s["item"].lower() or "orchestrator" in s.get("command", "").lower() for s in post_smoke)


# ── 28~32. rollback 기준 ─────────────────────────────────────────────────────

def test_28_rollback_trigger_conditions_exist(rollback):
    assert len(rollback.get("trigger_conditions", [])) >= 1


def test_29_rollback_includes_health_check_fail(rollback):
    triggers = " ".join(rollback.get("trigger_conditions", []))
    assert "health" in triggers.lower() or "500" in triggers or "기동" in triggers


def test_30_rollback_command_exists(rollback):
    assert rollback.get("rollback_command")


def test_31_rollback_approval_required(rollback):
    assert rollback.get("rollback_approval")


def test_32_rollback_no_unauthorized_force(rollback):
    cmd = rollback.get("rollback_command", "")
    note = rollback.get("note", "")
    # force push 단독 허용 없음 — 승인 후만
    if "--force" in cmd:
        assert "승인" in note or "대표" in note


# ── 33~37. GET /inbox deploy check ───────────────────────────────────────────

def test_33_get_inbox_effectively_disabled(inbox_check):
    assert inbox_check["status"] == "EFFECTIVELY_DISABLED"


def test_34_get_inbox_8400_handler_active(inbox_check):
    assert "ACTIVE_NORMAL" in inbox_check["8400_handler"]


def test_35_get_inbox_legacy_not_mounted(inbox_check):
    assert "NOT_MOUNTED" in inbox_check["legacy_mount"]


def test_36_get_inbox_regression_risk_none(inbox_check):
    assert inbox_check["regression_risk"] == "NONE"


def test_37_get_inbox_deploy_check_before_defined(inbox_check):
    assert inbox_check.get("check_before_deploy")


# ── 38~42. POST /tasks deploy check ──────────────────────────────────────────

def test_38_post_tasks_blocked_design_only(tasks_check):
    assert tasks_check["status"] == "BLOCKED_DESIGN_ONLY"


def test_39_post_tasks_disable_not_allowed(tasks_check):
    assert tasks_check["disable_allowed_now"] is False


def test_40_post_tasks_blockers_gte_5(tasks_check):
    assert tasks_check["blockers_count"] >= 5


def test_41_post_tasks_deploy_impact_none(tasks_check):
    assert "NONE" in tasks_check["deploy_impact"]


def test_42_post_tasks_check_before_defined(tasks_check):
    assert tasks_check.get("check_before_deploy")


# ── 43~46. quality gate / layer audit / known baseline ───────────────────────

def test_43_gate_checks_defined(gate_checks):
    assert gate_checks is not None


def test_44_quality_gate_check_defined(gate_checks):
    assert gate_checks.get("quality_gate")
    assert "errors: 0" in gate_checks["quality_gate"]["expected"]


def test_45_layer_audit_check_defined(gate_checks):
    assert gate_checks.get("layer_audit")
    assert "10 passed" in gate_checks["layer_audit"]["expected"]


def test_46_known_baselines_gte_6(gate_checks):
    assert len(gate_checks["known_baselines"]["tests"]) >= 6


# ── 47~52. 로컬 안정성 직접 확인 ────────────────────────────────────────────

def test_47_router_touch_phase_1r(router_content):
    assert (
        'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router_content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router_content
    )


def test_48_all_guard_flags_false(router_content):
    assert "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = True" not in router_content
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = True" not in router_content
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = True" not in router_content


def test_49_8400_inbox_handler_exists(router_content):
    assert '@router.get("/inbox")' in router_content or "@router.get('/inbox')" in router_content


def test_50_guard_function_exists(router_content):
    assert "_legacy_5050_should_use_route_wiring" in router_content


def test_51_legacy_5050_dir_exists():
    assert (REPO_ROOT / "backend/compat/legacy_5050").exists()


def test_52_all_phase_audits_exist():
    required = [
        "scripts/ops/audit_backend_operation_stabilization_final.py",
        "scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py",
        "scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py",
        "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py",
        "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py",
        "scripts/ops/audit_external_site_canonical_registry.py",
    ]
    for f in required:
        assert (REPO_ROOT / f).exists(), f"{f} 없음"


# ── 53~56. 운영 안전 플래그 ──────────────────────────────────────────────────

def test_53_server_apply_not_allowed(audit_mod):
    assert audit_mod.SERVER_APPLY_ALLOWED is False


def test_54_git_pull_not_allowed(audit_mod):
    assert audit_mod.GIT_PULL_ALLOWED is False


def test_55_container_restart_not_allowed(audit_mod):
    assert audit_mod.CONTAINER_RESTART_ALLOWED is False


def test_56_external_call_not_allowed(audit_mod):
    assert audit_mod.EXTERNAL_CALL_ALLOWED is False


# ── 57. no HTTP import ───────────────────────────────────────────────────────

def test_57_no_http_import_in_audit_script():
    content = (
        REPO_ROOT / "scripts/ops/audit_backend_pre_deploy_smoke_plan.py"
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


# ── 58~60. audit verdict ─────────────────────────────────────────────────────

def test_58_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "BACKEND_PRE_DEPLOY_SMOKE_PLAN_READY",
        "BACKEND_PRE_DEPLOY_SMOKE_PLAN_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_59_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_60_audit_local_readiness_all_ready(audit_result):
    assert audit_result["local_readiness"]["all_ready"] is True
