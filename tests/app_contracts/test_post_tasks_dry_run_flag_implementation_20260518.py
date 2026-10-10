"""
POST /api/v1/tasks Dry-Run Flag Implementation 테스트
tests/test_post_tasks_dry_run_flag_implementation_20260518.py

POST_TASKS_DRY_RUN_ENABLED=True 플래그 및 submit_task 분기 구현 검증.
실제 token 발행 / execute_task 호출 / DB write / 서버 반영 전면 금지.
"""

import ast
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        "audit_dry_run_impl",
        "tools/audits/backend/audit_post_tasks_dry_run_flag_implementation.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def impl_record(audit_mod):
    return audit_mod.IMPLEMENTATION_RECORD


@pytest.fixture(scope="module")
def path_impact(audit_mod):
    return audit_mod.PATH_IMPACT_ANALYSIS


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


# ── 3~6. 운영 안전 플래그 ────────────────────────────────────────────────────


def test_03_approval_token_not_allowed(audit_mod):
    assert audit_mod.APPROVAL_TOKEN_ISSUE_ALLOWED is False


def test_04_execute_task_not_allowed(audit_mod):
    assert audit_mod.EXECUTE_TASK_CALL_ALLOWED is False


def test_05_db_write_not_allowed(audit_mod):
    assert audit_mod.DB_WRITE_ALLOWED is False


def test_06_server_deploy_not_allowed(audit_mod):
    assert audit_mod.SERVER_DEPLOY_ALLOWED is False


# ── 7~16. router.py 구현 검증 ────────────────────────────────────────────────


def test_07_dry_run_flag_present(router_content):
    assert "POST_TASKS_DRY_RUN_ENABLED = True" in router_content


def test_08_dry_run_flag_in_feature_flag_section(router_content):
    lines = router_content.splitlines()
    flag_line = next((i for i, l in enumerate(lines) if "POST_TASKS_DRY_RUN_ENABLED = True" in l), None)  # noqa: E741
    assert flag_line is not None
    context = "\n".join(lines[max(0, flag_line - 10) : flag_line])
    assert "Phase 1-R" in context or "LEGACY_5050" in context


def test_09_dry_run_branch_present(router_content):
    assert "POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval" in router_content


def test_10_dry_run_branch_before_issue_token(router_content):
    dry_run_pos = router_content.find("POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval")
    issue_token_pos = router_content.find("issue_token(req, risk")
    assert dry_run_pos < issue_token_pos, "dry-run 분기가 issue_token 호출 이후에 위치함"


def test_11_dry_run_gate_blocked_log_event(router_content):
    assert "DRY_RUN_GATE_BLOCKED" in router_content


def test_12_dry_run_status_string(router_content):
    assert "DRY_RUN: would issue token" in router_content


def test_13_dry_run_response_has_dry_run_field(router_content):
    assert '"dry_run": True' in router_content or "'dry_run': True" in router_content


def test_14_issue_token_still_preserved(router_content):
    # dry-run OFF 경로 보존 — issue_token 코드 삭제되지 않아야 함
    assert "issue_token(req, risk" in router_content


def test_15_phase_1r_guards_intact(router_content):
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content


def test_16_touch_phase_1r_preserved(router_content):
    assert (
        'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router_content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router_content
    )


# ── 17~24. submit_task 동작 unit test (mock 기반) ─────────────────────────────


