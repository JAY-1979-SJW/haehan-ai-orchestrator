"""failure_reason/error_summary 가 "agent_error" 로만 뭉뚱그려지지 않는지 (2026-10-08).

실사용 중 발견: AI 콘솔에서 작업이 실패하면 늘 "작업 실패: agent_error"만 보였다. 원인 중
하나는 프런트(UniversalChat.tsx)가 failure_reason(항상 "agent_error")을 error_summary(구체적
원인, 예: "CLAUDE_CLI_NOT_FOUND: claude CLI를 찾을 수 없습니다")보다 먼저 썼기 때문 — 그건
고쳤지만(이 파일은 그 전제가 되는 서버 쪽을 검사), apply_result()가 error_summary 를 애초에
비워 두면 프런트가 뭘 먼저 보든 소용없다. error_code·error 가 있으면 error_summary 에 구체적인
내용이 반드시 들어가야 한다.
"""

from ai_orchestrator import local_agent_registry as reg


def _setup_running_task():
    agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
    task = reg.enqueue_task(
        agent_id=agent.agent.agent_id,
        action="run_claude_agent",
        params={"prompt": "p"},
        requested_by="test",
    )
    reg.mark_delivered(agent.agent.agent_id, task.task_id)
    reg.mark_running(agent.agent.agent_id, task.task_id)
    return agent.agent.agent_id, task.task_id


class TestFailureReasonIsSpecific:
    def setup_method(self):
        reg.clear()

    def test_claude_cli_not_found_error_summary_is_specific(self):
        """local_agent.actions.action_run_claude_agent 이 돌려주는 실제 모양(error_code=CLAUDE_CLI_NOT_FOUND,
        error="claude CLI를 찾을 수 없습니다 (PATH 확인 필요)")을 그대로 apply_result 에 넣었을 때,
        error_summary 가 "agent_error" 하나로 뭉개지지 않고 코드·문구를 담아야 한다."""
        agent_id, task_id = _setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=False,
            summary="run_claude_agent 실패",
            error="claude CLI를 찾을 수 없습니다 (PATH 확인 필요)",
            error_code="CLAUDE_CLI_NOT_FOUND",
        )
        assert result is not None
        assert result.status == "failed"
        assert result.error_summary != "agent_error"
        assert "CLAUDE_CLI_NOT_FOUND" in result.error_summary
        assert "claude CLI를 찾을 수 없습니다" in result.error_summary

    def test_claude_agent_error_with_stderr_snippet_is_specific(self):
        """MCP 설정 문제 등으로 claude -p 가 exit!=0 일 때(error_code=CLAUDE_AGENT_ERROR)도
        stderr 앞부분이 error_summary 에 들어가야 한다(2026-10-08 agent_error 사고 재발 방지)."""
        agent_id, task_id = _setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=False,
            summary="실패(exit=1)",
            error="Invalid MCP configuration: MCP config file not found",
            error_code="CLAUDE_AGENT_ERROR",
        )
        assert result is not None
        assert result.error_summary != "agent_error"
        assert "MCP config file not found" in result.error_summary

    def test_failure_without_error_code_or_message_still_sets_generic_failure_reason(self):
        """error_code·error 가 둘 다 없는 호출(기존 호출부 호환)은 failure_reason="agent_error" 로
        남아도 된다 — 이 시험은 그 경우까지 깨지 않았는지만 확인한다(회귀 방지)."""
        agent_id, task_id = _setup_running_task()
        result = reg.apply_result(agent_id=agent_id, task_id=task_id, success=False, summary="")
        assert result is not None
        assert result.failure_reason == "agent_error"
