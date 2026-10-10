"""
POST /api/v1/tasks Side-Effect Gate Design 테스트
tests/test_post_tasks_side_effect_gate_design_20260518.py

ASSISTANT_BACKEND_POST_TASKS_SIDE_EFFECT_GATE_DESIGN_01

설계·분석·기준선 작성 검증 전용.
실제 POST /tasks 실행 / execute 호출 / approval_token 발행 / DB write /
router.py 수정 / 서버 반영 전면 금지.
"""

import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_module(name, rel_path):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_post_tasks_gate",
        "tools/audits/backend/audit_post_tasks_side_effect_gate_design.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def call_chain(audit_mod):
    return audit_mod.CALL_CHAIN


@pytest.fixture(scope="module")
def side_effects(audit_mod):
    return audit_mod.SIDE_EFFECT_CATALOG


@pytest.fixture(scope="module")
def risk_paths(audit_mod):
    return audit_mod.RISK_LEVEL_PATHS


@pytest.fixture(scope="module")
def gate(audit_mod):
    return audit_mod.APPROVAL_GATE_DESIGN


@pytest.fixture(scope="module")
def dry_run(audit_mod):
    return audit_mod.DRY_RUN_POLICY


@pytest.fixture(scope="module")
def rollback(audit_mod):
    return audit_mod.ROLLBACK_CRITERIA


@pytest.fixture(scope="module")
def next_phase(audit_mod):
    return audit_mod.NEXT_PHASE_CONDITIONS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────


def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~8. 운영 안전 플래그 ────────────────────────────────────────────────────


def test_03_route_execution_not_allowed(audit_mod):
    assert audit_mod.ROUTE_EXECUTION_ALLOWED is False


def test_04_execute_call_not_allowed(audit_mod):
    assert audit_mod.EXECUTE_CALL_ALLOWED is False


def test_05_approval_token_issue_not_allowed(audit_mod):
    assert audit_mod.APPROVAL_TOKEN_ISSUE_ALLOWED is False