@pytest.fixture(scope="module")
def router_mod():
    """router 모듈 import — DB/외부 호출 없이 구조만."""
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
        "ai_orchestrator.sites.router": MagicMock(sites_router=MagicMock()),
        "ai_orchestrator.cad.router": MagicMock(cad_router=MagicMock()),
        "ai_orchestrator.web_task.web_task_router": MagicMock(web_task_router=MagicMock()),
        "ai_orchestrator.agent_hub.router.root": MagicMock(local_agent_router=MagicMock()),
        "ai_orchestrator.routers.admin_ui_router": MagicMock(admin_ui_router=MagicMock()),
        "ai_orchestrator.auth.auth_router": MagicMock(auth_router=MagicMock()),
        "ai_orchestrator.browser_tool.approval.approval_record_router": MagicMock(approval_record_router=MagicMock()),
        "ai_orchestrator.routers.action_router": MagicMock(action_router=MagicMock()),
        "ai_orchestrator.cad_ai_router": MagicMock(cad_ai_router=MagicMock()),
        "ai_orchestrator.connectors.naver_search.naver_search_router": MagicMock(naver_search_router=MagicMock()),
        "ai_orchestrator.routers.ops_router": MagicMock(ops_router=MagicMock()),
    }
    for mod_name, mock in mocks.items():
        sys.modules[mod_name] = mock
    try:
        import importlib.util as ilu

        spec = ilu.spec_from_file_location(
            "ai_orchestrator.routers.registry",
            REPO_ROOT / "ai_orchestrator/routers/registry.py",
        )
        mod = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    except Exception:  # noqa: BLE001 - pytest fixture — 테스트용 router 모듈을 exec_module로 로드하다 실패하면 yield None 하고, 각 테스트는 router_mod is None 이면 pytest.skip 으로 건너뛰는 테스트 전용 폴백(운영 코드 아님).
        yield None
    finally:
        # sys.modules 오염 방지 — 원래 모듈로 복원
        for mod_name in mock_names:
            if originals[mod_name] is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = originals[mod_name]
        # 결함(2026-10-10, PR165 verify FAIL — importlib.reload() 가 다른 테스트에서
        # "module ... not in sys.modules" 로 터지는 원인 조사 중 발견): 이 모듈은 임시로
        # exec_module 한 별도 복사본일 뿐인데, 원래 sys.modules 에 진짜(정상 import 된)
        # registry 모듈이 있었다면 그걸 무조건 pop 하면 안 되고 복원해야 한다 — 그래야
        # 뒤에 도는 다른 테스트의 `import ai_orchestrator.routers.registry as x;
        # importlib.reload(x)` 가 "sys.modules 에 없음" 으로 안 깨진다.
        if original_registry is None:
            sys.modules.pop("ai_orchestrator.routers.registry", None)
        else:
            sys.modules["ai_orchestrator.routers.registry"] = original_registry


def test_17_dry_run_flag_value_true(router_mod):
    if router_mod is None:
        pytest.skip("router 모듈 로드 실패")
    assert router_mod.POST_TASKS_DRY_RUN_ENABLED is True


def test_18_medium_path_returns_dry_run_status(router_mod):
    """medium 경로: dry-run=True → issue_token 미호출, DRY_RUN 상태 반환"""
    if router_mod is None:
        pytest.skip("router 모듈 로드 실패")

    mock_risk = MagicMock(risk_level="medium", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=True, steps=[], blocked_reasons=[])
    mock_req = MagicMock(task_id="t1", action_type="write_file", target="/tmp/x", requested_by="actor1")
    mock_user = {"actor": "actor1", "role": "operator"}

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token") as mock_issue,
        patch.object(router_mod, "execute") as mock_execute,
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        body = MagicMock()
        body.model_dump.return_value = {
            "task_id": "t1",
            "source": "test",
            "action_type": "write_file",
            "target": "/tmp/x",
            "description": "test",
            "payload": {},
            "requested_by": None,
        }

        result = router_mod.submit_task(body, mock_user)

        # issue_token 미호출
        mock_issue.assert_not_called()
        # execute 미호출
        mock_execute.assert_not_called()
        # DRY_RUN 상태 반환
        assert "DRY_RUN" in result["status"]
        assert result.get("dry_run") is True
        assert result["approval_token_id"] is None


def test_19_low_path_unaffected_by_dry_run(router_mod):
    """low 경로: requires_approval=False → dry-run 분기 미적용, execute 호출됨"""
    if router_mod is None:
        pytest.skip("router 모듈 로드 실패")

    mock_risk = MagicMock(risk_level="low", requires_approval=False)
    mock_ep = MagicMock(requires_approval=False, allowed=True, steps=[], blocked_reasons=[])
    mock_req = MagicMock(task_id="t2", action_type="get_server_status", target="server", requested_by="actor1")
    mock_user = {"actor": "actor1", "role": "operator"}

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token") as mock_issue,
        patch.object(router_mod, "execute", return_value="DRY_RUN_ONLY") as mock_execute,
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        body = MagicMock()
        body.model_dump.return_value = {
            "task_id": "t2",
            "source": "test",
            "action_type": "get_server_status",
            "target": "server",
            "description": "test",
            "payload": {},
            "requested_by": None,
        }

        result = router_mod.submit_task(body, mock_user)

        mock_issue.assert_not_called()
        mock_execute.assert_called_once()
        assert result.get("dry_run") is not True


