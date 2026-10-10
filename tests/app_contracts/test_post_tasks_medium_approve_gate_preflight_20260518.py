"""
POST /api/v1/tasks Medium Approve Gate Preflight 테스트
tests/test_post_tasks_medium_approve_gate_preflight_20260518.py

ASSISTANT_BACKEND_POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_01

approve → execute_task 연결 경로 preflight 설계 검증.
실제 token 발행 / approve 호출 / execute_task 호출 / DB write /
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
        "audit_medium_gate_preflight",
        "tools/audits/backend/audit_post_tasks_medium_approve_gate_preflight.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def connection_analysis(audit_mod):
    return audit_mod.APPROVE_EXECUTE_CONNECTION_ANALYSIS


@pytest.fixture(scope="module")
def medium_path(audit_mod):
    return audit_mod.MEDIUM_PATH_CURRENT_STATE


@pytest.fixture(scope="module")
def guard_status(audit_mod):
    return audit_mod.PHASE_1R_GUARD_STATUS


@pytest.fixture(scope="module")
def whitelist_analysis(audit_mod):
    return audit_mod.EXECUTE_TASK_WHITELIST_ANALYSIS


@pytest.fixture(scope="module")
def dry_run_scope(audit_mod):
    return audit_mod.DRY_RUN_FLAG_SCOPE


@pytest.fixture(scope="module")
def smoke_design(audit_mod):
    return audit_mod.MEDIUM_ISOLATION_SMOKE_DESIGN


@pytest.fixture(scope="module")
def token_isolation(audit_mod):
    return audit_mod.TOKEN_ISOLATION_DESIGN


@pytest.fixture(scope="module")
def router_assessment(audit_mod):
    return audit_mod.ROUTER_MODIFICATION_ASSESSMENT


@pytest.fixture(scope="module")
def approval_conditions(audit_mod):
    return audit_mod.REPRESENTATIVE_APPROVAL_CONDITIONS


@pytest.fixture(scope="module")
def gate_status(audit_mod):
    return audit_mod.PREFLIGHT_GATE_STATUS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def executor_content():
    return (REPO_ROOT / "ai_orchestrator/tasks/executor.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────


def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~8. 운영 안전 플래그 ────────────────────────────────────────────────────


def test_03_approval_token_issue_not_allowed(audit_mod):
    assert audit_mod.APPROVAL_TOKEN_ISSUE_ALLOWED is False


def test_04_approve_call_not_allowed(audit_mod):
    assert audit_mod.APPROVE_CALL_ALLOWED is False


def test_05_execute_task_call_not_allowed(audit_mod):
    assert audit_mod.EXECUTE_TASK_CALL_ALLOWED is False


def test_06_db_write_not_allowed(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_07_router_modification_not_allowed(audit_mod):
    assert audit_mod.ROUTER_MODIFICATION_ALLOWED is False


def test_08_preflight_only_true(audit_mod):
    assert audit_mod.PREFLIGHT_ONLY is True


# ── 9~14. 핵심 발견: approve → execute_task 미연결 ───────────────────────────


def test_09_connection_finding_id_correct(connection_analysis):
    assert connection_analysis["finding_id"] == "APPROVE_EXECUTE_NOT_CONNECTED"


def test_10_current_safety_safe_by_incompleteness(connection_analysis):
    assert connection_analysis["current_safety"] == "SAFE_BY_INCOMPLETENESS"


def test_11_router_import_check_no_execute_task(connection_analysis):
    assert (
        "execute_task" not in connection_analysis["router_import_check"]
        or "execute만 import" in connection_analysis["router_import_check"]
    )


def test_12_execute_task_not_imported_in_router(router_content):
    # execute_task를 import하는 구문이 없어야 함
    assert "import execute_task" not in router_content
    # 단순 문자열로 나타나더라도 import 구문이 아닌지 확인
    for line in router_content.splitlines():
        stripped = line.strip()
        if "execute_task" in stripped and stripped.startswith(("import", "from")):
            assert False, f"execute_task import 발견: {line}"


def test_13_approve_task_does_not_call_execute_task(router_content):
    # approve_task 함수 내에 execute_task 호출 없음
    lines = router_content.splitlines()
    in_approve = False
    for line in lines:
        if '@router.post("/tasks/{task_id}/approve")' in line or "@router.post('/tasks/{task_id}/approve')" in line:
            in_approve = True
        if in_approve and "@router.post(" in line and "approve" not in line:
            in_approve = False
        if in_approve:
            assert "execute_task(" not in line, f"approve_task에서 execute_task 호출 발견: {line}"


def test_14_risk_if_connected_documented(connection_analysis):
    assert connection_analysis.get("risk_if_connected")


# ── 15~20. medium 경로 현재 상태 ─────────────────────────────────────────────


def test_15_step1_execute_task_not_called(medium_path):
    assert medium_path["step_1"]["execute_task_called"] is False


def test_16_step1_result_pending_approval(medium_path):
    assert "PENDING_APPROVAL" in medium_path["step_1"]["execute_result"]


def test_17_step1_issue_token_called(medium_path):
    assert medium_path["step_1"]["issue_token"] and "O" in medium_path["step_1"]["issue_token"]


def test_18_step2_execute_task_not_called(medium_path):
    assert medium_path["step_2"]["execute_task_called"] is False


def test_19_step2_result_token_status_only(medium_path):
    result = medium_path["step_2"]["result"]
    assert "approved" in result.lower() and "execute" not in result.lower()


def test_20_gap_documented(medium_path):
    assert medium_path.get("gap")
    assert "PENDING_APPROVAL" in medium_path["gap"] or "미실행" in medium_path["gap"]


# ── 21~25. Phase 1-R guard 현황 ──────────────────────────────────────────────


def test_21_task_approve_guard_safe(guard_status):
    assert guard_status["TASK_APPROVE_guard"]["safe"] is True


def test_22_task_approve_flag_false(guard_status):
    assert guard_status["TASK_APPROVE_guard"]["current_value"] is False


def test_23_guard_semantic_note_correct(guard_status):
    note = guard_status["TASK_APPROVE_guard"]["semantic_note"]
    assert "5050" in note or "wiring" in note.lower()
    assert "approve_token" in note


def test_24_guard_active_in_router(router_content):
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in router_content
    )


def test_25_guard_conclusion_additional_gate_needed(guard_status):
    conclusion = guard_status["conclusion"]
    assert "gate" in conclusion.lower() or "승인" in conclusion


# ── 26~30. execute_task whitelist 분석 ───────────────────────────────────────


def test_26_whitelist_has_two_actions(whitelist_analysis):
    assert len(whitelist_analysis["current_whitelist"]) >= 2


def test_27_whitelist_medium_gap_identified(whitelist_analysis):
    assert whitelist_analysis.get("whitelist_gap")
    assert (
        "medium" in whitelist_analysis["whitelist_gap"].lower()
        or "write" in whitelist_analysis["whitelist_gap"].lower()
    )


def test_28_whitelist_separate_recommended(whitelist_analysis):
    assert whitelist_analysis.get("recommended_action")
    assert "medium" in whitelist_analysis["recommended_action"].lower()


def test_29_whitelist_design_pending(whitelist_analysis):
    assert whitelist_analysis["design_status"] == "PENDING"


def test_30_executor_whitelist_medium_action_not_included(executor_content):
    # executor.py ALLOWED_ACTIONS에 medium 계열 action이 없어야 함
    # write/edit/create_patch/generate는 whitelist에 없음
    whitelist_section = ""
    in_whitelist = False
    for line in executor_content.splitlines():
        if "ALLOWED_ACTIONS" in line and "=" in line:
            in_whitelist = True
        if in_whitelist:
            whitelist_section += line
            if "]" in line:
                break
    for medium_action in ["write", "edit", "create_patch", "generate"]:
        assert f'"{medium_action}"' not in whitelist_section and f"'{medium_action}'" not in whitelist_section, (
            f"medium action '{medium_action}'이 whitelist에 포함됨"
        )


# ── 31~36. dry-run flag 범위 ─────────────────────────────────────────────────


def test_31_dry_run_flag_name_defined(dry_run_scope):
    assert dry_run_scope["flag_name"] == "POST_TASKS_DRY_RUN_ENABLED"


def test_32_dry_run_default_true(dry_run_scope):
    assert dry_run_scope["default_value"] is True


def test_33_dry_run_applies_to_both_routes(dry_run_scope):
    scope = dry_run_scope["scope"]
    assert "submit_task" in scope and "approve_task" in scope


def test_34_dry_run_flag_implemented_as_true_if_present(router_content):
    # preflight 기준: 미구현이 원칙. DRY_RUN_FLAG_IMPLEMENTATION 공정에서 대표 승인 후 구현.
    # 구현된 경우 반드시 default=True(차단 방향)여야 함.
    if "POST_TASKS_DRY_RUN_ENABLED" in router_content:
        assert "POST_TASKS_DRY_RUN_ENABLED = True" in router_content, (
            "POST_TASKS_DRY_RUN_ENABLED가 True(차단)가 아닌 값으로 설정됨 — 안전 방향 위반"
        )


def test_35_dry_run_implementation_next_phase(dry_run_scope):
    assert "NEXT_PHASE" in dry_run_scope["implementation_phase"]


def test_36_dry_run_router_modification_required(dry_run_scope):
    assert dry_run_scope["router_modification_required"] is True
    assert dry_run_scope["modification_approval_required"] is True


# ── 37~42. medium isolation smoke 설계 ───────────────────────────────────────


def test_37_smoke_design_only_status(smoke_design):
    assert smoke_design["status"] == "DESIGN_ONLY"


def test_38_smoke_test_cases_gte_6(smoke_design):
    assert len(smoke_design["test_cases"]) >= 6


def test_39_smoke_ms1_pending_approval(smoke_design):
    ms1 = next((t for t in smoke_design["test_cases"] if t["id"] == "MS-1"), None)
    assert ms1 is not None
    assert "PENDING_APPROVAL" in ms1["desc"]
    assert ms1["real_token_issued"] is False


def test_40_smoke_ms2_dry_run_no_token(smoke_design):
    ms2 = next((t for t in smoke_design["test_cases"] if t["id"] == "MS-2"), None)
    assert ms2 is not None
    assert ms2["real_token_issued"] is False


def test_41_smoke_ms3_no_execute_task(smoke_design):
    ms3 = next((t for t in smoke_design["test_cases"] if t["id"] == "MS-3"), None)
    assert ms3 is not None
    assert ms3["execute_task_called"] is False


def test_42_smoke_implementation_next_phase(smoke_design):
    assert "NEXT_PHASE" in smoke_design["implementation_phase"]


# ── 43~47. token 격리 조건 ───────────────────────────────────────────────────


def test_43_token_isolation_design_only(token_isolation):
    assert token_isolation["status"] == "DESIGN_ONLY"


def test_44_isolation_has_three_conditions(token_isolation):
    assert len(token_isolation["conditions"]) >= 3


def test_45_dry_run_on_no_token(token_isolation):
    dry_run_cond = next((c for c in token_isolation["conditions"] if "dry-run flag ON" in c["condition"]), None)
    assert dry_run_cond is not None
    assert dry_run_cond["token_issued"] is False


def test_46_current_isolation_level_2(token_isolation):
    assert "LEVEL_2" in token_isolation["current_isolation_level"]


def test_47_target_isolation_level_3(token_isolation):
    assert "LEVEL_3" in token_isolation["target_isolation_level_before_connect"]


# ── 48~52. router.py 수정 판단 ───────────────────────────────────────────────


def test_48_no_modification_this_phase(router_assessment):
    assert router_assessment["current_phase_modification"] is False


def test_49_dry_run_modifications_planned(router_assessment):
    assert len(router_assessment["modifications_needed_for_dry_run"]) >= 2


def test_50_execute_connect_blocked_design_only(router_assessment):
    connect_mods = router_assessment["modifications_needed_for_execute_connect"]
    assert len(connect_mods) >= 1
    assert connect_mods[0]["current_status"] == "BLOCKED_DESIGN_ONLY"


def test_51_execute_connect_requires_approval(router_assessment):
    for mod in router_assessment["modifications_needed_for_execute_connect"]:
        assert mod["requires_approval"] is True


def test_52_router_modification_safety_check(router_content):
    # preflight 기준: 이번 공정에서 router.py 수정 없음.
    # DRY_RUN_FLAG_IMPLEMENTATION에서 대표 승인 후 플래그만 추가됨 — 허용된 변경.
    # 핵심 안전 검증: execute_task import 없음 (승인되지 않은 연결 경로 차단).
    if "from .executor import" in router_content:
        import_line = router_content.split("from .executor import")[1].split("\n")[0]
        assert "execute_task" not in import_line, "execute_task가 router.py에 import됨 — 미승인 연결 경로 열림"
    # 플래그가 있으면 반드시 True(차단 방향)여야 함
    if "POST_TASKS_DRY_RUN_ENABLED" in router_content:
        assert "POST_TASKS_DRY_RUN_ENABLED = True" in router_content


# ── 53~57. 대표 승인 조건 ────────────────────────────────────────────────────


def test_53_approval_received_false(approval_conditions):
    assert approval_conditions["approval_received"] is False


def test_54_approval_status_blocked(approval_conditions):
    assert approval_conditions["current_approval_status"] == "BLOCKED_DESIGN_ONLY"


def test_55_dry_run_approval_conditions_gte_4(approval_conditions):
    assert len(approval_conditions["for_dry_run_flag_implementation"]) >= 4


def test_56_execute_connect_approval_conditions_gte_5(approval_conditions):
    assert len(approval_conditions["for_execute_task_connection"]) >= 5


def test_57_representative_approval_in_conditions(approval_conditions):
    all_conditions = (
        approval_conditions["for_dry_run_flag_implementation"] + approval_conditions["for_execute_task_connection"]
    )
    combined = " ".join(all_conditions)
    assert "대표" in combined or "승인" in combined


# ── 58~60. preflight gate ────────────────────────────────────────────────────


def test_58_all_preflight_conditions_met(gate_status):
    assert gate_status["all_conditions_met"] is True


def test_59_all_seven_conditions_complete(gate_status):
    for i in range(1, 8):
        key = (
            f"condition_{i}_"
            + [
                "approve_execute_connection_analyzed",
                "execute_task_whitelist_reviewed",
                "dry_run_flag_scope_confirmed",
                "medium_isolation_smoke_designed",
                "token_isolation_conditions_designed",
                "router_modification_scope_confirmed",
                "representative_approval_conditions_fixed",
            ][i - 1]
        )
        assert gate_status.get(key, {}).get("status") == "COMPLETE", f"{key} not COMPLETE"


def test_60_next_phase_dry_run_implementation(gate_status):
    assert "DRY_RUN" in gate_status["next_phase"] or "IMPLEMENTATION" in gate_status["next_phase"]


# ── 61. no HTTP import ───────────────────────────────────────────────────────


def test_61_no_http_import_in_audit_script():
    content = (REPO_ROOT / "tools/audits/backend/audit_post_tasks_medium_approve_gate_preflight.py").read_text(
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


# ── 62~65. audit verdict ─────────────────────────────────────────────────────


def test_62_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_READY",
        "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_63_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_64_audit_key_finding_correct(audit_result):
    assert audit_result["key_finding"] == "APPROVE_EXECUTE_NOT_CONNECTED"


def test_65_audit_preflight_only(audit_result):
    assert audit_result["preflight_only"] is True
    assert audit_result["router_modified_this_phase"] is False
