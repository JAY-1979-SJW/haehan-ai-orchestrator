"""`claude -p` 텍스트 생성 어댑터 — 도구 없음·오류 처리. 실제 claude 를 부르지 않는다(러너 주입)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.naver.blog.automation import llm as L


def ok_json(text="본문입니다", **extra):
    return json.dumps({"result": text, "is_error": False, "total_cost_usd": 0.09, **extra}, ensure_ascii=False)


class FakeRun:
    def __init__(self, stdout="", returncode=0, raises=None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls = []

    def __call__(self, cmd, timeout, cwd):
        self.calls.append((cmd, timeout, cwd))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


# ── 명령 ─────────────────────────────────────────────────────────────────


def test_command_disables_tools_mcp_and_session_persistence():
    cmd = L.build_command("시스템", "사용자")
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""  # 모든 도구 끔
    assert "--strict-mcp-config" in cmd
    assert "--no-session-persistence" in cmd
    assert cmd[cmd.index("--system-prompt") + 1] == "시스템"
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_command_has_no_permission_bypass_or_allowed_tools():
    cmd = L.build_command("s", "u")
    for flag in (
        "--allowedTools",
        "--allowed-tools",
        "--dangerously-skip-permissions",
        "--mcp-config",
        "--permission-mode",
    ):
        assert flag not in cmd


def test_user_prompt_comes_last_after_separator():
    cmd = L.build_command("s", "-- 옵션처럼 보이는 사용자 텍스트")
    assert cmd[-2:] == ["--", "-- 옵션처럼 보이는 사용자 텍스트"]


def test_budget_and_model_options():
    cmd = L.build_command("s", "u", max_budget_usd=0.5, model="claude-sonnet-5-5")
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.5"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert "--model" not in L.build_command("s", "u")


# ── 출력 해석 ────────────────────────────────────────────────────────────


def test_parse_ok_strips_and_reports_cost():
    assert L.parse_output(ok_json("  글  ")) == {"ok": True, "text": "글", "cost_usd": 0.09}


@pytest.mark.parametrize(
    ("stdout", "error"),
    [
        ("not json", "invalid_json"),
        ("[1]", "invalid_json"),
        (json.dumps({"result": "x", "is_error": True}), "claude_reported_error"),
        (json.dumps({"result": "   "}), "empty_result"),
        (json.dumps({"result": None}), "empty_result"),
        (json.dumps({}), "empty_result"),
    ],
)
def test_parse_failures(stdout, error):
    assert L.parse_output(stdout) == {"ok": False, "error": error}


# ── 호출 ─────────────────────────────────────────────────────────────────


def test_llm_returns_text_and_uses_neutral_cwd(tmp_path):
    run = FakeRun(ok_json("결과"))
    llm = L.make_claude_llm(run=run, cwd=tmp_path, timeout=12.0)
    assert llm("sys", "usr", 5000) == {"ok": True, "text": "결과", "cost_usd": 0.09}
    cmd, timeout, cwd = run.calls[0]
    assert cmd[-1] == "usr" and timeout == 12.0 and cwd == tmp_path


def test_default_cwd_is_outside_the_repository():
    cwd = L.neutral_cwd()
    assert cwd.is_dir()
    assert Path.cwd().resolve() not in cwd.resolve().parents


def test_max_tokens_is_ignored_not_passed_to_cli():
    run = FakeRun(ok_json())
    L.make_claude_llm(run=run)("s", "u", 99999)
    assert "99999" not in run.calls[0][0]


@pytest.mark.parametrize(
    ("raises", "error"),
    [(FileNotFoundError(), "claude_cli_not_found"), (subprocess.TimeoutExpired("claude", 1), "timeout")],
)
def test_llm_turns_exceptions_into_failure_results(raises, error):
    assert L.make_claude_llm(run=FakeRun(raises=raises))("s", "u") == {"ok": False, "error": error}


def test_llm_reports_exit_code_when_no_output():
    assert L.make_claude_llm(run=FakeRun("", returncode=2))("s", "u") == {"ok": False, "error": "claude_exit_2"}


def test_web_tools_can_be_enabled_read_only():
    cmd = L.build_command("s", "u", tools=("WebSearch", "WebFetch"))
    assert cmd[cmd.index("--tools") + 1] == "WebFetch,WebSearch"
    assert cmd[cmd.index("--allowedTools") + 1] == "WebFetch,WebSearch"
    assert "--strict-mcp-config" in cmd and "--no-session-persistence" in cmd


@pytest.mark.parametrize("tool", ["Bash", "Write", "Edit", "Read", "mcp__haehan-orchestrator__call_api", "default", ""])
def test_write_capable_tools_are_refused(tool):
    with pytest.raises(ValueError):
        L.build_command("s", "u", tools=("WebSearch", tool))
    with pytest.raises(ValueError):
        L.make_claude_llm(tools=(tool,))


def test_llm_passes_tools_to_the_command():
    run = FakeRun(ok_json())
    L.make_claude_llm(run=run, tools=("WebSearch",))("s", "u")
    cmd = run.calls[0][0]
    assert cmd[cmd.index("--allowedTools") + 1] == "WebSearch"


def test_claude_available_uses_which():
    assert L.claude_available(which=lambda name: "C:/x/claude.exe" if name == "claude" else None)
    assert not L.claude_available(which=lambda name: None)