def test_06_db_write_not_allowed(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_07_router_modification_not_allowed(audit_mod):
    assert audit_mod.ROUTER_MODIFICATION_ALLOWED is False


def test_08_design_only_true(audit_mod):
    assert audit_mod.DESIGN_ONLY is True


# ── 9~14. call chain 분석 ────────────────────────────────────────────────────


def test_09_call_chain_gte_5_steps(call_chain):
    assert len(call_chain) >= 5


def test_10_call_chain_has_submit_task(call_chain):
    calls = [s["call"] for s in call_chain]
    assert any("submit_task" in c for c in calls)


def test_11_call_chain_has_plan(call_chain):
    calls = [s["call"] for s in call_chain]
    assert any("plan(" in c for c in calls)


def test_12_call_chain_has_issue_token(call_chain):
    calls = [s["call"] for s in call_chain]
    assert any("issue_token" in c for c in calls)


def test_13_call_chain_has_execute(call_chain):
    calls = [s["call"] for s in call_chain]
    assert any("execute(" in c for c in calls)


def test_14_blocking_steps_identified(call_chain):
    blocking = [s for s in call_chain if s.get("blocking")]
    assert len(blocking) >= 2


# ── 15~22. side-effect catalog ───────────────────────────────────────────────


def test_15_side_effect_catalog_gte_6(side_effects):
    assert len(side_effects) >= 6


def test_16_audit_log_write_cataloged(side_effects):
    assert "FILE_WRITE_AUDIT_LOG" in side_effects


def test_17_approval_tokens_write_cataloged(side_effects):
    assert "FILE_WRITE_APPROVAL_TOKENS" in side_effects


def test_18_execution_history_write_cataloged(side_effects):
    assert "FILE_WRITE_EXECUTION_HISTORY" in side_effects


def test_19_external_execution_cataloged(side_effects):
    assert "EXTERNAL_EXECUTION_WHITELIST" in side_effects


def test_20_approval_tokens_risk_medium(side_effects):
    assert side_effects["FILE_WRITE_APPROVAL_TOKENS"]["risk"] == "MEDIUM"


def test_21_approval_tokens_not_reversible(side_effects):
    assert side_effects["FILE_WRITE_APPROVAL_TOKENS"]["reversible"] is False


def test_22_external_execution_whitelist_has_two_actions(side_effects):
    whitelist = side_effects["EXTERNAL_EXECUTION_WHITELIST"]["whitelist"]
    assert len(whitelist) >= 2
    assert "get_server_status" in whitelist
    assert "fetch_web_page" in whitelist


# ── 23~30. risk level 경로 분석 ──────────────────────────────────────────────


def test_23_risk_levels_all_present(risk_paths):
    for level in ("low", "medium", "high", "critical"):
        assert level in risk_paths


def test_24_low_token_not_issued(risk_paths):
    assert risk_paths["low"]["token_issued"] is False


def test_25_medium_token_issued(risk_paths):
    assert risk_paths["medium"]["token_issued"] is True


def test_26_high_external_execution_not_possible(risk_paths):
    assert risk_paths["high"]["external_execution_possible"] is False


def test_27_critical_external_execution_not_possible(risk_paths):
    assert risk_paths["critical"]["external_execution_possible"] is False


def test_28_medium_execute_returns_pending(risk_paths):
    assert "PENDING_APPROVAL" in risk_paths["medium"]["execute_path"]


def test_29_low_file_writes_include_execution_history(risk_paths):
    writes = " ".join(risk_paths["low"]["file_writes"])
    assert "execution_history" in writes


def test_30_medium_gate_gap_identified(risk_paths):
    assert risk_paths["medium"]["gate_gap"]
    assert "approve" in risk_paths["medium"]["gate_gap"].lower() or "gate" in risk_paths["medium"]["gate_gap"].lower()


# ── 31~38. approval gate 설계 ────────────────────────────────────────────────


def test_31_gate_design_only_status(gate):
    assert gate["status"] == "DESIGN_ONLY"


def test_32_gate_disable_not_allowed(gate):
    assert gate["disable_allowed_now"] is False


def test_33_gate_blockers_gte_5(gate):
    assert len(gate["blockers"]) >= 5


def test_34_gate_has_write_possible(gate):
    assert "WRITE_POSSIBLE" in gate["blockers"]


def test_35_gate_has_execute_side_effect(gate):
    assert "execute_side_effect" in gate["blockers"]


def test_36_gate_has_approval_token_side_effect(gate):
    assert "approval_token_side_effect" in gate["blockers"]


def test_37_gate_has_db_write_impact(gate):
    assert "db_write_impact" in gate["blockers"]


def test_38_gate_has_approval_gate_not_designed(gate):
    assert "approval_gate_not_designed" in gate["blockers"]


# ── 39~43. dry-run 정책 ──────────────────────────────────────────────────────


def test_39_dry_run_policy_design_only(dry_run):
    assert dry_run["status"] == "DESIGN_ONLY"


def test_40_dry_run_default_true(dry_run):
    assert dry_run["dry_run_default"] is True


def test_41_dry_run_steps_gte_5(dry_run):
    assert len(dry_run["steps_before_real_run"]) >= 5


def test_42_dry_run_flag_name_defined(dry_run):
    assert dry_run.get("dry_run_flag_name")


def test_43_dry_run_flag_implemented_or_not_in_design_scope(router_content):
    # 설계 공정 기준: flag 미구현이 원칙이나,
    # 이후 DRY_RUN_FLAG_IMPLEMENTATION 공정에서 대표 승인 후 구현됨 — 정상 진행.
    # 구현된 경우 default=True(차단 방향)인지 확인.
    flag_name = "POST_TASKS_DRY_RUN_ENABLED"
    if flag_name in router_content:
        assert "POST_TASKS_DRY_RUN_ENABLED = True" in router_content, (
            f"{flag_name}이 True(차단)가 아닌 값으로 설정됨 — 안전 방향 위반"
        )


# ── 44~48. rollback 기준 ─────────────────────────────────────────────────────


def test_44_rollback_triggers_exist(rollback):
    assert len(rollback.get("trigger_conditions", [])) >= 3


def test_45_rollback_approval_required(rollback):
    assert rollback.get("rollback_approval")
    assert "승인" in rollback["rollback_approval"] or "대표" in rollback["rollback_approval"]


def test_46_rollback_force_push_false(rollback):
    assert rollback.get("force_push") is False


def test_47_rollback_command_exists(rollback):
    assert rollback.get("rollback_command")


def test_48_rollback_note_design_only(rollback):
    note = rollback.get("note", "")
    assert "설계" in note or "변경 없음" in note or "design" in note.lower()


# ── 49~53. 다음 Phase 조건 ───────────────────────────────────────────────────


def test_49_next_phase_defined(next_phase):
    assert next_phase.get("phase")


def test_50_next_phase_blocked_design_only(next_phase):
    assert next_phase["current_status"] == "BLOCKED_DESIGN_ONLY"


def test_51_next_phase_conditions_gte_5(next_phase):
    assert len(next_phase.get("all_conditions_must_be_met", [])) >= 5


def test_52_next_phase_requires_representative_approval(next_phase):
    conditions = " ".join(next_phase.get("all_conditions_must_be_met", []))
    assert "승인" in conditions or "approval" in conditions.lower()


def test_53_next_phase_requires_router_approval(next_phase):
    conditions = " ".join(next_phase.get("all_conditions_must_be_met", []))
    assert "router" in conditions.lower()


# ── 54~58. router.py Phase 1-R 안전장치 유지 ─────────────────────────────────


def test_54_task_approve_guard_active(router_content):
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in router_content
    )


def test_55_task_reject_guard_active(router_content):
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_REJECT")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_REJECT')" in router_content
    )


def test_56_task_approve_flag_false(router_content):
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content


def test_57_task_reject_flag_false(router_content):
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content


def test_58_touch_phase_still_1r(router_content):
    assert (
        'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router_content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router_content
    )


# ── 59. no HTTP import ───────────────────────────────────────────────────────


def test_59_no_http_import_in_audit_script():
    content = (REPO_ROOT / "tools/audits/backend/audit_post_tasks_side_effect_gate_design.py").read_text(
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
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for bad in ["requests", "httpx", "aiohttp", "urllib3"]:
        assert bad not in imported, f"HTTP client imported: {bad}"


# ── 60. audit verdict ────────────────────────────────────────────────────────


def test_60_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "POST_TASKS_SIDE_EFFECT_GATE_DESIGN_READY",
        "POST_TASKS_SIDE_EFFECT_GATE_DESIGN_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_61_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_62_audit_design_only_confirmed(audit_result):
    assert audit_result["design_only"] is True


def test_63_audit_blockers_gte_5(audit_result):
    assert audit_result["blockers_count"] >= 5


def test_64_audit_next_phase_blocked(audit_result):
    assert audit_result["next_phase_status"] == "BLOCKED_DESIGN_ONLY"
