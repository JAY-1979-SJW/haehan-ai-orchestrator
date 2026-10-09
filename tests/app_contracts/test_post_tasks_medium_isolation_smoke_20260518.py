"""
POST /api/v1/tasks Medium Isolation Smoke 테스트
tests/test_post_tasks_medium_isolation_smoke_20260518.py

ASSISTANT_BACKEND_POST_TASKS_MEDIUM_ISOLATION_SMOKE_01

mock 기반 unit smoke 전용.
실제 외부 실행 / 운영 token 발행 / execute_task 연결 /
DB write / 서버 반영 / 컨테이너 재시작 전면 금지.
"""

import ast
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter

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
        "audit_isolation_smoke",
        "tools/audits/backend/audit_post_tasks_medium_isolation_smoke.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def smoke_results(audit_mod):
    return audit_mod.SMOKE_RESULTS


@pytest.fixture(scope="module")
def write_paths(audit_mod):
    return audit_mod.WRITE_PATH_VERIFICATION


@pytest.fixture(scope="module")
def verdict_criteria(audit_mod):
    return audit_mod.SMOKE_VERDICT_CRITERIA


@pytest.fixture(scope="module")
def next_phase(audit_mod):
    return audit_mod.NEXT_PHASE_CONDITIONS


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def executor_content():
    return (REPO_ROOT / "ai_orchestrator/tasks/executor.py").read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def approval_content():
    return (REPO_ROOT / "tools/gates/approval.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~2. import ──────────────────────────────────────────────────────────────


def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_function_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~8. 운영 안전 플래그 ────────────────────────────────────────────────────


def test_03_real_execute_not_allowed(audit_mod):
    assert audit_mod.REAL_EXECUTE_ALLOWED is False


def test_04_real_token_issue_not_allowed(audit_mod):
    assert audit_mod.REAL_TOKEN_ISSUE_ALLOWED is False


def test_05_execute_task_connect_not_allowed(audit_mod):
    assert audit_mod.EXECUTE_TASK_CONNECT_ALLOWED is False


def test_06_db_write_not_allowed(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_07_server_deploy_not_allowed(audit_mod):
    assert audit_mod.SERVER_DEPLOY_ALLOWED is False


def test_08_smoke_mock_only_true(audit_mod):
    assert audit_mod.SMOKE_MOCK_ONLY is True


# ── 9~11. smoke 승인 기록 ────────────────────────────────────────────────────


def test_09_smoke_approved(audit_mod):
    assert audit_mod.SMOKE_APPROVAL["approved"] is True


def test_10_smoke_approval_verbatim(audit_mod):
    assert "isolation smoke 진행 승인" in audit_mod.SMOKE_APPROVAL["approved_verbatim"]


def test_11_smoke_scope_medium_only(audit_mod):
    assert "medium" in audit_mod.SMOKE_APPROVAL["scope"]


# ── 12~20. smoke 결과 — 정적 검증 (router.py / executor.py) ──────────────────


def test_12_dry_run_flag_active(router_content):
    assert "POST_TASKS_DRY_RUN_ENABLED = True" in router_content


def test_13_dry_run_branch_before_issue_token(router_content):
    dry_run_pos = router_content.find("POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval")
    issue_token_pos = router_content.find("issue_token(req, risk")
    assert dry_run_pos != -1 and issue_token_pos != -1
    assert dry_run_pos < issue_token_pos


def test_14_dry_run_gate_blocked_event_present(router_content):
    assert "DRY_RUN_GATE_BLOCKED" in router_content


def test_15_execute_task_not_imported(router_content):
    for line in router_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import", "from")) and "execute_task" in stripped:
            assert False, f"execute_task import 발견: {line}"


def test_16_approve_task_no_execute_task_call(router_content):
    lines = router_content.splitlines()
    in_approve = False
    for line in lines:
        if '"/tasks/{task_id}/approve"' in line or "'/tasks/{task_id}/approve'" in line:
            in_approve = True
        if in_approve and "@router.post(" in line and "approve" not in line:
            break
        if in_approve:
            assert "execute_task(" not in line, f"approve_task에서 execute_task 호출: {line}"


def test_17_whitelist_medium_actions_excluded(executor_content):
    allowed_section = ""
    in_list = False
    for line in executor_content.splitlines():
        if "ALLOWED_ACTIONS" in line and "=" in line:
            in_list = True
        if in_list:
            allowed_section += line
            if "]" in line:
                break
    for action in ["write_file", "edit_config", "create_patch", "generate"]:
        assert f'"{action}"' not in allowed_section and f"'{action}'" not in allowed_section, (
            f"medium action '{action}'이 whitelist에 포함됨"
        )


def test_18_high_critical_blocked_in_execute_task(executor_content):
    assert 'if risk_level in ("high", "critical")' in executor_content


def test_19_approval_expiry_check_exists(approval_content):
    assert "_now() > expires" in approval_content or "expires_at" in approval_content


def test_20_approval_tokens_write_mitigated(write_paths):
    assert write_paths["approval_tokens_jsonl"]["dry_run_prevents"] is True
    assert write_paths["approval_tokens_jsonl"]["risk"] == "MITIGATED"


# ── 21~30. mock 기반 smoke — MS-1~MS-8 ──────────────────────────────────────


@pytest.fixture(scope="module")
def router_mod():
    import sys

    mock_names = [
        "ai_orchestrator.llm.planner",
        "ai_orchestrator.tasks.executor",
        "tools.gates.approval",
        "ai_orchestrator.audit.audit_logger",
        "tools.gates.auth",
        "ai_orchestrator.notify.telegram_webhook",
        "ai_orchestrator.tasks.inbox",
        "ai_orchestrator.connectors.google.gmail_reader",
        "ai_orchestrator.sites.router",
        "ai_orchestrator.cad.router",
        "ai_orchestrator.web_task.web_task_router",
        "ai_orchestrator.agent_hub.router.root",
        "ai_orchestrator.routers.admin_ui_router",
        "ai_orchestrator.auth.auth_router",
        "ai_orchestrator.browser_tool.approval.approval_record_router",
        "ai_orchestrator.routers.action_router",
        "ai_orchestrator.cad_ai_router",
        "ai_orchestrator.connectors.naver_search.naver_search_router",
        "ai_orchestrator.routers.ops_router",
    ]
    originals = {n: sys.modules.get(n) for n in mock_names}
    original_registry = sys.modules.get("ai_orchestrator.routers.registry")
    mocks = {
        "ai_orchestrator.llm.planner": MagicMock(),
        "ai_orchestrator.tasks.executor": MagicMock(),
        "tools.gates.approval": MagicMock(),
        "ai_orchestrator.audit.audit_logger": MagicMock(),
        "tools.gates.auth": MagicMock(),
        "ai_orchestrator.notify.telegram_webhook": MagicMock(),
        "ai_orchestrator.tasks.inbox": MagicMock(),
        "ai_orchestrator.connectors.google.gmail_reader": MagicMock(),
        "ai_orchestrator.sites.router": MagicMock(sites_router=APIRouter()),
        "ai_orchestrator.cad.router": MagicMock(cad_router=APIRouter()),
        "ai_orchestrator.web_task.web_task_router": MagicMock(web_task_router=APIRouter()),
        "ai_orchestrator.agent_hub.router.root": MagicMock(local_agent_router=APIRouter()),
        "ai_orchestrator.routers.admin_ui_router": MagicMock(admin_ui_router=APIRouter()),
        "ai_orchestrator.auth.auth_router": MagicMock(auth_router=APIRouter()),
        "ai_orchestrator.browser_tool.approval.approval_record_router": MagicMock(approval_record_router=APIRouter()),
        "ai_orchestrator.routers.action_router": MagicMock(action_router=APIRouter()),
        "ai_orchestrator.cad_ai_router": MagicMock(cad_ai_router=APIRouter()),
        "ai_orchestrator.connectors.naver_search.naver_search_router": MagicMock(naver_search_router=APIRouter()),
        "ai_orchestrator.routers.ops_router": MagicMock(ops_router=APIRouter()),
    }
    for mod_name, mock in mocks.items():
        sys.modules[mod_name] = mock
    import importlib.util as ilu

    spec = ilu.spec_from_file_location(
        "ai_orchestrator.routers.registry",
        REPO_ROOT / "ai_orchestrator/routers/registry.py",
    )
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod
    # sys.modules 오염 방지 — 원래 모듈로 복원
    for mod_name in mock_names:
        if originals[mod_name] is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = originals[mod_name]
    # 결함(2026-10-10, PR165 verify FAIL — 같은 사유: test_post_tasks_dry_run_flag_
    # implementation_20260518.py 와 동일 패턴). 원래 sys.modules 에 있던 진짜 registry
    # 모듈을 복원 — 무조건 pop 하면 뒤에 도는 다른 테스트의 importlib.reload() 가 깨진다.
    if original_registry is None:
        sys.modules.pop("ai_orchestrator.routers.registry", None)
    else:
        sys.modules["ai_orchestrator.routers.registry"] = original_registry


def _make_body(action_type="write_file", task_id="t-smoke"):
    body = MagicMock()
    body.model_dump.return_value = {
        "task_id": task_id,
        "source": "smoke",
        "action_type": action_type,
        "target": "/tmp/x",
        "description": "smoke test",
        "payload": {},
        "requested_by": None,
    }
    return body


def test_21_ms1_medium_issue_token_not_called(router_mod):
    """MS-1: medium → dry-run gate → issue_token 미호출"""
    mock_risk = MagicMock(risk_level="medium", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=True, steps=[], blocked_reasons=[])
    mock_req = MagicMock(task_id="t1", action_type="write_file", target="/tmp", requested_by="a1")

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token") as mock_issue,
        patch.object(router_mod, "execute") as mock_execute,
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        result = router_mod.submit_task(_make_body("write_file", "t1"), {"actor": "a1", "role": "operator"})  # noqa: F841

    mock_issue.assert_not_called()
    mock_execute.assert_not_called()


def test_22_ms2_medium_dry_run_status_and_field(router_mod):
    """MS-2: dry-run 응답 status 및 dry_run=True, approval_token_id=None"""
    mock_risk = MagicMock(risk_level="medium", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=True, steps=[], blocked_reasons=[])
    mock_req = MagicMock(task_id="t2", action_type="write_file", target="/tmp", requested_by="a1")

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token"),
        patch.object(router_mod, "execute"),
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        result = router_mod.submit_task(_make_body("write_file", "t2"), {"actor": "a1", "role": "operator"})

    assert "DRY_RUN" in result["status"]
    assert result.get("dry_run") is True
    assert result["approval_token_id"] is None


def test_23_ms3_approve_execute_task_not_called(router_mod):
    """MS-3: approve_task → approve_token만 호출, execute_task 없음"""
    mock_token = MagicMock(risk_level="medium", public_id="appr_x")
    mock_user = {"actor": "admin1", "role": "admin"}

    with (
        patch.object(router_mod, "approve_token", return_value=(mock_token, "approved")) as mock_approve,
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "_STATUS_AUDIT", {"approved": "APPROVAL_GRANTED"}),
        patch.object(router_mod, "_STATUS_HTTP", {"approved": 200}),
    ):
        result = router_mod.approve_task("task1", "token1", MagicMock(), mock_user)

    mock_approve.assert_called_once()
    assert result["status"] == "approved"
    # execute_task 속성 없음 확인
    assert not hasattr(router_mod, "execute_task") or "execute_task" not in router_mod.__dict__


def test_24_ms4_low_execute_called(router_mod):
    """MS-4: low 경로 → dry-run 분기 미적용, execute 호출"""
    mock_risk = MagicMock(risk_level="low", requires_approval=False)
    mock_ep = MagicMock(requires_approval=False, allowed=True, steps=[], blocked_reasons=[])
    mock_req = MagicMock(task_id="t4", action_type="get_server_status", target="server", requested_by="a1")

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token") as mock_issue,
        patch.object(router_mod, "execute", return_value="DRY_RUN_ONLY") as mock_execute,
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        result = router_mod.submit_task(_make_body("get_server_status", "t4"), {"actor": "a1", "role": "operator"})

    mock_issue.assert_not_called()
    mock_execute.assert_called_once()
    assert result.get("dry_run") is not True


def test_25_ms5_low_whitelist_enforced(executor_content):
    """MS-5: low whitelist 외 action은 executor.py에서 BLOCKED"""
    allowed_section = ""
    in_list = False
    for line in executor_content.splitlines():
        if "ALLOWED_ACTIONS" in line and "=" in line:
            in_list = True
        if in_list:
            allowed_section += line
            if "]" in line:
                break
    assert '"get_server_status"' in allowed_section
    assert '"fetch_web_page"' in allowed_section
    assert '"write_file"' not in allowed_section
    assert '"edit_config"' not in allowed_section


def test_26_ms6_blocked_path_no_dry_run(router_mod):
    """MS-6: allowed=False → dry-run 분기 미적용, BLOCKED 반환"""
    mock_risk = MagicMock(risk_level="high", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=False, steps=[], blocked_reasons=["차단"])
    mock_req = MagicMock(task_id="t6", action_type="shell", target="/", requested_by="a1")

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token") as mock_issue,
        patch.object(router_mod, "execute", return_value="BLOCKED: 차단") as mock_execute,  # noqa: F841
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        result = router_mod.submit_task(_make_body("shell", "t6"), {"actor": "a1", "role": "operator"})

    mock_issue.assert_not_called()
    assert result.get("dry_run") is not True


def test_27_ms7_high_critical_blocked_in_executor(executor_content):
    """MS-7: execute_task에서 high/critical 즉시 BLOCKED"""
    assert 'if risk_level in ("high", "critical")' in executor_content
    lines = executor_content.splitlines()
    for i, line in enumerate(lines):
        if 'if risk_level in ("high", "critical")' in line:
            next_lines = "\n".join(lines[i : i + 5])
            assert "BLOCKED" in next_lines
            break


def test_28_ms8_token_expiry_exists(approval_content):
    """MS-8: approval.py에 토큰 만료 검사 존재"""
    assert "_now() > expires" in approval_content or (
        "expires_at" in approval_content and "expired" in approval_content
    )


def test_29_dry_run_log_event_called_for_medium(router_mod):
    """medium dry-run 분기에서 DRY_RUN_GATE_BLOCKED log_event 호출 확인"""
    mock_risk = MagicMock(risk_level="medium", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=True, steps=[], blocked_reasons=[])
    mock_req = MagicMock(task_id="t9", action_type="write_file", target="/tmp", requested_by="a1")

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token"),
        patch.object(router_mod, "execute"),
        patch.object(router_mod, "log_event") as mock_log,
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        router_mod.submit_task(_make_body("write_file", "t9"), {"actor": "a1", "role": "operator"})

    log_calls = [str(c) for c in mock_log.call_args_list]
    assert any("DRY_RUN_GATE_BLOCKED" in c for c in log_calls)


def test_30_phase_1r_guards_still_active(router_content):
    """Phase 1-R guard 유지 확인"""
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in router_content
    )


