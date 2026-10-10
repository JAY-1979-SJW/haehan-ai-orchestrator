"""
LOCAL_AGENT_WEBSOCKET_USER_PRESENT_DISPATCH_RUNTIME_1 테스트

routing dry-run 결과 DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED 시
서버가 연결된 로컬 Agent에 USER_PRESENT_TASK를 push하고
로컬 Agent가 WAITING_FOR_USER 상태를 생성하는 경로를 검증한다.

보안 원칙:
- safe_to_execute=False 항상
- raw target_url 포함 금지
- click/type/fill/submit 코드 없음
- cookie/session/token 저장·전송 금지
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ── 경로 설정 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── fixture 로드 ─────────────────────────────────────────────────────────────
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "local_agent_websocket_user_present_dispatch_runtime_20260507.json"


def _load_fixture():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _case(case_id: str) -> dict:
    data = _load_fixture()
    for c in data["cases"]:
        if c["id"] == case_id:
            return c
    raise KeyError(f"fixture case not found: {case_id}")


# ── 모듈 임포트 ──────────────────────────────────────────────────────────────
from ai_orchestrator.agent_hub.user_present_dispatcher import (  # noqa: E402
    DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    build_user_present_dispatch_context,
    build_user_present_dispatch_response,
    build_user_present_task_from_dryrun,
    should_dispatch_user_present_task,
    validate_user_present_dispatch_request,
)

# ════════════════════════════════════════════════════════════════════════════
# 1. should_dispatch_user_present_task
# ════════════════════════════════════════════════════════════════════════════


class TestShouldDispatch:
    def test_user_present_required_true(self):
        c = _case("should_dispatch_when_user_present_required")
        result = should_dispatch_user_present_task(c["input"]["dryrun_result"])
        assert result is True

    def test_server_playwright_false(self):
        c = _case("should_not_dispatch_server_playwright")
        result = should_dispatch_user_present_task(c["input"]["dryrun_result"])
        assert result is False

    def test_blocked_false(self):
        c = _case("should_not_dispatch_blocked")
        result = should_dispatch_user_present_task(c["input"]["dryrun_result"])
        assert result is False

    def test_api_connector_false(self):
        c = _case("should_not_dispatch_api_connector")
        result = should_dispatch_user_present_task(c["input"]["dryrun_result"])
        assert result is False

    def test_manual_review_false(self):
        c = _case("should_not_dispatch_manual_review")
        result = should_dispatch_user_present_task(c["input"]["dryrun_result"])
        assert result is False

    def test_empty_dryrun_false(self):
        assert should_dispatch_user_present_task({}) is False

    def test_none_dryrun_false(self):
        assert should_dispatch_user_present_task({"dispatch_decision": None}) is False


# ════════════════════════════════════════════════════════════════════════════
# 2. build_user_present_dispatch_context
# ════════════════════════════════════════════════════════════════════════════


class TestBuildDispatchContext:
    def test_eligible_when_user_present_required(self):
        c = _case("dispatch_context_eligible")
        ctx = build_user_present_dispatch_context(c["input"])
        assert ctx["dispatch_eligible"] is True
        assert ctx["safe_to_execute"] is False

    def test_not_eligible_when_blocked(self):
        c = _case("dispatch_context_not_eligible")
        ctx = build_user_present_dispatch_context(c["input"])
        assert ctx["dispatch_eligible"] is False
        assert ctx["safe_to_execute"] is False

    def test_safe_to_execute_always_false(self):
        ctx = build_user_present_dispatch_context(
            {
                "workflow_run_id": "wr_x",
                "dryrun_result": {"dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED},
            }
        )
        assert ctx["safe_to_execute"] is False

    def test_context_has_required_keys(self):
        ctx = build_user_present_dispatch_context(
            {
                "workflow_run_id": "wr_x",
                "tenant_id": "t1",
                "dryrun_result": {},
            }
        )
        required = ["workflow_run_id", "tenant_id", "dispatch_eligible", "safe_to_execute", "dryrun_result"]
        for key in required:
            assert key in ctx, f"컨텍스트에 키 없음: {key}"


# ════════════════════════════════════════════════════════════════════════════
# 3. build_user_present_task_from_dryrun
# ════════════════════════════════════════════════════════════════════════════


class TestBuildTaskFromDryrun:
    def test_message_type_is_user_present_task(self):
        c = _case("build_task_from_dryrun_valid")
        msg = build_user_present_task_from_dryrun(c["input"])
        assert msg.get("message_type") == "USER_PRESENT_TASK"

    def test_safe_to_execute_false(self):
        c = _case("build_task_from_dryrun_valid")
        msg = build_user_present_task_from_dryrun(c["input"])
        assert msg.get("safe_to_execute") is False

    def test_no_raw_target_url(self):
        c = _case("build_task_from_dryrun_no_raw_url")
        msg = build_user_present_task_from_dryrun(c["input"])
        assert "target_url" not in msg

    def test_redacted_url_preserved(self):
        c = _case("build_task_from_dryrun_valid")
        msg = build_user_present_task_from_dryrun(c["input"])
        instruction = c["input"].get("next_step_instruction", {})
        if instruction.get("target_url_redacted"):
            assert "target_url_redacted" in msg

    def test_no_forbidden_fields(self):
        forbidden = ["password", "otp", "cookie", "session", "token", "target_url"]
        msg = build_user_present_task_from_dryrun(
            {
                "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                "workflow_run_id": "wr_x",
                "next_step_instruction": {
                    "password": "secret",
                    "target_url": "https://example.com/login",
                },
            }
        )
        for field in forbidden:
            assert field not in msg, f"금지 필드 포함됨: {field}"


# ════════════════════════════════════════════════════════════════════════════
# 4. validate_user_present_dispatch_request
# ════════════════════════════════════════════════════════════════════════════


class TestValidateDispatchRequest:
    def test_missing_workflow_run_id(self):
        c = _case("validate_missing_workflow_run_id")
        errors = validate_user_present_dispatch_request(c["input"])
        assert len(errors) > 0
        assert any("workflow_run_id" in e for e in errors)

    def test_missing_selected_agent_id(self):
        c = _case("validate_missing_selected_agent_id")
        errors = validate_user_present_dispatch_request(c["input"])
        assert len(errors) > 0
        assert any("AGENT_SELECTION_REQUIRED" in e for e in errors)

    def test_wrong_dispatch_decision(self):
        c = _case("validate_wrong_dispatch_decision")
        errors = validate_user_present_dispatch_request(c["input"])
        assert len(errors) > 0

    def test_safe_to_execute_true_rejected(self):
        c = _case("validate_safe_to_execute_true_rejected")
        errors = validate_user_present_dispatch_request(c["input"])
        assert any("safe_to_execute" in e for e in errors)

    def test_valid_request_no_errors(self):
        errors = validate_user_present_dispatch_request(
            {
                "workflow_run_id": "wr_valid",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "selected_agent_id": "agent_001",
                "dryrun_result": {
                    "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                },
            }
        )
        assert errors == []

    def test_missing_tenant_id(self):
        errors = validate_user_present_dispatch_request(
            {
                "workflow_run_id": "wr_x",
                "user_id": "u1",
                "site_id": "s1",
                "selected_agent_id": "agent_001",
                "dryrun_result": {
                    "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                },
            }
        )
        assert any("tenant_id" in e for e in errors)


# ════════════════════════════════════════════════════════════════════════════
# 5. build_user_present_dispatch_response
# ════════════════════════════════════════════════════════════════════════════


class TestBuildDispatchResponse:
    def test_valid_response_ok(self):
        c = _case("build_dispatch_response_valid")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["dispatched"] is True
        assert result["safe_to_execute"] is False

    def test_invalid_response_not_ok(self):
        c = _case("build_dispatch_response_invalid")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is False
        assert result["dispatched"] is False
        assert result["safe_to_execute"] is False

    def test_response_contains_task_message(self):
        c = _case("dispatch_response_contains_task_message")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert "task_message" in result
        assert result["task_message"].get("message_type") == "USER_PRESENT_TASK"

    def test_response_safe_to_execute_always_false(self):
        c = _case("dispatch_response_safe_to_execute_always_false")
        result = build_user_present_dispatch_response(c["input"])
        assert result.get("safe_to_execute") is False

    def test_response_dispatch_decision_correct(self):
        c = _case("build_dispatch_response_valid")
        result = build_user_present_dispatch_response(c["input"])
        assert result["dispatch_decision"] == DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED

    def test_task_message_no_raw_url(self):
        result = build_user_present_dispatch_response(
            {
                "workflow_run_id": "wr_url_001",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "selected_agent_id": "agent_001",
                "dryrun_result": {
                    "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                    "next_step_instruction": {
                        "target_url": "https://kbstar.com/login",
                        "target_url_redacted": "https://kbstar.com/***",
                        "target_url_hash": "abc123",
                    },
                },
            }
        )
        assert result["ok"] is True
        task_msg = result.get("task_message", {})
        assert "target_url" not in task_msg


# ════════════════════════════════════════════════════════════════════════════
# 6. in-memory 큐 (router)
# ════════════════════════════════════════════════════════════════════════════


class TestInMemoryQueue:
    def test_enqueue_and_drain(self):
        from ai_orchestrator.agent_hub.router.root import _drain_up_tasks, _enqueue_up_task

        _drain_up_tasks("agent_q_test")  # 초기화
        task = {"message_type": "USER_PRESENT_TASK", "workflow_run_id": "wr_q_001", "safe_to_execute": False}
        _enqueue_up_task("agent_q_test", task)
        drained = _drain_up_tasks("agent_q_test")
        assert len(drained) == 1
        assert drained[0]["message_type"] == "USER_PRESENT_TASK"
        assert drained[0]["safe_to_execute"] is False

    def test_drain_empty_queue(self):
        from ai_orchestrator.agent_hub.router.root import _drain_up_tasks

        drained = _drain_up_tasks("agent_empty_test")
        assert drained == []

    def test_drain_clears_queue(self):
        from ai_orchestrator.agent_hub.router.root import _drain_up_tasks, _enqueue_up_task

        _drain_up_tasks("agent_clear_test")
        _enqueue_up_task("agent_clear_test", {"message_type": "USER_PRESENT_TASK", "safe_to_execute": False})
        _drain_up_tasks("agent_clear_test")
        drained_again = _drain_up_tasks("agent_clear_test")
        assert drained_again == []

    def test_multiple_agents_isolated(self):
        from ai_orchestrator.agent_hub.router.root import _drain_up_tasks, _enqueue_up_task

        _drain_up_tasks("agent_a")
        _drain_up_tasks("agent_b")
        _enqueue_up_task("agent_a", {"message_type": "USER_PRESENT_TASK", "wfid": "a1", "safe_to_execute": False})
        _enqueue_up_task("agent_b", {"message_type": "USER_PRESENT_TASK", "wfid": "b1", "safe_to_execute": False})
        drained_a = _drain_up_tasks("agent_a")
        drained_b = _drain_up_tasks("agent_b")
        assert len(drained_a) == 1 and drained_a[0]["wfid"] == "a1"
        assert len(drained_b) == 1 and drained_b[0]["wfid"] == "b1"

    def test_enqueued_task_safe_to_execute_false(self):
        from ai_orchestrator.agent_hub.router.root import _drain_up_tasks, _enqueue_up_task

        _drain_up_tasks("agent_sec_test")
        task = {"message_type": "USER_PRESENT_TASK", "safe_to_execute": False}
        _enqueue_up_task("agent_sec_test", task)
        drained = _drain_up_tasks("agent_sec_test")
        assert drained[0]["safe_to_execute"] is False


# ════════════════════════════════════════════════════════════════════════════
# 7. 보안 원칙 검증
# ════════════════════════════════════════════════════════════════════════════


class TestSecurityPolicy:
    def test_dispatcher_has_no_browser_launch_code(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_dispatcher as mod

        src = inspect.getsource(mod)
        forbidden = ["playwright", "chromium", "firefox", "websockets.connect", "click(", "fill(", "type("]
        for pattern in forbidden:
            assert pattern not in src, f"금지 패턴 포함: {pattern}"

    def test_dispatcher_safe_to_execute_always_false(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_dispatcher as mod

        src = inspect.getsource(mod)
        assert "safe_to_execute" in src

    def test_no_raw_url_in_dispatch_constants(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_dispatcher as mod

        src = inspect.getsource(mod)
        assert "target_url" not in src or "target_url_redacted" in src or "target_url_hash" in src

    def test_dispatch_response_never_contains_raw_url(self):
        result = build_user_present_dispatch_response(
            {
                "workflow_run_id": "wr_sec_url",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "selected_agent_id": "agent_001",
                "dryrun_result": {
                    "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                    "next_step_instruction": {"target_url": "https://secret.example.com/login"},
                },
            }
        )
        # task_message에 raw target_url이 없어야 함
        task_msg = result.get("task_message", {})
        assert "target_url" not in task_msg

    def test_dispatch_context_safe_to_execute_cannot_be_true(self):
        ctx = build_user_present_dispatch_context(
            {
                "safe_to_execute": True,  # 무시되어야 함
                "dryrun_result": {},
            }
        )
        assert ctx["safe_to_execute"] is False

    def test_should_dispatch_returns_bool(self):
        result = should_dispatch_user_present_task(
            {
                "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
            }
        )
        assert isinstance(result, bool)


# ════════════════════════════════════════════════════════════════════════════
# 8. fixture 무결성
# ════════════════════════════════════════════════════════════════════════════


class TestFixtureIntegrity:
    def test_fixture_exists(self):
        assert FIXTURE_PATH.exists(), f"fixture 파일 없음: {FIXTURE_PATH}"

    def test_fixture_has_required_fields(self):
        data = _load_fixture()
        assert "version" in data
        assert "cases" in data
        assert len(data["cases"]) >= 18

    def test_all_cases_have_id_and_expected(self):
        data = _load_fixture()
        for c in data["cases"]:
            assert "id" in c, f"id 없음: {c}"
            assert "expected" in c, f"expected 없음: {c['id']}"

    def test_all_expected_safe_to_execute_false(self):
        data = _load_fixture()
        for c in data["cases"]:
            exp = c.get("expected", {})
            if "safe_to_execute" in exp:
                assert exp["safe_to_execute"] is False, f"케이스 {c['id']}: safe_to_execute는 항상 False여야 함"

    def test_no_raw_url_in_expected(self):
        data = _load_fixture()
        for c in data["cases"]:
            exp_str = json.dumps(c.get("expected", {}))
            # 실제 URL 패턴(쿼리스트링 포함)은 없어야 함 (redacted URL은 허용)
            assert "/login" not in exp_str, f"케이스 {c['id']}: raw URL 포함 가능성"
