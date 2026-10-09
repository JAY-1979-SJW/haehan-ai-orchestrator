"""core/agent_runtime/connection/actions.py의 action_run_claude_agent 회귀 테스트.

실기 검증(2026-09-28): --allowedTools 는 공식 --help상 "<tools...>" 로 표기된
greedy 옵션이라, 구분자 없이 prompt를 바로 이어 붙이면 prompt까지 도구 이름으로
먹혀 "Input must be provided ... when using --print" 오류가 났다(실측 확인).
이 파일은 subprocess.run을 모킹해 실제 claude CLI 없이도 cmd 배열 구성 자체가
그 버그를 재발시키지 않는지 검사한다. MCP 도구 호출까지 포함한 실제 종단 검증은
docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md 참고
(target=app snapshot_page 실제 호출, denials=[], result="40" 확인됨).
"""

from __future__ import annotations

import json
from unittest.mock import patch

from core.agent_runtime.connection.actions import action_run_claude_agent


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _ok_payload(result: str = "1") -> str:
    return json.dumps({"result": result, "is_error": False, "session_id": "s1", "total_cost_usd": 0.01, "num_turns": 1})


def test_missing_prompt_short_circuits_without_subprocess() -> None:
    with patch("core.agent_runtime.connection.actions.subprocess.run") as run:
        result = action_run_claude_agent({})
    run.assert_not_called()
    assert result.success is False
    assert result.error_code == "MISSING_PROMPT"


def test_cmd_has_no_allowed_tools_flag_when_not_requested() -> None:
    """allowed_tools 미지정 시 --allowedTools 를 아예 안 붙인다(기존 안전한 기본값 유지)."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=fake_run):
        result = action_run_claude_agent({"prompt": "숫자 1만 답해"})

    assert result.success is True
    cmd = captured["cmd"]
    assert "--allowedTools" not in cmd
    # prompt는 "--" 뒤에 옵션 파싱이 끝난 채로 마지막 인자로 붙어야 한다.
    assert cmd[-2:] == ["--", "숫자 1만 답해"]


def test_cmd_joins_allowed_tools_and_terminates_options_before_prompt() -> None:
    """allowed_tools 지정 시 콤마로 합쳐 --allowedTools 로 전달하고, 그 뒤 "--" 로
    옵션 파싱을 끊어야 prompt가 도구 이름으로 먹히지 않는다(실측으로 확인한 버그의
    회귀 테스트)."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(_ok_payload("40"))

    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=fake_run):
        result = action_run_claude_agent(
            {
                "prompt": "스냅샷 노드 개수만 답해",
                "allowed_tools": [
                    "mcp__haehan-orchestrator__snapshot_page",
                    "mcp__haehan-orchestrator__navigate_page",
                ],
            }
        )

    assert result.success is True
    assert result.data["result"] == "40"
    cmd = captured["cmd"]
    idx = cmd.index("--allowedTools")
    assert cmd[idx + 1] == "mcp__haehan-orchestrator__snapshot_page,mcp__haehan-orchestrator__navigate_page"
    # --allowedTools 값 바로 다음이 "--", 그다음이 prompt여야 한다(그 사이에 다른
    # 토큰이 끼면 greedy 옵션이 prompt까지 삼킨다).
    assert cmd[idx + 2 : idx + 4] == ["--", "스냅샷 노드 개수만 답해"]


def test_single_string_allowed_tools_is_normalized_to_list() -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "p", "allowed_tools": "mcp__haehan-orchestrator__snapshot_page"})

    cmd = captured["cmd"]
    idx = cmd.index("--allowedTools")
    assert cmd[idx + 1] == "mcp__haehan-orchestrator__snapshot_page"


def test_claude_cli_not_found_returns_error_code() -> None:
    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=FileNotFoundError):
        result = action_run_claude_agent({"prompt": "p"})
    assert result.success is False
    assert result.error_code == "CLAUDE_CLI_NOT_FOUND"


def test_result_full_is_opt_in_and_default_behavior_unchanged() -> None:
    """작업 분배 종단 시험(2026-10-02)에서 계획 JSON 이 잘려 파싱 실패 → 긴 결과는 선택 키로만 제공."""
    long_text = "가" * 5000

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(_ok_payload(long_text))

    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=fake_run):
        default = action_run_claude_agent({"prompt": "x"})
        wanted = action_run_claude_agent({"prompt": "x", "result_max_chars": 4000})
        capped = action_run_claude_agent({"prompt": "x", "result_max_chars": 10**9})
        bad = action_run_claude_agent({"prompt": "x", "result_max_chars": "abc"})

    assert len(default.data["result"]) == 2000 and "result_full" not in default.data  # 기존 호출 불변
    assert len(wanted.data["result"]) == 2000 and len(wanted.data["result_full"]) == 4000
    assert len(capped.data["result_full"]) == 5000  # 20000 상한 안에서 전문
    assert "result_full" not in bad.data


def _capture_cmd(params: dict) -> list[str]:
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "조사해", **params})
    return captured["cmd"]


def test_restricted_mode_closes_tool_set_and_mcp() -> None:
    """실측(2026-10-02): --allowedTools 만으로는 Bash 가 실행됐다 — 읽기 전용 호출은 도구 집합 자체를 닫는다."""
    cmd = _capture_cmd(
        {"restricted": True, "allowed_tools": ["Read", "Grep", "Glob", "mcp__haehan-orchestrator__call_api"]}
    )
    assert "--restricted" in cmd and "--strict-mcp-config" in cmd
    assert "--mcp-config" not in cmd  # MCP 서버를 하나도 싣지 않는다
    assert cmd[cmd.index("--tools") + 1] == "Read,Grep,Glob"  # 도구 집합 한정, mcp__ 이름은 제거됨
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Grep,Glob"
    assert "--dangerously-skip-permissions" not in cmd
    assert cmd[-2:] == ["--", "조사해"]


def test_default_mode_command_unchanged_by_restricted_support() -> None:
    cmd = _capture_cmd({"allowed_tools": ["Read"]})
    assert "--mcp-config" in cmd and "--restricted" not in cmd and "--strict-mcp-config" not in cmd
    assert "--tools" not in cmd


def test_restricted_requires_literal_true() -> None:
    for value in ("true", 1, "yes", None):
        cmd = _capture_cmd({"restricted": value, "allowed_tools": ["Read"]})
        assert "--restricted" not in cmd  # 느슨한 값으로 제한 모드를 켜거나 끄는 혼동 방지(True 만 인정)


def test_stdin_is_devnull_so_claude_does_not_wait_for_input() -> None:
    """에이전트는 Electron 이 열린 빈 stdin 파이프로 띄운다 — 상속하면 claude -p 가 입력을 3초 기다린다
    (2026-10-04 실측 18.6초 → 15.1초). subprocess.run 에 stdin=DEVNULL 을 명시해야 한다."""
    import subprocess

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("core.agent_runtime.connection.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "숫자 1만 답해"})

    assert captured["kwargs"].get("stdin") is subprocess.DEVNULL
