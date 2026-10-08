"""local_agent/actions.py의 action_run_claude_agent 회귀 테스트.

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
from pathlib import Path
from unittest.mock import patch

from local_agent.actions import action_run_claude_agent


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _ok_payload(result: str = "1") -> str:
    return json.dumps({"result": result, "is_error": False, "session_id": "s1", "total_cost_usd": 0.01, "num_turns": 1})


def test_missing_prompt_short_circuits_without_subprocess() -> None:
    with patch("local_agent.actions.subprocess.run") as run:
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

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
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

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
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

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "p", "allowed_tools": "mcp__haehan-orchestrator__snapshot_page"})

    cmd = captured["cmd"]
    idx = cmd.index("--allowedTools")
    assert cmd[idx + 1] == "mcp__haehan-orchestrator__snapshot_page"


def test_claude_cli_not_found_returns_error_code() -> None:
    with patch("local_agent.actions.subprocess.run", side_effect=FileNotFoundError):
        result = action_run_claude_agent({"prompt": "p"})
    assert result.success is False
    assert result.error_code == "CLAUDE_CLI_NOT_FOUND"


def test_result_full_is_opt_in_and_default_behavior_unchanged() -> None:
    """작업 분배 종단 시험(2026-10-02)에서 계획 JSON 이 잘려 파싱 실패 → 긴 결과는 선택 키로만 제공."""
    long_text = "가" * 5000

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(_ok_payload(long_text))

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
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

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
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
    # 2026-10-08: --mcp-config 를 줄 때는 --strict-mcp-config 도 같이 줘야 사용자 claude.ai
    # 커넥터(Gmail 등)·다른 프로젝트 MCP 설정이 안 섞인다(지휘창 교차 점검에서 발견된 누출 수정).
    # "--restricted" 플래그 자체(도구 집합을 닫는 그 모드)는 여전히 켜지지 않는다.
    cmd = _capture_cmd({"allowed_tools": ["Read"]})
    assert "--mcp-config" in cmd and "--restricted" not in cmd and "--strict-mcp-config" in cmd
    assert "--tools" not in cmd


def test_restricted_requires_literal_true() -> None:
    for value in ("true", 1, "yes", None):
        cmd = _capture_cmd({"restricted": value, "allowed_tools": ["Read"]})
        assert "--restricted" not in cmd  # 느슨한 값으로 제한 모드를 켜거나 끄는 혼동 방지(True 만 인정)


def test_frozen_without_mcp_exe_env_omits_mcp_config_with_warning(monkeypatch, caplog) -> None:
    """2026-10-08 agent_error 사고: frozen exe 는 저장소 .mcp.json 을 못 쓴다. HAEHAN_MCP_EXE 가
    없으면 --mcp-config 를 조용히 생략하지 않고 경고를 남긴 뒤 생략해야 한다(claude 는 MCP 없이도 뜬다)."""
    import local_agent.actions as actions_mod

    monkeypatch.setattr(actions_mod.sys, "frozen", True, raising=False)
    monkeypatch.delenv("HAEHAN_MCP_EXE", raising=False)
    monkeypatch.delenv("HAEHAN_DATA_DIR", raising=False)
    with caplog.at_level("WARNING"):
        cmd = _capture_cmd({"prompt": "조사해"})
    assert "--mcp-config" not in cmd
    assert any("MCP" in r.message for r in caplog.records)


def test_frozen_with_mcp_exe_builds_runtime_mcp_config(monkeypatch, tmp_path) -> None:
    """HAEHAN_MCP_EXE·HAEHAN_DATA_DIR 가 있으면 데이터 폴더 아래 agent/mcp.json 을 만들어
    --mcp-config 로 넘긴다(저장소 .mcp.json 대신 번들 exe 를 가리킴)."""
    import local_agent.actions as actions_mod

    fake_exe = tmp_path / "haehan-mcp.exe"
    fake_exe.write_bytes(b"fake")
    data_dir = tmp_path / "data"

    monkeypatch.setattr(actions_mod.sys, "frozen", True, raising=False)
    monkeypatch.setenv("HAEHAN_MCP_EXE", str(fake_exe))
    monkeypatch.setenv("HAEHAN_DATA_DIR", str(data_dir))

    cmd = _capture_cmd({"prompt": "조사해"})

    idx = cmd.index("--mcp-config")
    cfg_path = Path(cmd[idx + 1])
    assert cfg_path == data_dir / "agent" / "mcp.json"
    body = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert body["mcpServers"]["haehan-orchestrator"]["command"] == str(fake_exe)


def test_frozen_with_missing_mcp_exe_file_omits_mcp_config(monkeypatch, tmp_path) -> None:
    """HAEHAN_MCP_EXE 가 가리키는 파일이 실제로 없으면(설치 손상 등) --mcp-config 를 생략한다."""
    import local_agent.actions as actions_mod

    monkeypatch.setattr(actions_mod.sys, "frozen", True, raising=False)
    monkeypatch.setenv("HAEHAN_MCP_EXE", str(tmp_path / "missing-haehan-mcp.exe"))
    monkeypatch.setenv("HAEHAN_DATA_DIR", str(tmp_path / "data"))

    cmd = _capture_cmd({"prompt": "조사해"})
    assert "--mcp-config" not in cmd


def test_frozen_cwd_uses_data_dir_not_bundle_internal_dir(monkeypatch, tmp_path) -> None:
    """frozen 일 때 작업 폴더는 PyInstaller 내부 폴더(_internal)가 아니라 HAEHAN_DATA_DIR 이어야 한다
    (2026-10-08 agent_error 사고: _internal 안에서 claude 를 돌릴 이유가 없고 쓰기 권한도 불확실)."""
    import local_agent.actions as actions_mod

    data_dir = tmp_path / "data"
    monkeypatch.setattr(actions_mod.sys, "frozen", True, raising=False)
    monkeypatch.setenv("HAEHAN_DATA_DIR", str(data_dir))
    monkeypatch.delenv("HAEHAN_MCP_EXE", raising=False)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "조사해"})

    assert captured["kwargs"]["cwd"] == str(data_dir)
    assert data_dir.is_dir()  # 호출 전에 만들어져 있어야 한다(없으면 subprocess 가 FileNotFoundError)


def test_not_frozen_cwd_unchanged() -> None:
    """dev 모드(sys.frozen 미설정)는 기존처럼 저장소 루트를 cwd 로 쓴다(회귀 방지)."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "조사해"})

    import local_agent.actions as actions_mod

    assert captured["kwargs"]["cwd"] == str(Path(actions_mod.__file__).parents[1])