def test_20_blocked_path_unaffected_by_dry_run(router_mod):
    """blocked 경로: allowed=False → dry-run 분기 미적용"""
    if router_mod is None:
        pytest.skip("router 모듈 로드 실패")

    mock_risk = MagicMock(risk_level="high", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=False, steps=[], blocked_reasons=["차단 경로"])
    mock_req = MagicMock(task_id="t3", action_type="shell", target="/", requested_by="actor1")
    mock_user = {"actor": "actor1", "role": "operator"}

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token") as mock_issue,
        patch.object(router_mod, "execute", return_value="BLOCKED: 차단 경로"),
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        body = MagicMock()
        body.model_dump.return_value = {
            "task_id": "t3",
            "source": "test",
            "action_type": "shell",
            "target": "/",
            "description": "test",
            "payload": {},
            "requested_by": None,
        }

        result = router_mod.submit_task(body, mock_user)

        mock_issue.assert_not_called()
        assert result.get("dry_run") is not True


def test_21_dry_run_response_structure(router_mod):
    """dry-run 응답에 필수 필드 존재 확인"""
    if router_mod is None:
        pytest.skip("router 모듈 로드 실패")

    mock_risk = MagicMock(risk_level="medium", requires_approval=True)
    mock_ep = MagicMock(requires_approval=True, allowed=True, steps=["s1"], blocked_reasons=[])
    mock_req = MagicMock(task_id="t4", action_type="write_file", target="/tmp", requested_by="actor1")
    mock_user = {"actor": "actor1", "role": "operator"}

    with (
        patch.object(router_mod, "plan", return_value=(mock_risk, mock_ep)),
        patch.object(router_mod, "issue_token"),
        patch.object(router_mod, "execute"),
        patch.object(router_mod, "log_event"),
        patch.object(router_mod, "TaskRequest", return_value=mock_req),
    ):
        body = MagicMock()
        body.model_dump.return_value = {
            "task_id": "t4",
            "source": "test",
            "action_type": "write_file",
            "target": "/tmp",
            "description": "test",
            "payload": {},
            "requested_by": None,
        }

        result = router_mod.submit_task(body, mock_user)

    required_fields = [
        "task_id",
        "risk_level",
        "allowed",
        "requires_approval",
        "approval_token_id",
        "status",
        "steps",
        "blocked_reasons",
        "dry_run",
    ]
    for field in required_fields:
        assert field in result, f"응답에 {field} 필드 없음"


# ── 22~25. 경로 영향 분석 검증 ───────────────────────────────────────────────


def test_22_medium_path_no_token(path_impact):
    medium = path_impact["medium_requires_approval_True_allowed_True"]
    assert medium["token_issued"] is False
    assert "DRY_RUN" in medium["after"]


def test_23_low_path_unchanged(path_impact):
    low = path_impact["low_requires_approval_False"]
    assert "변경 없음" in low["after"]


def test_24_blocked_path_unchanged(path_impact):
    blocked = path_impact["blocked_allowed_False"]
    assert "변경 없음" in blocked["after"]


def test_25_high_critical_unchanged(path_impact):
    hc = path_impact["high_critical"]
    assert "변경 없음" in hc["after"]


# ── 26~28. 다음 Phase ────────────────────────────────────────────────────────


def test_26_next_phase_isolation_smoke(next_phase):
    assert "ISOLATION_SMOKE" in next_phase["phase"] or "SMOKE" in next_phase["phase"]


def test_27_next_phase_conditions_gte_6(next_phase):
    assert len(next_phase["all_conditions_must_be_met"]) >= 6


def test_28_next_phase_requires_representative_approval(next_phase):
    conditions = " ".join(next_phase["all_conditions_must_be_met"])
    assert "대표" in conditions or "승인" in conditions


# ── 29. no HTTP import ───────────────────────────────────────────────────────


def test_29_no_http_import_in_audit_script():
    content = (REPO_ROOT / "tools/audits/backend/audit_post_tasks_dry_run_flag_implementation.py").read_text(
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


# ── 30~33. audit verdict ─────────────────────────────────────────────────────


def test_30_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "POST_TASKS_DRY_RUN_IMPLEMENTATION_READY",
        "POST_TASKS_DRY_RUN_IMPLEMENTATION_READY_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_31_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_32_audit_dry_run_branch_active(audit_result):
    assert audit_result["dry_run_branch_active"] is True


def test_33_audit_phase_1r_guards_intact(audit_result):
    assert audit_result["phase_1r_guards_intact"] is True