# ── 31~35. 종합 판정 기준 ─────────────────────────────────────────────────────


def test_31_all_smoke_cases_pass(smoke_results):
    for smoke_id, result in smoke_results.items():
        assert result["result"] == "PASS", f"smoke FAIL: {smoke_id}"


def test_32_verdict_medium_token_blocked(verdict_criteria):
    assert verdict_criteria["medium_token_blocked"] is True


def test_33_verdict_low_unaffected(verdict_criteria):
    assert verdict_criteria["low_unaffected"] is True


def test_34_verdict_approve_not_connected(verdict_criteria):
    assert verdict_criteria["approve_not_connected"] is True


def test_35_verdict_dangerous_write_mitigated(verdict_criteria):
    assert verdict_criteria["dangerous_write_mitigated"] is True


# ── 36~38. 다음 Phase ────────────────────────────────────────────────────────


def test_36_next_phase_server_sync(next_phase):
    assert "SERVER_SYNC" in next_phase["phase"] or "SERVER" in next_phase["phase"]


def test_37_next_phase_conditions_gte_6(next_phase):
    assert len(next_phase["conditions"]) >= 6


def test_38_next_phase_requires_approval(next_phase):
    conditions = " ".join(next_phase["conditions"])
    assert "승인" in conditions or "approval" in conditions.lower()


# ── 39. no HTTP import ───────────────────────────────────────────────────────


def test_39_no_http_import_in_audit_script():
    content = (REPO_ROOT / "tools/audits/backend/audit_post_tasks_medium_isolation_smoke.py").read_text(
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


# ── 40~43. audit verdict ─────────────────────────────────────────────────────


def test_40_audit_verdict_pass(audit_result):
    assert audit_result["verdict"] in (
        "POST_TASKS_MEDIUM_ISOLATION_SMOKE_PASS",
        "POST_TASKS_MEDIUM_ISOLATION_SMOKE_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_41_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_42_audit_medium_token_blocked(audit_result):
    assert audit_result["medium_token_blocked"] is True


def test_43_audit_smoke_mock_only(audit_result):
    assert audit_result["smoke_mock_only"] is True
    assert audit_result["approve_not_connected"] is True