def test_setting_sources_project_always_set_so_user_claude_md_hooks_skills_dont_leak() -> None:
    """2026-10-08 A 방식 전용 에이전트 분리: --setting-sources project 로 "user" 소스
    (~/.claude/CLAUDE.md·메모리·훅·스킬)를 안 읽는다. CLAUDE_CONFIG_DIR 로는 못 한다
    (로그인 자격까지 분리돼버림, 실측 확인) — 그래서 CLI 플래그로만 한다."""
    cmd = _capture_cmd({"allowed_tools": ["Read"]})
    idx = cmd.index("--setting-sources")
    assert cmd[idx + 1] == "project"


def test_append_system_prompt_present_and_warns_before_irreversible_actions() -> None:
    """앱 전용 역할·안전 지시가 모든 호출에 들어가야 한다(확인 요청 문구 포함)."""
    cmd = _capture_cmd({"allowed_tools": ["Read"]})
    idx = cmd.index("--append-system-prompt")
    prompt = cmd[idx + 1]
    assert "Haehan AI" in prompt
    assert "확인" in prompt


def test_non_restricted_mcp_call_is_strict_so_user_claudeai_connectors_dont_leak(monkeypatch, tmp_path) -> None:
    """2026-10-08 지휘창 교차 점검에서 발견: --mcp-config 만 주고 --strict-mcp-config 가 없어서
    사용자의 claude.ai 커넥터(Gmail 등)가 앱 세션에 새어 들어왔다("연결된 건 Gmail 뿐"이라 답함).
    --mcp-config 를 줄 때는 반드시 --strict-mcp-config 도 같이 가야 한다."""
    import local_agent.actions as actions_mod

    fake_exe = tmp_path / "haehan-mcp.exe"
    fake_exe.write_bytes(b"fake")
    monkeypatch.setattr(actions_mod.sys, "frozen", True, raising=False)
    monkeypatch.setenv("HAEHAN_MCP_EXE", str(fake_exe))
    monkeypatch.setenv("HAEHAN_DATA_DIR", str(tmp_path / "data"))

    cmd = _capture_cmd({})
    assert "--mcp-config" in cmd
    assert "--strict-mcp-config" in cmd


def test_stdin_is_devnull_so_claude_does_not_wait_for_input() -> None:
    """에이전트는 Electron 이 열린 빈 stdin 파이프로 띄운다 — 상속하면 claude -p 가 입력을 3초 기다린다
    (2026-10-04 실측 18.6초 → 15.1초). subprocess.run 에 stdin=DEVNULL 을 명시해야 한다."""
    import subprocess

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletedProcess(_ok_payload("1"))

    with patch("local_agent.actions.subprocess.run", side_effect=fake_run):
        action_run_claude_agent({"prompt": "숫자 1만 답해"})

    assert captured["kwargs"].get("stdin") is subprocess.DEVNULL
